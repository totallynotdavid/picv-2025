"""Everything that reads or writes compute.jobs.

Split out of the old monolithic jobs.py so the queue tasks (tasks.py) hold
only orchestration and this module holds only persistence. Every write that
changes what a watcher would see ends in a NOTIFY on the job's channel, so
progress is pushed to SSE clients instead of polled for.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, cast

import psycopg
from psycopg.types.json import Jsonb

from api.core.db import JobRow, connect, notify_channel, pooled
from api.core.storage import artifact_store, iso
from tsdhn.domain import EarthquakeInput, JobStatus
from tsdhn.engine import SimulationResult
from tsdhn.utils.file_utils import sanitize_for_log

__all__ = [
    "ArtifactRef",
    "complete_job",
    "create_or_get_job",
    "fetch_by_id",
    "get_artifacts",
    "get_job_status",
    "is_database_connected",
    "mark_started",
    "record_failure",
    "record_progress",
]

logger = logging.getLogger(__name__)

ArtifactRef = dict[str, str]

# compute.jobs.details and .error reach browsers through the control plane,
# so neither string may carry internal detail.
FAILED_JOB_DETAILS = "Pipeline failed - check error logs"

_COLUMNS = """
  id, external_id, status, input_params, details, step, step_index,
  total_steps, calculation, travel_times, artifacts, result_bucket,
  result_key, error, created_at, updated_at, started_at, finished_at
"""


def _sql(template: str) -> str:
    """Splice the shared column list into a query template.

    The only place query text is composed. `_COLUMNS` is a module-level
    literal; every value in these queries travels through a %s placeholder.
    """
    return template.format(columns=_COLUMNS)


SELECT_BY_EXTERNAL_ID = _sql(
    "SELECT {columns} FROM compute.jobs WHERE external_id = %s"
)
SELECT_BY_ID = _sql("SELECT {columns} FROM compute.jobs WHERE id = %s")

INSERT_JOB_SQL = _sql(
    """
    INSERT INTO compute.jobs (id, external_id, status, input_params, details)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (external_id) DO NOTHING
    RETURNING {columns}
    """
)


def as_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value, version=4)


def _model_dump(data: EarthquakeInput) -> dict[str, Any]:
    dumped: object = data.model_dump(mode="json")
    if not isinstance(dumped, dict):
        raise TypeError("EarthquakeInput did not dump to a JSON object")
    return cast(dict[str, Any], dumped)


def _notify(conn: psycopg.Connection[JobRow], external_id: uuid.UUID) -> None:
    """Wake anyone streaming this job. Delivered on commit, so a listener
    never sees a notification for a row state that isn't visible yet."""
    conn.execute(f"NOTIFY {notify_channel(external_id)}")


def status_from_row(row: JobRow) -> dict[str, Any]:
    status = str(row["status"])
    artifacts = row["artifacts"] or []
    return {
        "compute_job_id": str(row["id"]),
        "status": status,
        "details": row["details"],
        "step": row["step"],
        "step_index": row["step_index"],
        "total_steps": row["total_steps"],
        "calculation": row["calculation"],
        "travel_times": row["travel_times"],
        "result_bucket": row["result_bucket"],
        "result_key": row["result_key"],
        "error": row["error"],
        "created_at": iso(row["created_at"]),
        "started_at": iso(row["started_at"]),
        "finished_at": iso(row["finished_at"]),
        "artifacts": [a["name"] for a in artifacts],
    }


def _public_error(e: Exception, step: str | None) -> str:
    """The user-facing error stored in compute.jobs.error.

    Raw exception messages embed server filesystem paths (jobs dir, model
    locations), so only the exception class and failed step are exposed;
    the full traceback stays in the worker logs.
    """
    if step:
        return f"Simulation failed at step '{step}' ({type(e).__name__})"
    return f"Simulation failed ({type(e).__name__})"


def fetch_by_id(conn: psycopg.Connection[JobRow], job_id: uuid.UUID) -> JobRow | None:
    return conn.execute(SELECT_BY_ID, [job_id]).fetchone()


def create_or_get_job(
    *, data: EarthquakeInput, external_id: str, defer: Any
) -> dict[str, Any]:
    """Insert a job and enqueue it, atomically.

    `defer` is called with the open connection and the new compute job id;
    it is passed in rather than imported so this module stays free of any
    queue dependency. The insert and the enqueue commit together, so a job
    row can never exist without its queue entry.
    """
    app_job_id = as_uuid(external_id)
    input_params = _model_dump(data)

    with pooled() as conn, conn.transaction():
        compute_job_id = uuid.uuid4()
        inserted = conn.execute(
            INSERT_JOB_SQL,
            [
                compute_job_id,
                app_job_id,
                JobStatus.QUEUED.value,
                Jsonb(input_params),
                "Queued for simulation worker",
            ],
        ).fetchone()

        if inserted is None:
            existing = conn.execute(SELECT_BY_EXTERNAL_ID, [app_job_id]).fetchone()
            if existing is None:
                raise RuntimeError("Compute job was not persisted")
            if existing["input_params"] != input_params:
                raise ValueError("Job id already exists with different input")
            return status_from_row(existing)

        defer(conn, compute_job_id)
        return status_from_row(inserted)


def get_job_status(app_job_id: str) -> dict[str, Any]:
    try:
        external_id = as_uuid(app_job_id)
        with pooled() as conn:
            row = conn.execute(SELECT_BY_EXTERNAL_ID, [external_id]).fetchone()
    except Exception as e:
        logger.error("Job lookup failed for %s: %s", sanitize_for_log(app_job_id), e)
        raise ValueError("Invalid or unknown job ID") from e

    if row is None:
        raise ValueError("Invalid or unknown job ID")
    return status_from_row(row)


def get_artifacts(app_job_id: str) -> list[ArtifactRef]:
    """The artifact manifest recorded at completion.

    Read from Postgres rather than by listing the bucket: the manifest is
    written in the same transaction that marks the job COMPLETED, so it
    cannot disagree with the job's status, and presigning needs no round
    trip to MinIO.
    """
    external_id = as_uuid(app_job_id)
    with pooled() as conn:
        row = conn.execute(
            "SELECT status, artifacts FROM compute.jobs WHERE external_id = %s",
            [external_id],
        ).fetchone()
    if row is None:
        raise ValueError("Invalid or unknown job ID")
    if row["status"] != JobStatus.COMPLETED.value:
        return []
    return cast(list[ArtifactRef], row["artifacts"] or [])


def is_database_connected() -> bool:
    try:
        with pooled() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def mark_started(
    conn: psycopg.Connection[JobRow], job_uuid: uuid.UUID, external_id: uuid.UUID
) -> None:
    conn.execute(
        """
        UPDATE compute.jobs
        SET status = %s, details = %s,
            started_at = COALESCE(started_at, now()), updated_at = now()
        WHERE id = %s
        """,
        [JobStatus.RUNNING.value, "Simulation worker started", job_uuid],
    )
    _notify(conn, external_id)
    conn.commit()


def record_progress(
    conn: psycopg.Connection[JobRow],
    job_uuid: uuid.UUID,
    external_id: uuid.UUID,
    message: str,
    details: dict[str, Any],
) -> None:
    """Persist one `SimulationEngine.run` progress callback."""
    conn.execute(
        """
        UPDATE compute.jobs
        SET status = %s,
            details = %s,
            step = COALESCE(%s, step),
            step_index = COALESCE(%s, step_index),
            total_steps = COALESCE(%s, total_steps),
            calculation = COALESCE(%s, calculation),
            travel_times = COALESCE(%s, travel_times),
            updated_at = now()
        WHERE id = %s
        """,
        [
            JobStatus.RUNNING.value,
            message,
            details.get("step"),
            details.get("step_index"),
            details.get("total_steps"),
            Jsonb(details["calculation"]) if "calculation" in details else None,
            Jsonb(details["travel_times"]) if "travel_times" in details else None,
            job_uuid,
        ],
    )
    _notify(conn, external_id)
    conn.commit()


def record_failure(
    conn: psycopg.Connection[JobRow],
    job_uuid: uuid.UUID,
    external_id: uuid.UUID,
    exc: Exception,
    *,
    step: str | None,
    will_retry: bool,
) -> None:
    """Record a failed run.

    When the exception is about to be retried this only updates `details`
    and leaves the status RUNNING, so an in-flight retry does not look
    terminal to anyone watching.
    """
    logger.exception("Simulation failed for compute job %s", job_uuid)
    if will_retry:
        conn.execute(
            "UPDATE compute.jobs SET details = %s, updated_at = now() WHERE id = %s",
            [f"Retrying after transient error ({type(exc).__name__})", job_uuid],
        )
    else:
        conn.execute(
            """
            UPDATE compute.jobs
            SET status = %s, details = %s, error = %s,
                finished_at = now(), updated_at = now()
            WHERE id = %s
            """,
            [
                JobStatus.FAILED.value,
                FAILED_JOB_DETAILS,
                _public_error(exc, step),
                job_uuid,
            ],
        )
    _notify(conn, external_id)
    conn.commit()


def fail_job(
    conn: psycopg.Connection[JobRow],
    job_uuid: uuid.UUID,
    external_id: uuid.UUID,
    error: str,
) -> None:
    conn.execute(
        """
        UPDATE compute.jobs
        SET status = %s, details = %s, error = %s,
            finished_at = now(), updated_at = now()
        WHERE id = %s
        """,
        [JobStatus.FAILED.value, FAILED_JOB_DETAILS, error, job_uuid],
    )
    _notify(conn, external_id)
    conn.commit()


def complete_job(
    conn: psycopg.Connection[JobRow], row: JobRow, result: SimulationResult
) -> None:
    """Upload the bundle to MinIO, then mark the job COMPLETED.

    The artifact manifest is stored on the row in the same statement that
    sets status=COMPLETED, so `artifacts_available` is not a separate fact
    that can drift from the objects that actually exist.
    """
    now = datetime.now().astimezone()
    app_job_id = str(row["external_id"])
    compute_job_id = str(row["id"])
    calculation = result.calculation.model_dump(mode="json")
    travel_times = result.travel_times.model_dump(mode="json")

    artifacts: list[ArtifactRef] = [
        {
            "name": artifact.name,
            "key": f"simulations/{app_job_id}/artifacts/{artifact.path.name}",
            "filename": artifact.path.name,
            "content_type": artifact.content_type,
        }
        for artifact in result.bundle.artifacts
    ]

    metadata = {
        "app_job_id": app_job_id,
        "compute_job_id": compute_job_id,
        "status": JobStatus.COMPLETED.value,
        "created_at": iso(row["created_at"]),
        "started_at": iso(row["started_at"]),
        "finished_at": now.isoformat(),
        "calculation": calculation,
        "travel_times": travel_times,
        "artifacts": artifacts,
    }
    bucket, metadata_key = artifact_store.upload_simulation_result(
        app_job_id=app_job_id,
        compute_job_id=compute_job_id,
        bundle=result.bundle,
        metadata=metadata,
    )

    conn.execute(
        """
        UPDATE compute.jobs
        SET status = %s, details = %s, calculation = %s, travel_times = %s,
            artifacts = %s, result_bucket = %s, result_key = %s, error = NULL,
            finished_at = %s, updated_at = now()
        WHERE id = %s
        """,
        [
            JobStatus.COMPLETED.value,
            "Simulation completed successfully",
            Jsonb(calculation),
            Jsonb(travel_times),
            Jsonb(artifacts),
            bucket,
            metadata_key,
            now,
            row["id"],
        ],
    )
    _notify(conn, row["external_id"])
    conn.commit()


def open_worker_connection() -> psycopg.Connection[JobRow]:
    return connect()
