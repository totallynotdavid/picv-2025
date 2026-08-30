"""Read and write the compute service's job state."""

import logging
import uuid
from datetime import datetime
from typing import Any, cast

import psycopg
from psycopg.types.json import Jsonb

from api.core.db import JobRow, connect, notify_channel, pooled
from api.core.storage import iso, output_store
from tsdhn.domain import EarthquakeInput, JobStatus
from tsdhn.engine import SimulationResult
from tsdhn.utils.file_utils import sanitize_for_log

__all__ = [
    "StoredOutput",
    "complete_job",
    "create_or_get_job",
    "fetch_by_id",
    "get_current_step",
    "get_job_status",
    "get_outputs",
    "is_database_connected",
    "list_abandoned_work_dirs",
    "mark_started",
    "record_failure",
    "record_progress",
]

logger = logging.getLogger(__name__)

StoredOutput = dict[str, str]

# These details are safe to show to researchers.
FAILED_JOB_DETAILS = "Pipeline failed - check error logs"

_COLUMNS = """
  id, simulation_id, status, input_params, details, step, step_index,
  total_steps, calculation, travel_times, outputs, error, created_at,
  updated_at, started_at, finished_at
"""


def _sql(template: str) -> str:
    return template.format(columns=_COLUMNS)


SELECT_BY_SIMULATION_ID = _sql(
    "SELECT {columns} FROM compute.jobs WHERE simulation_id = %s"
)
SELECT_BY_ID = _sql("SELECT {columns} FROM compute.jobs WHERE id = %s")

INSERT_JOB_SQL = _sql(
    """
    INSERT INTO compute.jobs (id, simulation_id, status, input_params, details)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (simulation_id) DO NOTHING
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


def _notify(conn: psycopg.Connection[JobRow], simulation_id: uuid.UUID) -> None:
    """PostgreSQL delivers the notification when the update commits."""
    conn.execute(f"NOTIFY {notify_channel(simulation_id)}")


def status_from_row(row: JobRow) -> dict[str, Any]:
    status = str(row["status"])
    outputs = row["outputs"] or []
    return {
        "status": status,
        "details": row["details"],
        "step": row["step"],
        "step_index": row["step_index"],
        "total_steps": row["total_steps"],
        "calculation": row["calculation"],
        "travel_times": row["travel_times"],
        "error": row["error"],
        "created_at": iso(row["created_at"]),
        "started_at": iso(row["started_at"]),
        "finished_at": iso(row["finished_at"]),
        "outputs": [output["name"] for output in outputs],
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
    *, data: EarthquakeInput, simulation_id: str, defer: Any
) -> dict[str, Any]:
    """Insert a job and enqueue it, atomically.

    `defer` receives the open connection and new compute job id. Keeping it as
    an argument leaves this module independent of the queue implementation.
    The insert and enqueue commit together, so a job row always has a queue
    entry.
    """
    simulation_uuid = as_uuid(simulation_id)
    input_params = _model_dump(data)

    with pooled() as conn, conn.transaction():
        compute_job_id = uuid.uuid4()
        inserted = conn.execute(
            INSERT_JOB_SQL,
            [
                compute_job_id,
                simulation_uuid,
                JobStatus.QUEUED.value,
                Jsonb(input_params),
                "Queued for simulation worker",
            ],
        ).fetchone()

        if inserted is None:
            existing = conn.execute(
                SELECT_BY_SIMULATION_ID, [simulation_uuid]
            ).fetchone()
            if existing is None:
                raise RuntimeError("Compute job was not persisted")
            if existing["input_params"] != input_params:
                raise ValueError("Job id already exists with different input")
            return status_from_row(existing)

        defer(conn, compute_job_id)
        return status_from_row(inserted)


def get_job_status(simulation_id: str) -> dict[str, Any]:
    try:
        simulation_uuid = as_uuid(simulation_id)
        with pooled() as conn:
            row = conn.execute(SELECT_BY_SIMULATION_ID, [simulation_uuid]).fetchone()
    except Exception as e:
        logger.error("Job lookup failed for %s: %s", sanitize_for_log(simulation_id), e)
        raise ValueError("Invalid or unknown job ID") from e

    if row is None:
        raise ValueError("Invalid or unknown job ID")
    return status_from_row(row)


def get_outputs(simulation_id: str) -> list[StoredOutput]:
    """Return the outputs recorded with a completed job."""
    simulation_uuid = as_uuid(simulation_id)
    with pooled() as conn:
        row = conn.execute(
            "SELECT status, outputs FROM compute.jobs WHERE simulation_id = %s",
            [simulation_uuid],
        ).fetchone()
    if row is None:
        raise ValueError("Invalid or unknown job ID")
    if row["status"] != JobStatus.COMPLETED.value:
        return []
    return cast(list[StoredOutput], row["outputs"] or [])


def get_current_step(
    conn: psycopg.Connection[JobRow], job_uuid: uuid.UUID
) -> str | None:
    row = conn.execute(
        "SELECT step FROM compute.jobs WHERE id = %s", [job_uuid]
    ).fetchone()
    return str(row["step"]) if row and row["step"] else None


def list_abandoned_work_dirs(cutoff: datetime) -> list[str]:
    """Return failed job workspaces older than the retention cutoff."""
    with pooled() as conn:
        rows = conn.execute(
            """
            SELECT simulation_id FROM compute.jobs
            WHERE status = %s AND finished_at IS NOT NULL AND finished_at < %s
            """,
            [JobStatus.FAILED.value, cutoff],
        ).fetchall()
    return [str(row["simulation_id"]) for row in rows]


def is_database_connected() -> bool:
    try:
        with pooled() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def mark_started(
    conn: psycopg.Connection[JobRow], job_uuid: uuid.UUID, simulation_id: uuid.UUID
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
    _notify(conn, simulation_id)
    conn.commit()


def record_progress(
    conn: psycopg.Connection[JobRow],
    job_uuid: uuid.UUID,
    simulation_id: uuid.UUID,
    message: str,
    details: dict[str, Any],
) -> None:
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
    _notify(conn, simulation_id)
    conn.commit()


def record_failure(
    conn: psycopg.Connection[JobRow],
    job_uuid: uuid.UUID,
    simulation_id: uuid.UUID,
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
    _notify(conn, simulation_id)
    conn.commit()


def fail_job(
    conn: psycopg.Connection[JobRow],
    job_uuid: uuid.UUID,
    simulation_id: uuid.UUID,
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
    _notify(conn, simulation_id)
    conn.commit()


def complete_job(
    conn: psycopg.Connection[JobRow], row: JobRow, result: SimulationResult
) -> None:
    """Upload the result and commit its manifest with the terminal state."""
    now = datetime.now().astimezone()
    simulation_id = str(row["simulation_id"])
    compute_job_id = str(row["id"])
    calculation = result.calculation.model_dump(mode="json")
    travel_times = result.travel_times.model_dump(mode="json")

    outputs: list[StoredOutput] = [
        {
            "name": output.name,
            "key": f"simulations/{simulation_id}/outputs/{output.path.name}",
            "filename": output.path.name,
            "content_type": output.content_type,
        }
        for output in result.outputs.files
    ]

    metadata = {
        "simulation_id": simulation_id,
        "compute_job_id": compute_job_id,
        "status": JobStatus.COMPLETED.value,
        "created_at": iso(row["created_at"]),
        "started_at": iso(row["started_at"]),
        "finished_at": now.isoformat(),
        "calculation": calculation,
        "travel_times": travel_times,
        "outputs": outputs,
    }
    bucket, metadata_key = output_store.upload_simulation_result(
        simulation_id=simulation_id,
        compute_job_id=compute_job_id,
        outputs=result.outputs,
        metadata=metadata,
    )

    conn.execute(
        """
        UPDATE compute.jobs
        SET status = %s, details = %s, calculation = %s, travel_times = %s,
            outputs = %s, result_bucket = %s, result_key = %s, error = NULL,
            finished_at = %s, updated_at = now()
        WHERE id = %s
        """,
        [
            JobStatus.COMPLETED.value,
            "Simulation completed successfully",
            Jsonb(calculation),
            Jsonb(travel_times),
            Jsonb(outputs),
            bucket,
            metadata_key,
            now,
            row["id"],
        ],
    )
    _notify(conn, row["simulation_id"])
    conn.commit()


def open_worker_connection() -> psycopg.Connection[JobRow]:
    return connect()
