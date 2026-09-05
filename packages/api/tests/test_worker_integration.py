"""A real rqueue.Worker running the simulation task against PostgreSQL."""

import asyncio
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from rqueue import Admin, Queue, Worker

from api.core import db, repository, tasks
from api.core.errors import TransientInfraError
from api.core.settings import COMPUTE_QUEUE_SCHEMA
from api.core.storage import output_store
from api.core.tasks import RUN_SIMULATION, enqueue_simulation
from tsdhn.domain import CalculationResponse, EarthquakeInput, TsunamiTravelResponse
from tsdhn.engine import OutputFile, SimulationOutputs, SimulationResult
from tsdhn.runtime import RuntimeContext

pytestmark = pytest.mark.integration

db_module: Any = db

INPUT = EarthquakeInput(Mw=8.0, h=10.0, lat0=-20.5, lon0=-70.5, hhmm="0000", dia="23")


def _result(root: Path) -> SimulationResult:
    output_path = root / "calculation.json"
    output_path.write_text("{}", encoding="utf-8")
    return SimulationResult(
        calculation=CalculationResponse(
            length=1.0,
            width=2.0,
            dislocation=3.0,
            seismic_moment=4.0,
            tsunami_warning="none",
            distance_to_coast=5.0,
            azimuth=6.0,
            dip=7.0,
            epicenter_location="0.00/0.00",
            rectangle_parameters={},
            rectangle_corners=[],
        ),
        travel_times=TsunamiTravelResponse(
            arrival_times={"PORT": "01:00"},
            distances={"PORT": 100.0},
            epicenter_info={"lat": "0.0"},
        ),
        runtime=RuntimeContext(model_dir=root, model_version="test", capabilities={}),
        outputs=SimulationOutputs(
            root=root,
            files=(OutputFile("calculation", output_path, "application/json"),),
        ),
    )


async def _submit(simulation_id: str) -> uuid.UUID:
    await repository.create_or_get_job(
        data=INPUT, simulation_id=simulation_id, defer=enqueue_simulation
    )
    async with db.acquire() as conn:
        compute_job_id: uuid.UUID = await conn.fetchval(
            "SELECT id FROM compute.jobs WHERE simulation_id = $1",
            uuid.UUID(simulation_id),
        )
    return compute_job_id


async def _queue_row(compute_job_id: uuid.UUID) -> Any:
    async with db.acquire() as conn:
        return await conn.fetchrow(
            f"SELECT * FROM {COMPUTE_QUEUE_SCHEMA}.jobs "  # noqa: S608
            "WHERE payload->>'compute_job_id' = $1",
            str(compute_job_id),
        )


def _worker(queue: Queue) -> Worker:
    return Worker(queue, worker_id="test-worker", concurrency=2, lease_duration=30.0)


@pytest.mark.asyncio
async def test_a_queued_simulation_runs_to_completion_on_a_bounded_thread(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")
    (tmp_path / "jobs" / simulation_id).mkdir(parents=True)
    kernel_threads: list[str] = []

    def run_simulation(
        _data: EarthquakeInput,
        work_dir: Path,
        *,
        resume: bool,
        on_progress: Any,
    ) -> SimulationResult:
        kernel_threads.append(threading.current_thread().name)
        on_progress(
            "Processing tsunami",
            {"step": "tsunami", "step_index": 3, "total_steps": 8},
        )
        return _result(work_dir)

    monkeypatch.setattr(tasks, "run_simulation", run_simulation)
    monkeypatch.setattr(
        output_store,
        "upload_simulation_result",
        lambda **_kwargs: ("results", "simulations/x/metadata.json"),
    )

    compute_job_id = await _submit(simulation_id)
    await _worker(queue).drain(timeout=60)

    status = await repository.get_job_status(simulation_id)
    assert status["status"] == "completed"
    assert status["outputs"] == ["calculation"]

    row = await _queue_row(compute_job_id)
    assert row["state"] == "succeeded"
    assert row["attempt"] == 1
    assert row["error_type"] is None

    # rqueue installs its own bounded default executor, so a bare
    # asyncio.to_thread lands there rather than on the interpreter's default.
    assert kernel_threads
    assert kernel_threads[0].startswith("rqueue-test-worker")
    assert kernel_threads[0] != threading.current_thread().name

    # The workspace is removed once the result is durable.
    assert not (tmp_path / "jobs" / simulation_id).exists()


@pytest.mark.asyncio
async def test_a_pipeline_error_fails_the_job_after_one_attempt(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")

    def fail(*_args: Any, **_kwargs: Any) -> SimulationResult:
        raise RuntimeError("bad epicenter")

    monkeypatch.setattr(tasks, "run_simulation", fail)

    compute_job_id = await _submit(simulation_id)
    await _worker(queue).drain(timeout=60)

    row = await _queue_row(compute_job_id)
    # retry_on is an allowlist of transient infrastructure errors only.
    assert row["state"] == "failed"
    assert row["attempt"] == 1
    assert row["error_type"] == "RuntimeError"

    status = await repository.get_job_status(simulation_id)
    assert status["status"] == "failed"
    assert status["error"] == "Simulation failed (RuntimeError)"


@pytest.mark.asyncio
async def test_a_transient_error_is_retried_within_its_budget(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from api.core.errors import TransientInfraError

    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")

    def fail(*_args: Any, **_kwargs: Any) -> SimulationResult:
        raise TransientInfraError("storage unavailable")

    monkeypatch.setattr(tasks, "run_simulation", fail)

    compute_job_id = await _submit(simulation_id)
    await _worker(queue).drain(timeout=60)

    row = await _queue_row(compute_job_id)
    # Rescheduled, not terminal: the backoff puts the next attempt in the
    # future, so drain() returns with the job pending rather than failed.
    assert row["state"] == "pending"
    assert row["attempt"] == 1
    assert row["error_type"] == "TransientInfraError"

    status = await repository.get_job_status(simulation_id)
    assert status["status"] == "running"
    assert status["details"] == "Retrying after transient error (TransientInfraError)"


@pytest.mark.asyncio
async def test_a_job_whose_compute_row_vanished_fails_permanently(
    queue: Queue, tmp_path: Path
) -> None:
    compute_job_id = uuid.uuid4()
    async with db.acquire() as conn:
        await tasks.enqueue_simulation(conn, compute_job_id)

    await _worker(queue).drain(timeout=60)

    row = await _queue_row(compute_job_id)
    assert row["state"] == "failed"
    assert row["attempt"] == 1
    assert row["error_type"] == "PermanentFailure"


@pytest.mark.asyncio
async def test_an_undecodable_payload_fails_before_the_handler_runs(
    queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreached(*_args: Any, **_kwargs: Any) -> SimulationResult:
        pytest.fail("the handler must not run for a payload that cannot decode")

    monkeypatch.setattr(tasks, "run_simulation", unreached)

    async with db.acquire() as conn:
        await queue.enqueue(
            conn, task=RUN_SIMULATION, payload={"compute_job_id": "not-a-uuid"}
        )

    await _worker(queue).drain(timeout=60)

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT state, attempt, error_type FROM {COMPUTE_QUEUE_SCHEMA}.jobs"  # noqa: S608
        )
    assert row["state"] == "failed"
    assert row["error_type"] == "PayloadDecodeError"


@pytest.mark.asyncio
async def test_the_queue_tables_stay_out_of_the_compute_schema(queue: Queue) -> None:
    async with db.acquire() as conn:
        compute_tables = {
            record["tablename"]
            for record in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'compute'"
            )
        }
        queue_tables = {
            record["tablename"]
            for record in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = $1",
                COMPUTE_QUEUE_SCHEMA,
            )
        }

    assert compute_tables == {"jobs"}
    assert {"jobs", "job_attempts", "schema_migrations"} <= queue_tables


async def _put_on_its_last_attempt(compute_job_id: uuid.UUID) -> None:
    """Shrink the job's budget so one lease expiry exhausts it.

    Three real expiries would cost three lease durations of wall clock and
    prove nothing the first one does not: what is under test is what happens
    when recovery has no attempt left to give, not how it counts to three.
    """
    async with db.acquire() as conn:
        await conn.execute(
            f"UPDATE {COMPUTE_QUEUE_SCHEMA}.jobs SET max_attempts = 1 "  # noqa: S608
            "WHERE payload->>'compute_job_id' = $1",
            str(compute_job_id),
        )


@pytest.mark.asyncio
async def test_a_crash_that_exhausts_the_lease_budget_is_reconciled(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")

    def unreached(*_args: Any, **_kwargs: Any) -> SimulationResult:
        # Lease recovery is a SQL update. It never calls the handler back, so
        # nothing in run_simulation_task gets the chance to raise or to report.
        pytest.fail("recovery must not re-invoke the simulation handler")

    monkeypatch.setattr(tasks, "run_simulation", unreached)

    compute_job_id = await _submit(simulation_id)
    await _put_on_its_last_attempt(compute_job_id)

    # A worker claims the job and writes compute.jobs = running exactly as
    # run_simulation_task's first statement does -- and then its process dies.
    # A sub-second lease is how rqueue models a holder that never comes back:
    # no heartbeat renews it and no finalizing write is ever made.
    async with db.acquire() as conn:
        claimed = await queue.storage.claim(
            conn,
            queue=queue.name,
            worker_id="crashed-worker",
            tasks=[RUN_SIMULATION],
            limit=1,
            lease_seconds=0.2,
        )
        assert len(claimed) == 1
        await repository.mark_started(conn, compute_job_id, uuid.UUID(simulation_id), 1)

    await asyncio.sleep(0.4)
    # Any live worker's poll recovers the expired lease; drain() is one poll.
    await _worker(queue).drain(timeout=60)

    row = await _queue_row(compute_job_id)
    assert row["state"] == "failed"
    assert row["error_type"] == "LeaseExpired"

    # The gap this pass exists to close: the queue has given up, and nothing
    # told compute.jobs, which would otherwise read "running" forever.
    assert (await repository.get_job_status(simulation_id))["status"] == "running"

    await tasks.reconcile_terminal_jobs(grace=timedelta(0))

    status = await repository.get_job_status(simulation_id)
    assert status["status"] == "failed"
    assert status["error"] == (
        "Simulation stopped without reporting a result; "
        "status reconciled from the task queue (LeaseExpired)"
    )
    assert status["finished_at"] is not None

    # Reconciled once, never again: the second pass finds nothing to do.
    assert (
        await repository.reconcile_terminal_jobs(
            queue_schema=queue.schema,
            queue_name=queue.name,
            task=RUN_SIMULATION,
            cutoff=datetime.now().astimezone(),
        )
        == []
    )


@pytest.mark.asyncio
async def test_reconciliation_leaves_a_finished_job_alone(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")
    (tmp_path / "jobs" / simulation_id).mkdir(parents=True)
    monkeypatch.setattr(
        tasks,
        "run_simulation",
        lambda _data, work_dir, **_kwargs: _result(work_dir),
    )
    monkeypatch.setattr(
        output_store,
        "upload_simulation_result",
        lambda **_kwargs: ("results", "simulations/x/metadata.json"),
    )

    compute_job_id = await _submit(simulation_id)
    await _worker(queue).drain(timeout=60)
    assert (await repository.get_job_status(simulation_id))["status"] == "completed"

    # A run that reported its own outcome is off limits, whatever the queue
    # row next to it says. Nothing here is stuck, so nothing is reconciled.
    async with db.acquire() as conn:
        await conn.execute(
            f"UPDATE {COMPUTE_QUEUE_SCHEMA}.jobs "  # noqa: S608
            "SET state = 'failed', error_type = 'LeaseExpired' "
            "WHERE payload->>'compute_job_id' = $1",
            str(compute_job_id),
        )
    await tasks.reconcile_terminal_jobs(grace=timedelta(0))

    assert (await repository.get_job_status(simulation_id))["status"] == "completed"


@pytest.mark.asyncio
async def test_a_transient_finalization_failure_is_reported_as_retrying(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")
    (tmp_path / "jobs" / simulation_id).mkdir(parents=True)
    monkeypatch.setattr(
        tasks, "run_simulation", lambda _data, work_dir, **_kwargs: _result(work_dir)
    )

    def minio_is_down(**_kwargs: Any) -> tuple[str, str]:
        raise TransientInfraError("output upload failed")

    monkeypatch.setattr(output_store, "upload_simulation_result", minio_is_down)

    compute_job_id = await _submit(simulation_id)
    await _worker(queue).drain(timeout=60)

    row = await _queue_row(compute_job_id)
    assert row["state"] == "pending"
    assert row["error_type"] == "TransientInfraError"

    # The kernel succeeded and the upload did not, so the failure lands in
    # complete_job -- outside the block that used to be the only caller of
    # _record_failure. crash_recovery_e2e.sh scenario 3 watches for exactly
    # this text while MinIO is stopped.
    status = await repository.get_job_status(simulation_id)
    assert status["status"] == "running"
    assert status["details"] == "Retrying after transient error (TransientInfraError)"
    # The workspace survives, so the retry resumes rather than recomputing.
    assert (tmp_path / "jobs" / simulation_id).exists()


@pytest.mark.asyncio
async def test_a_redelivered_completed_job_is_not_run_again(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")
    work_dir = tmp_path / "jobs" / simulation_id
    work_dir.mkdir(parents=True)
    monkeypatch.setattr(
        tasks, "run_simulation", lambda _data, wd, **_kwargs: _result(wd)
    )
    monkeypatch.setattr(
        output_store,
        "upload_simulation_result",
        lambda **_kwargs: ("results", "simulations/x/metadata.json"),
    )

    compute_job_id = await _submit(simulation_id)
    await _worker(queue).drain(timeout=60)
    finished = await repository.get_job_status(simulation_id)
    assert finished["status"] == "completed"

    # rqueue is at-least-once: a worker that died after complete_job committed
    # but before rqueue finalized gets the job again. Put the queue row back
    # the way that leaves it, and leave a workspace behind too.
    work_dir.mkdir(parents=True, exist_ok=True)
    async with db.acquire() as conn, conn.transaction():
        queue_job_id = await conn.fetchval(
            f"UPDATE {COMPUTE_QUEUE_SCHEMA}.jobs "  # noqa: S608
            "SET state = 'pending', finished_at = NULL, attempt = 0 "
            "WHERE payload->>'compute_job_id' = $1 RETURNING id",
            str(compute_job_id),
        )
        # The attempt record is closed only at finalization, which is exactly
        # what the dead worker never reached.
        await conn.execute(
            f"DELETE FROM {COMPUTE_QUEUE_SCHEMA}.job_attempts "  # noqa: S608
            "WHERE job_id = $1",
            queue_job_id,
        )

    def unreached(*_args: Any, **_kwargs: Any) -> SimulationResult:
        pytest.fail("a completed job must not be simulated again")

    monkeypatch.setattr(tasks, "run_simulation", unreached)
    await _worker(queue).drain(timeout=60)

    # Not re-run, and -- the part that actually hurt -- mark_started did not
    # flip a finished job back to `running` for everyone watching.
    redelivered = await repository.get_job_status(simulation_id)
    assert redelivered["status"] == "completed"
    assert redelivered["finished_at"] == finished["finished_at"]
    assert (await _queue_row(compute_job_id))["state"] == "succeeded"
    # The step the dead attempt may never have reached.
    assert not work_dir.exists()


@pytest.mark.asyncio
async def test_one_unreadable_payload_does_not_abort_the_reconciliation_pass(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")

    compute_job_id = await _submit(simulation_id)
    await _put_on_its_last_attempt(compute_job_id)
    async with db.acquire() as conn:
        claimed = await queue.storage.claim(
            conn,
            queue=queue.name,
            worker_id="crashed-worker",
            tasks=[RUN_SIMULATION],
            limit=1,
            lease_seconds=0.2,
        )
        assert len(claimed) == 1
        await repository.mark_started(conn, compute_job_id, uuid.UUID(simulation_id), 1)

        # A terminal queue row whose payload is not a uuid. Casting it aborts
        # the whole statement, so without a guard this one row would silently
        # un-reconcile every genuinely stuck job beside it.
        await conn.execute(
            f"""
            INSERT INTO {COMPUTE_QUEUE_SCHEMA}.jobs
                (queue, task, payload, state, attempt, max_attempts, finished_at)
            VALUES ($1, $2, '{{"compute_job_id": "not-a-uuid"}}'::jsonb,
                    'failed', 1, 1, now())
            """,  # noqa: S608
            queue.name,
            RUN_SIMULATION,
        )

    await asyncio.sleep(0.4)
    await _worker(queue).drain(timeout=60)

    await tasks.reconcile_terminal_jobs(grace=timedelta(0))

    assert (await repository.get_job_status(simulation_id))["status"] == "failed"


@pytest.mark.asyncio
async def test_a_stale_attempt_cannot_undo_a_reconciled_failure(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The exposure reconciliation itself had, closed in the same statement.

    A thread abandoned by attempt N keeps running after its coroutine is gone.
    If reconciliation has already marked the job failed, a stale progress write
    would set it back to `running` -- silently undoing the repair. The write is
    still made by the row's *owner*, so nothing but the status predicate on the
    UPDATE itself can refuse it.
    """
    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")

    compute_job_id = await _submit(simulation_id)
    await _put_on_its_last_attempt(compute_job_id)

    async with db.acquire() as conn:
        claimed = await queue.storage.claim(
            conn,
            queue=queue.name,
            worker_id="crashed-worker",
            tasks=[RUN_SIMULATION],
            limit=1,
            lease_seconds=0.2,
        )
        assert len(claimed) == 1
        attempt = claimed[0].job.attempt
        assert await repository.mark_started(
            conn, compute_job_id, uuid.UUID(simulation_id), attempt
        )

    await asyncio.sleep(0.4)
    await _worker(queue).drain(timeout=60)
    await tasks.reconcile_terminal_jobs(grace=timedelta(0))
    assert (await repository.get_job_status(simulation_id))["status"] == "failed"

    # The kernel thread from that attempt is still alive and still owns the row.
    async with db.acquire() as conn:
        written = await repository.record_progress(
            conn,
            compute_job_id,
            uuid.UUID(simulation_id),
            "Processing tsunami",
            {"step": "tsunami", "step_index": 3, "total_steps": 8},
            attempt,
        )

    assert written is False
    status = await repository.get_job_status(simulation_id)
    assert status["status"] == "failed"
    assert status["step"] != "tsunami"
    assert status["error"] == (
        "Simulation stopped without reporting a result; "
        "status reconciled from the task queue (LeaseExpired)"
    )


@pytest.mark.asyncio
async def test_a_superseded_attempt_cannot_write_over_the_newer_one(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")
    compute_job_id = await _submit(simulation_id)
    job_uuid = uuid.UUID(simulation_id)

    async with db.acquire() as conn:
        assert await repository.mark_started(conn, compute_job_id, job_uuid, 1)
        # A newer attempt takes the row over, as it does after lease recovery.
        assert await repository.mark_started(conn, compute_job_id, job_uuid, 2)
        assert await repository.record_progress(
            conn, compute_job_id, job_uuid, "Processing maxola", {"step": "maxola"}, 2
        )

        # Attempt 1's thread is still running and still holds the loop.
        assert not await repository.record_progress(
            conn, compute_job_id, job_uuid, "Processing tsunami", {"step": "tsunami"}, 1
        )
        # And it cannot take the row back either.
        assert not await repository.mark_started(conn, compute_job_id, job_uuid, 1)

    status = await repository.get_job_status(simulation_id)
    assert status["step"] == "maxola"
    assert status["details"] == "Processing maxola"


@pytest.mark.asyncio
async def test_an_operator_retry_of_a_failed_job_can_still_start(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Why `mark_started` refuses only COMPLETED, never FAILED.

    `rqueue.Admin.retry_job` is the documented way an operator restarts a job
    rqueue considers terminally failed, and it works by putting the same row
    back to `pending` with a raised budget -- so the retry arrives as an
    ordinary claim of the same job, running the same handler. If `mark_started`
    refused a `failed` compute row the way it refuses a `completed` one, that
    retry would run a whole simulation whose every write was rejected.
    """
    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")

    def fail(*_args: Any, **_kwargs: Any) -> SimulationResult:
        raise RuntimeError("bad epicenter")

    monkeypatch.setattr(tasks, "run_simulation", fail)
    compute_job_id = await _submit(simulation_id)
    await _worker(queue).drain(timeout=60)

    failed_row = await _queue_row(compute_job_id)
    assert failed_row["state"] == "failed"
    assert (await repository.get_job_status(simulation_id))["status"] == "failed"

    # The operator retry, through rqueue's own public API.
    (tmp_path / "jobs" / simulation_id).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        tasks, "run_simulation", lambda _data, wd, **_kwargs: _result(wd)
    )
    monkeypatch.setattr(
        output_store,
        "upload_simulation_result",
        lambda **_kwargs: ("results", "simulations/x/metadata.json"),
    )
    retried = await Admin(queue.pool, schema=queue.schema).retry_job(failed_row["id"])
    assert retried.state == "pending"

    await _worker(queue).drain(timeout=60)

    assert (await _queue_row(compute_job_id))["state"] == "succeeded"
    assert (await repository.get_job_status(simulation_id))["status"] == "completed"


@pytest.mark.asyncio
async def test_a_stand_down_is_not_counted_as_a_failed_job(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A refused write must not look like a broken simulation to rqueue."""
    simulation_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks, "JOBS_DIR", tmp_path / "jobs")
    compute_job_id = await _submit(simulation_id)

    def superseded(*_args: Any, on_progress: Any, **_kwargs: Any) -> SimulationResult:
        # A newer attempt takes the row over while this kernel is running.
        asyncio.run(_take_over(compute_job_id, uuid.UUID(simulation_id)))
        on_progress("Processing tsunami", {"step": "tsunami"})
        pytest.fail("the kernel must not continue past a refused write")

    monkeypatch.setattr(tasks, "run_simulation", superseded)
    await _worker(queue).drain(timeout=60)

    row = await _queue_row(compute_job_id)
    # Not `failed`: standing down is the fence working, and rqueue's failure
    # accounting has to keep meaning genuine failures.
    assert row["state"] == "cancelled"
    assert row["error_type"] == "Cancelled"
    assert "no longer owns this job" in row["error_message"]

    # And reconciliation treats a cancelled queue row as the queue giving up,
    # so compute.jobs cannot be left reading `running` forever either.
    await tasks.reconcile_terminal_jobs(grace=timedelta(0))
    assert (await repository.get_job_status(simulation_id))["status"] == "failed"


async def _take_over(compute_job_id: uuid.UUID, simulation_id: uuid.UUID) -> None:
    """Claim the compute row for a later attempt, from off the loop."""
    # The queue fixture points this at the test's disposable database.
    connection = await asyncpg.connect(db_module.COMPUTE_DATABASE_URL)
    try:
        await connection.execute(
            "UPDATE compute.jobs SET owner_attempt = 99 WHERE id = $1", compute_job_id
        )
    finally:
        await connection.close()
