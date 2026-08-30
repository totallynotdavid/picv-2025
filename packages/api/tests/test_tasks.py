"""Worker lifecycle behavior at the repository and engine boundaries."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from procrastinate import exceptions as procrastinate_exceptions
from procrastinate.jobs import Job as ProcrastinateJob

from api.core import tasks
from api.core.errors import TransientInfraError
from api.core.tasks import MAX_ATTEMPTS
from tsdhn.domain import EarthquakeInput

tasks_module: Any = tasks

INPUT = EarthquakeInput(Mw=8.0, h=10.0, lat0=-20.5, lon0=-70.5, hhmm="0000", dia="23")


class _Connection:
    pass


class _TaskContext:
    def __init__(self, attempts: int) -> None:
        self.job = SimpleNamespace(attempts=attempts)


def _row(job_id: uuid.UUID, simulation_id: uuid.UUID) -> dict[str, Any]:
    return {
        "id": job_id,
        "simulation_id": simulation_id,
        "input_params": INPUT.model_dump(mode="json"),
    }


@pytest.fixture
def worker_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[uuid.UUID, uuid.UUID, Path, _Connection]:
    job_id = uuid.uuid4()
    simulation_id = uuid.uuid4()
    work_dir = tmp_path / "jobs" / str(simulation_id)
    work_dir.mkdir(parents=True)
    connection = _Connection()

    @contextmanager
    def connect() -> Iterator[_Connection]:
        yield connection

    monkeypatch.setattr(tasks_module, "connect", connect)
    monkeypatch.setattr(tasks_module, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(
        tasks_module.repository,
        "fetch_by_id",
        lambda _conn, _id: _row(job_id, simulation_id),
    )
    return job_id, simulation_id, work_dir, connection


def test_run_simulation_task_completes_and_removes_the_workspace(
    worker_job: tuple[uuid.UUID, uuid.UUID, Path, _Connection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, simulation_id, work_dir, connection = worker_job
    events: list[tuple[str, Any]] = []
    result = object()

    monkeypatch.setattr(
        tasks_module.repository,
        "mark_started",
        lambda conn, current_id, current_external: events.append(
            ("started", (conn, current_id, current_external))
        ),
    )
    monkeypatch.setattr(
        tasks_module.repository,
        "record_progress",
        lambda conn, current_id, current_external, message, details: events.append(
            ("progress", (conn, current_id, current_external, message, details))
        ),
    )
    monkeypatch.setattr(
        tasks_module.repository,
        "complete_job",
        lambda conn, row, completed: events.append(("completed", (conn, completed))),
    )

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

    tasks_module.run_simulation_task.func(_TaskContext(attempts=0), str(job_id))

    assert events == [
        ("started", (connection, job_id, simulation_id)),
        ("run", (INPUT, work_dir, True)),
        (
            "progress",
            (
                connection,
                job_id,
                simulation_id,
                "Processing tsunami",
                {"step": "tsunami"},
            ),
        ),
        ("completed", (connection, result)),
    ]
    assert not work_dir.exists()


@pytest.mark.parametrize(("attempts", "will_retry"), [(0, True), (MAX_ATTEMPTS, False)])
def test_run_simulation_task_records_failure_and_preserves_workspace(
    worker_job: tuple[uuid.UUID, uuid.UUID, Path, _Connection],
    monkeypatch: pytest.MonkeyPatch,
    attempts: int,
    will_retry: bool,
) -> None:
    job_id, simulation_id, work_dir, connection = worker_job
    failures: list[dict[str, Any]] = []

    monkeypatch.setattr(tasks_module.repository, "mark_started", lambda *_args: None)
    monkeypatch.setattr(
        tasks_module.repository, "get_current_step", lambda _conn, _job_id: "tsunami"
    )

    def record_failure(
        conn: Any,
        current_id: Any,
        current_external: Any,
        exc: Exception,
        *,
        step: str | None,
        will_retry: bool,
    ) -> None:
        failures.append(
            {
                "conn": conn,
                "job_id": current_id,
                "simulation_id": current_external,
                "exception": exc,
                "step": step,
                "will_retry": will_retry,
            }
        )

    monkeypatch.setattr(
        tasks_module.repository,
        "record_failure",
        record_failure,
    )

    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise TransientInfraError("storage unavailable")

    monkeypatch.setattr(tasks_module, "run_simulation", fail)

    with pytest.raises(TransientInfraError, match="storage unavailable"):
        tasks_module.run_simulation_task.func(_TaskContext(attempts), str(job_id))

    assert len(failures) == 1
    assert failures[0]["conn"] is connection
    assert failures[0]["job_id"] == job_id
    assert failures[0]["simulation_id"] == simulation_id
    assert isinstance(failures[0]["exception"], TransientInfraError)
    assert failures[0]["step"] == "tsunami"
    assert failures[0]["will_retry"] is will_retry
    assert work_dir.exists()


def test_run_simulation_task_rejects_an_unknown_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()

    @contextmanager
    def connect() -> Iterator[_Connection]:
        yield connection

    monkeypatch.setattr(tasks_module, "connect", connect)
    monkeypatch.setattr(tasks_module.repository, "fetch_by_id", lambda *_args: None)
    job_id = uuid.uuid4()

    with pytest.raises(RuntimeError, match="Unknown compute job"):
        tasks_module.run_simulation_task.func(_TaskContext(0), str(job_id))


def test_enqueue_simulation_configures_and_defers_the_worker_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    compute_job_id = uuid.uuid4()
    configured: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []

    class _ConfiguredTask:
        def configure(self, **kwargs: Any) -> Any:
            configured.append(kwargs)
            return self

        def defer(self, **kwargs: Any) -> None:
            deferred.append(kwargs)

    monkeypatch.setattr(tasks_module, "run_simulation_task", _ConfiguredTask())

    tasks_module.enqueue_simulation(connection, compute_job_id)

    assert configured == [
        {
            "connection": connection,
            "queue": tasks_module.PROCRASTINATE_QUEUE,
            "queueing_lock": f"simulation:{compute_job_id}",
            "lock": f"compute-job:{compute_job_id}",
        }
    ]
    assert deferred == [{"compute_job_id": str(compute_job_id)}]


class _JobManager:
    def __init__(self, jobs: list[ProcrastinateJob]) -> None:
        self.jobs = jobs
        self.retried: list[int] = []
        self.finished: list[int] = []

    async def get_stalled_jobs(
        self, *, seconds_since_heartbeat: int
    ) -> list[ProcrastinateJob]:
        assert seconds_since_heartbeat == tasks_module.STALLED_HEARTBEAT_SECONDS
        return self.jobs

    async def retry_job_by_id_async(self, *, job_id: int, retry_at: Any) -> None:
        self.retried.append(job_id)

    async def finish_job_by_id_async(
        self, *, job_id: int, status: Any, delete_job: bool
    ) -> None:
        assert status.value == "failed"
        assert delete_job is False
        self.finished.append(job_id)


def _queue_job(job_id: int | None, attempts: int) -> ProcrastinateJob:
    return ProcrastinateJob(
        id=job_id,
        queue="simulations",
        lock=None,
        queueing_lock=None,
        task_name="api.run_simulation",
        task_kwargs={"compute_job_id": str(uuid.uuid4())},
        attempts=attempts,
    )


@pytest.mark.asyncio
async def test_reap_stalled_jobs_retries_or_finishes_by_attempt_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retry_job = _queue_job(1, 0)
    exhausted_job = _queue_job(2, MAX_ATTEMPTS)
    manager = _JobManager([retry_job, exhausted_job])
    exhausted_ids: list[str] = []

    monkeypatch.setattr(tasks_module.app, "job_manager", manager)
    monkeypatch.setattr(
        tasks_module,
        "_fail_exhausted",
        lambda compute_job_id: exhausted_ids.append(compute_job_id),
    )

    await tasks_module.reap_stalled_jobs_task.func(0)

    assert manager.retried == [1]
    assert manager.finished == [2]
    assert exhausted_ids == [exhausted_job.task_kwargs["compute_job_id"]]


@pytest.mark.asyncio
async def test_reap_stalled_jobs_returns_when_the_queue_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _JobManager([])
    monkeypatch.setattr(tasks_module.app, "job_manager", manager)

    await tasks_module.reap_stalled_jobs_task.func(0)

    assert manager.retried == []
    assert manager.finished == []


@pytest.mark.asyncio
async def test_reap_stalled_jobs_ignores_malformed_queue_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = _queue_job(None, 0)
    missing_compute_id = ProcrastinateJob(
        id=3,
        queue="simulations",
        lock=None,
        queueing_lock=None,
        task_name="api.run_simulation",
        task_kwargs={},
        attempts=0,
    )
    manager = _JobManager([missing_id, missing_compute_id])
    monkeypatch.setattr(tasks_module.app, "job_manager", manager)

    await tasks_module.reap_stalled_jobs_task.func(0)

    assert manager.retried == []
    assert manager.finished == []


@pytest.mark.asyncio
async def test_reap_stalled_jobs_tolerates_queue_connector_races(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retry_job = _queue_job(1, 0)
    exhausted_job = _queue_job(2, MAX_ATTEMPTS)
    manager = _JobManager([retry_job, exhausted_job])
    retry_attempts: list[int] = []
    finish_attempts: list[int] = []
    exhausted_ids: list[str] = []

    async def retry_failure(*, job_id: int, retry_at: Any) -> None:
        retry_attempts.append(job_id)
        raise procrastinate_exceptions.ConnectorException("job already resolved")

    async def finish_failure(*, job_id: int, status: Any, delete_job: bool) -> None:
        finish_attempts.append(job_id)
        raise procrastinate_exceptions.ConnectorException("job already resolved")

    monkeypatch.setattr(tasks_module.app, "job_manager", manager)
    monkeypatch.setattr(tasks_module, "_fail_exhausted", exhausted_ids.append)
    monkeypatch.setattr(manager, "retry_job_by_id_async", retry_failure)
    monkeypatch.setattr(manager, "finish_job_by_id_async", finish_failure)

    await tasks_module.reap_stalled_jobs_task.func(0)

    assert retry_attempts == [1]
    assert exhausted_ids == [exhausted_job.task_kwargs["compute_job_id"]]
    assert finish_attempts == [2]


def test_sweep_abandoned_work_dirs_removes_only_selected_workspaces(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    old_id = str(uuid.uuid4())
    old_dir = tmp_path / old_id
    old_dir.mkdir()
    unrelated = tmp_path / "keep"
    unrelated.mkdir()
    monkeypatch.setattr(
        tasks_module.repository, "list_abandoned_work_dirs", lambda _cutoff: [old_id]
    )
    monkeypatch.setattr(tasks_module, "JOBS_DIR", tmp_path)

    tasks_module.sweep_abandoned_work_dirs_task.func(0)

    assert not old_dir.exists()
    assert unrelated.exists()


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_fail_exhausted_does_not_overwrite_terminal_jobs(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    connection = _Connection()

    @contextmanager
    def pooled() -> Iterator[_Connection]:
        yield connection

    monkeypatch.setattr(tasks_module, "pooled", pooled)
    fetched: list[tuple[Any, ...]] = []

    def fetch(*args: Any) -> dict[str, Any]:
        fetched.append(args)
        return {"status": status, "simulation_id": uuid.uuid4()}

    monkeypatch.setattr(tasks_module.repository, "fetch_by_id", fetch)
    monkeypatch.setattr(
        tasks_module.repository,
        "fail_job",
        lambda *_args: pytest.fail("terminal job must not be overwritten"),
    )

    tasks_module._fail_exhausted(str(uuid.uuid4()))

    assert len(fetched) == 1


def test_fail_exhausted_marks_an_active_job_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    simulation_id = uuid.uuid4()
    failures: list[tuple[Any, ...]] = []

    @contextmanager
    def pooled() -> Iterator[_Connection]:
        yield connection

    monkeypatch.setattr(tasks_module, "pooled", pooled)
    monkeypatch.setattr(
        tasks_module.repository,
        "fetch_by_id",
        lambda *_args: {"status": "running", "simulation_id": simulation_id},
    )
    monkeypatch.setattr(
        tasks_module.repository,
        "fail_job",
        lambda *args: failures.append(args),
    )

    job_id = uuid.uuid4()
    tasks_module._fail_exhausted(str(job_id))

    assert failures == [
        (
            connection,
            job_id,
            simulation_id,
            tasks_module.CRASH_BUDGET_EXHAUSTED_ERROR,
        )
    ]
