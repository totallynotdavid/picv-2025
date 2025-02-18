import logging
import os
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
    base_dir = (Path(MODEL_DIR).parent / "jobs").resolve()
    base_str = str(base_dir)

    # Construct the path and normalize it
    constructed_path = os.path.join(base_str, job_id)
    normalized_path = os.path.normpath(constructed_path)

    # Check if the normalized path is within the base directory
    if not normalized_path.startswith(base_str):
        logger.error(f"Path traversal attempt detected: {job_id}")
        raise HTTPException(status_code=400, detail="Invalid job path")

    # Convert to Path and resolve any symlinks
    job_dir = Path(normalized_path).resolve()

    # Ensure the resolved path is still within the base directory
    if not job_dir.is_relative_to(base_dir):
        logger.error(f"Resolved path traversal detected: {job_id}")
        raise HTTPException(status_code=400, detail="Invalid job path")

    return job_dir
