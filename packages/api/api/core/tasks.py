"""Queue tasks for simulation runs and worker maintenance."""

import logging
import shutil
import uuid
from datetime import datetime, timedelta
from typing import Any, Literal

import psycopg
from procrastinate import JobContext, RetryStrategy
from procrastinate import exceptions as procrastinate_exceptions
from procrastinate.jobs import Job as ProcrastinateJob
from procrastinate.jobs import Status as ProcrastinateStatus

from api.core import repository
from api.core.db import JobRow, connect, pooled
from api.core.errors import TransientInfraError
from api.core.procrastinate_app import app
from api.core.settings import JOBS_DIR, PROCRASTINATE_QUEUE
from tsdhn.domain import EarthquakeInput, JobStatus
from tsdhn.engine import run_simulation
from tsdhn.utils.file_utils import sanitize_for_log

__all__ = [
    "enqueue_simulation",
    "reap_action",
    "reap_stalled_jobs_task",
    "run_simulation_task",
    "sweep_abandoned_work_dirs_task",
]

type ReapAction = Literal["retry", "exhausted"]

logger = logging.getLogger(__name__)

# Retry only infrastructure failures. Domain and pipeline errors are terminal.
MAX_ATTEMPTS = 3
TRANSIENT_RETRY = RetryStrategy(
    max_attempts=MAX_ATTEMPTS,
    exponential_wait=15,
    retry_exceptions=(TransientInfraError,),
)

# This is a heartbeat timeout, not a simulation runtime limit.
STALLED_HEARTBEAT_SECONDS = 90

# Delay requeued work so several jobs do not start at once after a worker crash.
CRASH_REQUEUE_DELAY_SECONDS = 30

CRASH_BUDGET_EXHAUSTED_ERROR = (
    "Simulation worker stopped responding mid-run (retry budget exhausted)"
)

# Keep failed workspaces for local inspection and manual recovery.
WORK_DIR_TTL = timedelta(hours=24)


def enqueue_simulation(
    conn: psycopg.Connection[JobRow], compute_job_id: uuid.UUID
) -> None:
    """Queue the task on `conn` so it commits with the job row."""
    run_simulation_task.configure(
        connection=conn,
        queue=PROCRASTINATE_QUEUE,
        queueing_lock=f"simulation:{compute_job_id}",
        lock=f"compute-job:{compute_job_id}",
    ).defer(compute_job_id=str(compute_job_id))


@app.task(
    name="api.run_simulation",
    queue=PROCRASTINATE_QUEUE,
    pass_context=True,
    retry=TRANSIENT_RETRY,
)
def run_simulation_task(context: JobContext, compute_job_id: str) -> None:
    """Run one simulation end to end, streaming progress into compute.jobs."""
    job_uuid = repository.as_uuid(compute_job_id)

    # A simulation keeps its connection for the duration of the run.
    with connect() as conn:
        row = repository.fetch_by_id(conn, job_uuid)
        if row is None:
            raise RuntimeError(f"Unknown compute job {compute_job_id}")

        external_id: uuid.UUID = row["external_id"]
        work_dir = JOBS_DIR / str(external_id)
        data = EarthquakeInput(**row["input_params"])

        repository.mark_started(conn, job_uuid, external_id)

        def on_progress(message: str, details: dict[str, Any]) -> None:
            repository.record_progress(conn, job_uuid, external_id, message, details)

        try:
            result = run_simulation(
                data,
                work_dir,
                # Keep outputs and checkpoints when a retry has a work directory.
                resume=work_dir.exists(),
                on_progress=on_progress,
            )
            repository.complete_job(conn, row, result)
        except Exception as e:
            will_retry = (
                isinstance(e, TransientInfraError)
                and context.job.attempts < MAX_ATTEMPTS
            )
            repository.record_failure(
                conn,
                job_uuid,
                external_id,
                e,
                step=_current_step(conn, job_uuid),
                will_retry=will_retry,
            )
            raise
        else:
            shutil.rmtree(work_dir, ignore_errors=True)


def reap_action(job: ProcrastinateJob) -> ReapAction:
    """Return whether a stalled queue job can be retried."""
    return "retry" if job.attempts < MAX_ATTEMPTS else "exhausted"


def _current_step(conn: psycopg.Connection[JobRow], job_uuid: uuid.UUID) -> str | None:
    row = conn.execute(
        "SELECT step FROM compute.jobs WHERE id = %s", [job_uuid]
    ).fetchone()
    return str(row["step"]) if row and row["step"] else None


@app.periodic(cron="*/2 * * * *")
@app.task(name="api.reap_stalled_jobs", queue=PROCRASTINATE_QUEUE)
async def reap_stalled_jobs_task(timestamp: int) -> None:
    """Requeue work whose Procrastinate heartbeat has expired."""
    stalled = list(
        await app.job_manager.get_stalled_jobs(
            seconds_since_heartbeat=STALLED_HEARTBEAT_SECONDS
        )
    )
    if not stalled:
        return

    retry_at = datetime.now().astimezone() + timedelta(
        seconds=CRASH_REQUEUE_DELAY_SECONDS
    )

    for job in stalled:
        if job.id is None:  # pragma: no cover - persisted jobs always have an id
            continue
        compute_job_id = str(job.task_kwargs.get("compute_job_id", ""))
        if not compute_job_id:
            continue

        if reap_action(job) == "retry":
            logger.warning(
                "Requeuing stalled job %s (compute job %s): heartbeat went stale",
                job.id,
                sanitize_for_log(compute_job_id),
            )
            try:
                await app.job_manager.retry_job_by_id_async(
                    job_id=job.id, retry_at=retry_at
                )
            except procrastinate_exceptions.ConnectorException:
                logger.info("Stalled job %s resolved before requeue", job.id)
            continue

        logger.warning(
            "Retry budget exhausted for compute job %s: marking FAILED",
            sanitize_for_log(compute_job_id),
        )
        _fail_exhausted(compute_job_id)
        try:
            await app.job_manager.finish_job_by_id_async(
                job_id=job.id, status=ProcrastinateStatus.FAILED, delete_job=False
            )
        except procrastinate_exceptions.ConnectorException:
            logger.info("Stalled job %s was already resolved", job.id)


def _fail_exhausted(compute_job_id: str) -> None:
    job_uuid = repository.as_uuid(compute_job_id)
    with pooled() as conn:
        row = repository.fetch_by_id(conn, job_uuid)
        if row is None or row["status"] in {
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
        }:
            return
        repository.fail_job(
            conn, job_uuid, row["external_id"], CRASH_BUDGET_EXHAUSTED_ERROR
        )


@app.periodic(cron="0 * * * *")
@app.task(name="api.sweep_abandoned_work_dirs", queue=PROCRASTINATE_QUEUE)
def sweep_abandoned_work_dirs_task(timestamp: int) -> None:
    """Remove old workspaces for failed jobs."""
    cutoff = datetime.now().astimezone() - WORK_DIR_TTL
    with pooled() as conn:
        rows = conn.execute(
            """
            SELECT external_id FROM compute.jobs
            WHERE status = %s AND finished_at IS NOT NULL AND finished_at < %s
            """,
            [JobStatus.FAILED.value, cutoff],
        ).fetchall()

    for row in rows:
        shutil.rmtree(JOBS_DIR / str(row["external_id"]), ignore_errors=True)
