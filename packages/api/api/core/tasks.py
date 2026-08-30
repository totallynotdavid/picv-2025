"""The compute plane's queue tasks.

One task runs one whole simulation. An earlier design split the pipeline
into a chain of one queue job per step, so a crash cost only the current
step -- but the resume it bought already exists a layer down, on disk:
`is_step_complete()` skips finished steps and the tsunami kernel restarts
from its own checkpoint. The chain only added a way to *reach* that resume,
at the price of cross-hop attempt tracking, supersede detection and a
requirement that every worker see the same filesystem. Re-running a
completed step now costs a marker read and a few stat calls, against a
run measured in tens of minutes.
"""

import logging
import shutil
import uuid
from datetime import datetime, timedelta
from typing import Any

import psycopg
from procrastinate import JobContext, RetryStrategy
from procrastinate import exceptions as procrastinate_exceptions
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
    "reap_stalled_jobs_task",
    "run_simulation_task",
    "sweep_abandoned_work_dirs_task",
]

logger = logging.getLogger(__name__)

# Automatic retry is deliberately narrow: only TransientInfraError (raised
# at DB-reconnect and MinIO-upload boundaries) is retried. Domain errors
# (bad epicenter, missing model data, a step failure) fail immediately --
# retrying those would just fail identically and waste the wait.
MAX_ATTEMPTS = 3
TRANSIENT_RETRY = RetryStrategy(
    max_attempts=MAX_ATTEMPTS,
    exponential_wait=15,
    retry_exceptions=(TransientInfraError,),
)

# A worker's heartbeat updates every 10s (procrastinate default) regardless
# of what it is running, so this only needs to clear that interval plus
# jitter. It is unrelated to how long a simulation takes -- which is the
# whole reason stalled-job detection keys off the heartbeat and not job
# runtime, and why the tsunami step's long silent stretches never trip it.
STALLED_HEARTBEAT_SECONDS = 90

# Delay before a crash-requeued job becomes eligible again. Dampens a
# thundering herd when one node dying takes out several jobs at once.
CRASH_REQUEUE_DELAY_SECONDS = 30

CRASH_BUDGET_EXHAUSTED_ERROR = (
    "Simulation worker stopped responding mid-run (retry budget exhausted)"
)

# How long a terminally-FAILED job's work_dir (including any tsunami
# checkpoint) survives, in case it is still wanted for local inspection or
# a manual resume.
WORK_DIR_TTL = timedelta(hours=24)


def enqueue_simulation(
    conn: psycopg.Connection[JobRow], compute_job_id: uuid.UUID
) -> None:
    """Defer the simulation on the caller's connection, so the queue entry
    commits with the compute.jobs row it belongs to.

    Safe here because this only ever runs in the API process, which never
    opens procrastinate's async pool. The worker cannot do this: with the
    async pool open, `.configure(connection=<sync conn>)` routes through
    the async execute path and fails on a connection that was never async.
    """
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

    # A dedicated connection, not a pooled one: this is held across a
    # multi-minute run and would otherwise pin a pool slot the API needs.
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
                # An existing work_dir means a previous attempt got part of
                # the way through; keep its step outputs and checkpoint.
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


def _current_step(conn: psycopg.Connection[JobRow], job_uuid: uuid.UUID) -> str | None:
    row = conn.execute(
        "SELECT step FROM compute.jobs WHERE id = %s", [job_uuid]
    ).fetchone()
    return str(row["step"]) if row and row["step"] else None


@app.periodic(cron="*/2 * * * *")
@app.task(name="api.reap_stalled_jobs", queue=PROCRASTINATE_QUEUE)
async def reap_stalled_jobs_task(timestamp: int) -> None:
    """Requeue jobs whose worker's heartbeat went stale -- the process was
    most likely OOM-killed or crashed mid-run, which leaves the queue row
    stuck in `doing` with nothing to raise an exception on its behalf.

    With one queue job per simulation there is no chain to reason about:
    a stalled job is either retryable or out of budget. Requeuing reuses
    the same job id and kwargs, so the run resumes through its on-disk
    checkpoint. Only effective with >=2 worker replicas: if the only
    worker dies, nothing is left to run this task either.
    """
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

        if job.attempts < MAX_ATTEMPTS:
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
    """Delete work_dirs for terminally-FAILED jobs older than WORK_DIR_TTL.

    A resumable job's work_dir is never touched: only rows already marked
    FAILED are candidates, and that status is set only once the retry
    budget is used up.
    """
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
