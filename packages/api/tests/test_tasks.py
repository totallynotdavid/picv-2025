"""Worker lifecycle behavior at the repository and engine boundaries."""

import asyncio
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest
from rqueue import PermanentFailure, TaskContext
from rqueue.testing import RecordingQueue

from api.core import queue as queue_module
from api.core import tasks
from api.core.errors import TransientInfraError
from api.core.settings import COMPUTE_QUEUE
from api.core.tasks import MAX_ATTEMPTS, RUN_SIMULATION
from tsdhn.domain import EarthquakeInput, JobStatus

tasks_module: Any = tasks

INPUT = EarthquakeInput(Mw=8.0, h=10.0, lat0=-20.5, lon0=-70.5, hhmm="0000", dia="23")


class _Connection:
    """Stands in for the caller's asyncpg connection; never used as one."""


def _context(attempt: int) -> TaskContext:
    async def heartbeat() -> bool:
        return False

    return TaskContext(
        job_id=uuid.uuid4(),
        queue=COMPUTE_QUEUE,
        task=RUN_SIMULATION,
        attempt=attempt,
        max_attempts=MAX_ATTEMPTS,
        metadata={},
        heartbeat=heartbeat,
        cancel_event=asyncio.Event(),
    )


def _row(
    job_id: uuid.UUID, simulation_id: uuid.UUID, status: JobStatus = JobStatus.QUEUED
) -> dict[str, Any]:
    return {
        "id": job_id,
        "simulation_id": simulation_id,
        "status": status.value,
        "input_params": INPUT.model_dump(mode="json"),
    }


@pytest.fixture
def recording_queue(monkeypatch: pytest.MonkeyPatch) -> RecordingQueue:
    """Install a queue that runs the real validation and records the result."""
    queue = RecordingQueue(name=COMPUTE_QUEUE)
    tasks.register_tasks(queue)
    monkeypatch.setattr(queue_module, "_queue", queue)
    return queue


@pytest.fixture
def worker_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[uuid.UUID, uuid.UUID, Path]:
    job_id = uuid.uuid4()
    simulation_id = uuid.uuid4()
    work_dir = tmp_path / "jobs" / str(simulation_id)
    work_dir.mkdir(parents=True)
    connection = _Connection()

    class _Acquire:
        async def __aenter__(self) -> _Connection:
            return connection

        async def __aexit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(tasks_module.db, "acquire", lambda: _Acquire())
    monkeypatch.setattr(tasks_module, "JOBS_DIR", tmp_path / "jobs")

    async def fetch_by_id(_conn: Any, _id: uuid.UUID) -> dict[str, Any]:
        return _row(job_id, simulation_id)

    monkeypatch.setattr(tasks_module.repository, "fetch_by_id", fetch_by_id)
    return job_id, simulation_id, work_dir


@pytest.mark.asyncio
async def test_enqueue_simulation_builds_the_job_the_worker_expects(
    recording_queue: RecordingQueue,
) -> None:
    connection = _Connection()
    compute_job_id = uuid.uuid4()

    await tasks.enqueue_simulation(connection, compute_job_id)

    (recorded,) = recording_queue.enqueued(RUN_SIMULATION)
    assert recorded.connection is connection
    assert recorded.queue == COMPUTE_QUEUE
    assert recorded.payload == {"compute_job_id": str(compute_job_id)}
    # queueing_lock and lock, ported one for one onto rqueue's two keys.
    assert recorded.dedupe_key == f"simulation:{compute_job_id}"
    assert recorded.concurrency_key == f"compute-job:{compute_job_id}"
    # The registered retry policy, not the queue default, reaches the row.
    assert recorded.spec.max_attempts == MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_enqueue_simulation_fails_when_the_queue_was_never_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(queue_module, "_queue", None)

    with pytest.raises(RuntimeError, match="build_queue"):
        await tasks.enqueue_simulation(_Connection(), uuid.uuid4())


@pytest.mark.asyncio
async def test_run_simulation_task_completes_and_removes_the_workspace(
    worker_job: tuple[uuid.UUID, uuid.UUID, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, simulation_id, work_dir = worker_job
    events: list[tuple[str, Any]] = []
    result = object()

    async def mark_started(
        _conn: Any, current_id: Any, current_external: Any, attempt: int
    ) -> bool:
        events.append(("started", (current_id, current_external, attempt)))
        return True

    async def record_progress(
        _conn: Any,
        current_id: Any,
        current_external: Any,
        message: str,
        details: dict[str, Any],
        attempt: int,
    ) -> bool:
        events.append(("progress", (current_id, current_external, message, details)))
        return True

    async def complete_job(
        _conn: Any, _row: Any, completed: Any, _attempt: int
    ) -> bool:
        events.append(("completed", completed))
        return True

    monkeypatch.setattr(tasks_module.repository, "mark_started", mark_started)
    monkeypatch.setattr(tasks_module.repository, "record_progress", record_progress)
    monkeypatch.setattr(tasks_module.repository, "complete_job", complete_job)

    def run_simulation(
        data: EarthquakeInput,
        current_work_dir: Path,
        *,
        resume: bool,
        on_progress: Any,
    ) -> object:
        events.append(("run", (data, current_work_dir, resume)))
        on_progress("Processing tsunami", {"step": "tsunami"})
        return result

    monkeypatch.setattr(tasks_module, "run_simulation", run_simulation)

    await tasks.run_simulation_task(job_id, _context(attempt=1))

    assert events == [
        ("started", (job_id, simulation_id, 1)),
        ("run", (INPUT, work_dir, True)),
        (
            "progress",
            (job_id, simulation_id, "Processing tsunami", {"step": "tsunami"}),
        ),
        ("completed", result),
    ]
    assert not work_dir.exists()


@pytest.mark.asyncio
async def test_the_simulation_runs_off_the_event_loop(
    worker_job: tuple[uuid.UUID, uuid.UUID, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, _simulation_id, _work_dir = worker_job
    threads: list[int] = []

    async def claimed(*_args: Any, **_kwargs: Any) -> bool:
        """mark_started and friends: the claim always succeeds in these tests."""
        return True

    monkeypatch.setattr(tasks_module.repository, "mark_started", claimed)
    monkeypatch.setattr(tasks_module.repository, "record_progress", claimed)
    monkeypatch.setattr(tasks_module.repository, "complete_job", claimed)

    def run_simulation(*_args: Any, on_progress: Any, **_kwargs: Any) -> object:
        import threading

        threads.append(threading.get_ident())
        # The callback runs on this thread and has to reach the loop's pool.
        on_progress("Processing tsunami", {"step": "tsunami"})
        return object()

    monkeypatch.setattr(tasks_module, "run_simulation", run_simulation)

    import threading

    await tasks.run_simulation_task(job_id, _context(attempt=1))

    # A blocking kernel on the loop thread would stall rqueue's heartbeat and
    # cost the worker its lease mid-run.
    assert threads and threads[0] != threading.get_ident()


@pytest.mark.asyncio
@pytest.mark.parametrize(("attempt", "will_retry"), [(1, True), (MAX_ATTEMPTS, False)])
async def test_run_simulation_task_records_failure_and_preserves_workspace(
    worker_job: tuple[uuid.UUID, uuid.UUID, Path],
    monkeypatch: pytest.MonkeyPatch,
    attempt: int,
    will_retry: bool,
) -> None:
    job_id, simulation_id, work_dir = worker_job
    failures: list[dict[str, Any]] = []

    async def claimed(*_args: Any, **_kwargs: Any) -> bool:
        """mark_started and friends: the claim always succeeds in these tests."""
        return True

    async def get_current_step(_conn: Any, _job_id: uuid.UUID) -> str:
        return "tsunami"

    async def record_failure(
        _conn: Any,
        current_id: Any,
        current_external: Any,
        exc: Exception,
        *,
        step: str | None,
        will_retry: bool,
        attempt: int,
    ) -> None:
        failures.append(
            {
                "job_id": current_id,
                "simulation_id": current_external,
                "exception": exc,
                "step": step,
                "will_retry": will_retry,
            }
        )

    monkeypatch.setattr(tasks_module.repository, "mark_started", claimed)
    monkeypatch.setattr(tasks_module.repository, "get_current_step", get_current_step)
    monkeypatch.setattr(tasks_module.repository, "record_failure", record_failure)

    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise TransientInfraError("storage unavailable")

    monkeypatch.setattr(tasks_module, "run_simulation", fail)

    with pytest.raises(TransientInfraError, match="storage unavailable"):
        await tasks.run_simulation_task(job_id, _context(attempt))

    assert len(failures) == 1
    assert failures[0]["job_id"] == job_id
    assert failures[0]["simulation_id"] == simulation_id
    assert isinstance(failures[0]["exception"], TransientInfraError)
    assert failures[0]["step"] == "tsunami"
    assert failures[0]["will_retry"] is will_retry
    assert work_dir.exists()


@pytest.mark.asyncio
async def test_a_failed_failure_write_does_not_replace_the_original_error(
    worker_job: tuple[uuid.UUID, uuid.UUID, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, _simulation_id, _work_dir = worker_job

    async def claimed(*_args: Any, **_kwargs: Any) -> bool:
        """mark_started and friends: the claim always succeeds in these tests."""
        return True

    async def unavailable(*_args: Any, **_kwargs: Any) -> None:
        raise TransientInfraError("database connection failed")

    monkeypatch.setattr(tasks_module.repository, "mark_started", claimed)
    monkeypatch.setattr(tasks_module.repository, "get_current_step", unavailable)

    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise RuntimeError("bad epicenter")

    monkeypatch.setattr(tasks_module, "run_simulation", fail)

    # The pipeline error is what rqueue must see, so it applies retry_on to
    # the real cause rather than to a second outage reporting it.
    with pytest.raises(RuntimeError, match="bad epicenter"):
        await tasks.run_simulation_task(job_id, _context(attempt=1))


@pytest.mark.asyncio
async def test_run_simulation_task_rejects_an_unknown_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Acquire:
        async def __aenter__(self) -> _Connection:
            return _Connection()

        async def __aexit__(self, *_exc: object) -> None:
            return None

    async def missing(*_args: Any) -> None:
        return None

    monkeypatch.setattr(tasks_module.db, "acquire", lambda: _Acquire())
    monkeypatch.setattr(tasks_module.repository, "fetch_by_id", missing)

    # No later attempt can find a row that was never written.
    with pytest.raises(PermanentFailure, match="Unknown compute job"):
        await tasks.run_simulation_task(uuid.uuid4(), _context(attempt=1))


@pytest.mark.asyncio
async def test_sweep_abandoned_work_dirs_removes_only_selected_workspaces(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    old_id = str(uuid.uuid4())
    old_dir = tmp_path / old_id
    old_dir.mkdir()
    unrelated = tmp_path / "keep"
    unrelated.mkdir()

    async def list_abandoned_work_dirs(_cutoff: Any) -> list[str]:
        return [old_id]

    monkeypatch.setattr(
        tasks_module.repository,
        "list_abandoned_work_dirs",
        list_abandoned_work_dirs,
    )
    monkeypatch.setattr(tasks_module, "JOBS_DIR", tmp_path)

    await tasks.sweep_abandoned_work_dirs()

    assert not old_dir.exists()
    assert unrelated.exists()


@pytest.mark.asyncio
async def test_the_periodic_sweep_keeps_running_after_a_failed_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passes: list[int] = []
    stop = asyncio.Event()

    async def sweep() -> None:
        passes.append(len(passes))
        if len(passes) == 1:
            raise RuntimeError("database unavailable")
        stop.set()

    monkeypatch.setattr(tasks_module, "sweep_abandoned_work_dirs", sweep)

    await tasks.run_periodic_sweep(stop, interval=0.01)

    assert len(passes) == 2


@pytest.mark.asyncio
async def test_the_periodic_reconcile_keeps_running_after_a_failed_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passes: list[int] = []
    stop = asyncio.Event()

    async def reconcile(**_kwargs: Any) -> None:
        passes.append(len(passes))
        if len(passes) == 1:
            raise TransientInfraError("database connection failed")
        stop.set()

    monkeypatch.setattr(tasks_module, "reconcile_terminal_jobs", reconcile)

    # A database outage is exactly when jobs get stranded, so it must not be
    # the thing that stops the pass which unstrands them.
    await tasks.run_periodic_reconcile(stop, interval=0.01)

    assert len(passes) == 2


@pytest.mark.asyncio
async def test_an_abandoned_attempt_stops_writing_from_its_kernel_thread(
    worker_job: tuple[uuid.UUID, uuid.UUID, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, _simulation_id, _work_dir = worker_job
    messages: list[str] = []
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    raised: list[BaseException] = []

    async def claimed(*_args: Any, **_kwargs: Any) -> bool:
        """mark_started and friends: the claim always succeeds in these tests."""
        return True

    async def record_progress(
        _conn: Any, _id: Any, _external: Any, message: str, _details: Any, _attempt: int
    ) -> bool:
        messages.append(message)
        return True

    monkeypatch.setattr(tasks_module.repository, "mark_started", claimed)
    monkeypatch.setattr(tasks_module.repository, "record_progress", record_progress)

    def run_simulation(*_args: Any, on_progress: Any, **_kwargs: Any) -> object:
        try:
            on_progress("Processing tsunami", {})
            entered.set()
            release.wait(5)
            on_progress("Processing maxola", {})
            return object()
        except BaseException as e:
            raised.append(e)
            raise
        finally:
            finished.set()

    monkeypatch.setattr(tasks_module, "run_simulation", run_simulation)

    task = asyncio.create_task(tasks.run_simulation_task(job_id, _context(attempt=1)))
    await asyncio.to_thread(entered.wait, 5)

    # rqueue cancels the handler coroutine when the heartbeat finds the lease
    # gone. Python cannot kill the thread underneath it, and that thread still
    # holds a live reference to this loop.
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    release.set()
    await asyncio.to_thread(finished.wait, 5)

    # The write from before the cancellation stands; the one after is refused,
    # and the refusal unwinds the kernel instead of letting it run on.
    assert messages == ["Processing tsunami"]
    assert raised and isinstance(raised[0], tasks.AbandonedAttempt)


def test_a_workspace_held_by_a_live_thread_is_not_resumed(tmp_path: Path) -> None:
    """The filesystem half of the fence, which the database fence cannot cover.

    A kernel thread abandoned mid-step keeps writing into a workspace keyed by
    simulation id. A replacement attempt resuming from those checkpoints could
    read a half-written one, which is worse than a confusing status: it yields a
    wrong scientific result rather than an error.
    """
    work_dir = tmp_path / "sim"
    work_dir.mkdir()
    holding = threading.Event()
    release = threading.Event()

    def zombie() -> None:
        claim, _resume = tasks.claim_workspace(work_dir, 1)
        holding.set()
        release.wait(5)
        claim.release()
        claim.release()

    thread = threading.Thread(target=zombie)
    thread.start()
    assert holding.wait(5)

    # flock is held against the open file description, so the replacement is
    # refused even though it is another thread of this same process.
    with pytest.raises(TransientInfraError, match="still held by an earlier attempt"):
        tasks.claim_workspace(work_dir, 2)

    release.set()
    thread.join(5)

    # Once the owner really is gone the workspace is resumable again, which is
    # what an ordinary worker crash looks like: the kernel drops the lock with
    # the process.
    claim, resume = tasks.claim_workspace(work_dir, 2)
    assert resume is True
    claim.release()
    claim.release()


def test_a_claim_survives_until_its_last_share_is_given_back(tmp_path: Path) -> None:
    """The kernel thread and the upload hold the same claim, one share each.

    complete_job reads the result files back out of the workspace after the
    kernel thread has returned. If the claim ended with the kernel, a lease lost
    in between would let a redelivered attempt take the freed lock and write
    into the directory being uploaded from -- the same corruption, a few lines
    later.
    """
    work_dir = tmp_path / "sim"
    work_dir.mkdir()
    claim, _resume = tasks.claim_workspace(work_dir, 1)

    # The kernel thread finishes; the upload has not started.
    claim.release()
    with pytest.raises(TransientInfraError, match="still held by an earlier attempt"):
        tasks.claim_workspace(work_dir, 2)

    # The upload finishes too.
    claim.release()
    second, _ = tasks.claim_workspace(work_dir, 2)
    second.release()
    second.release()


def test_releasing_a_claim_more_than_twice_is_harmless(tmp_path: Path) -> None:
    work_dir = tmp_path / "sim"
    work_dir.mkdir()
    claim, _resume = tasks.claim_workspace(work_dir, 1)
    for _ in range(4):
        claim.release()


@pytest.mark.asyncio
async def test_a_cancelled_attempt_keeps_holding_its_workspace(
    worker_job: tuple[uuid.UUID, uuid.UUID, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The claim is tied to the thread, not to the coroutine.

    Releasing it when the coroutine is cancelled would hand the workspace to a
    replacement attempt while the thread it belongs to is still writing there.
    """
    job_id, _simulation_id, work_dir = worker_job
    entered = threading.Event()
    release = threading.Event()

    async def claimed(*_args: Any, **_kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(tasks_module.repository, "mark_started", claimed)

    def hang(*_args: Any, **_kwargs: Any) -> object:
        entered.set()
        release.wait(5)
        return object()

    monkeypatch.setattr(tasks_module, "run_simulation", hang)

    task = asyncio.create_task(tasks.run_simulation_task(job_id, _context(attempt=1)))
    await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The coroutine is gone, and gave back its own share; the thread is not, and
    # still holds its own.
    with pytest.raises(TransientInfraError, match="still held by an earlier attempt"):
        tasks.claim_workspace(work_dir, 2)

    release.set()


def test_a_fresh_workspace_reports_that_there_is_nothing_to_resume(
    tmp_path: Path,
) -> None:
    claim, resume = tasks.claim_workspace(tmp_path / "unstarted", 1)
    assert resume is False
    claim.release()
    claim.release()
    # The lock lives beside the workspace, not inside it: the engine removes the
    # whole directory when a run starts without resuming.
    assert (tmp_path / "unstarted.lock").exists()
    assert not (tmp_path / "unstarted").exists()


def test_removing_a_workspace_takes_its_lock_file_with_it(tmp_path: Path) -> None:
    work_dir = tmp_path / "sim"
    work_dir.mkdir()
    claim, _resume = tasks.claim_workspace(work_dir, 1)
    claim.release()
    claim.release()

    assert tasks.remove_workspace(work_dir) is True

    assert not work_dir.exists()
    assert not (tmp_path / "sim.lock").exists()
    # Idempotent: the sweep runs over jobs it may already have cleaned.
    assert tasks.remove_workspace(work_dir) is True


def test_a_held_workspace_is_left_for_the_next_sweep(tmp_path: Path) -> None:
    """The flock+unlink race, which is why removal takes the lock first.

    unlink() drops the directory entry while the holder keeps its lock on the
    now-orphaned inode, so the next O_CREAT at that path makes a *new* inode
    and locks it uncontended -- two threads each believing they own the
    workspace. The sweep reaches jobs whose row is terminal while their kernel
    thread is still alive, so this is reachable.
    """
    work_dir = tmp_path / "sim"
    work_dir.mkdir()
    (work_dir / "checkpoint").write_text("half written", encoding="utf-8")
    claim, _resume = tasks.claim_workspace(work_dir, 1)

    assert tasks.remove_workspace(work_dir) is False
    assert work_dir.exists()
    assert (tmp_path / "sim.lock").exists()

    # And the holder's claim still means something afterwards.
    with pytest.raises(TransientInfraError, match="still held by an earlier attempt"):
        tasks.claim_workspace(work_dir, 2)

    claim.release()
    claim.release()
    assert tasks.remove_workspace(work_dir) is True
    assert not work_dir.exists()
