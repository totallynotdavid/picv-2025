import logging
import uuid
from pathlib import Path

from fastapi import HTTPException

from orchestrator.core.config import MODEL_DIR
from orchestrator.core.queue import tsdhn_queue

logger = logging.getLogger(__name__)


def validate_job_id(job_id: str) -> None:
    """
    Validate that the job ID is a valid UUID and that a job with that ID exists.
    """
    try:
        uuid.UUID(job_id, version=4)
    except ValueError as e:
        logger.warning(f"Invalid job ID format: {job_id}")
        raise HTTPException(status_code=400, detail="Invalid job identifier") from e

    try:
        tsdhn_queue.get_job_status(job_id)
    except ValueError as e:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(status_code=404, detail="Job not found") from e


def secure_path_construction(job_id: str) -> Path:
    """
    Safely construct and validate the job directory
    path to prevent path traversal attacks.
    """
    base_dir = (Path(MODEL_DIR).parent / "jobs").resolve()
    job_dir = (base_dir / job_id).resolve()

    # Ensure that the resolved job directory is under the base directory.
    if not job_dir.is_relative_to(base_dir):
        logger.error(f"Path traversal attempt detected: {job_id}")
        raise HTTPException(status_code=400, detail="Invalid job path")

    return job_dir
