import logging
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from redis import Redis
from redis.exceptions import ConnectionError
from rq import Queue, get_current_job
from rq.job import Job

from orchestrator.core.config import MASTER_PIPELINE, MODEL_DIR
from orchestrator.models.schemas import JobStatus
from orchestrator.utils.file_utils import setup_workspace
from orchestrator.utils.processing import process_step
from orchestrator.utils.system import check_dependencies

logger = logging.getLogger(__name__)


def _update_job_metadata(job: Optional[Job], details: str, **kwargs) -> None:
    if job:
        job.meta.update({"details": details, **kwargs})
        job.save_meta()


def _validate_skip_steps(skip_steps: List[str]) -> None:
    all_step_names = [step.name for step in MASTER_PIPELINE]
    invalid = set(skip_steps) - set(all_step_names)
    if invalid:
        raise ValueError(f"Invalid skip steps: {invalid}")


def execute_tsdhn_commands(job_id: str, skip_steps: Optional[List[str]] = None) -> Dict:
    job = get_current_job()
    job_work_dir: Optional[Path] = None
    skip_steps = skip_steps or []
    _validate_skip_steps(skip_steps)

    try:
        _update_job_metadata(
            job, "Initializing environment", status=JobStatus.RUNNING.value
        )
        logger.info(f"Starting TSDHN execution for job {job_id}")

        check_dependencies()

        # Setup workspace
        repo_root = Path(__file__).resolve().parent.parent.parent
        base_model_dir = repo_root / MODEL_DIR
        job_work_dir = repo_root / "jobs" / job_id
        setup_workspace(base_model_dir, job_work_dir)

        # Process all steps in single loop
        for step in MASTER_PIPELINE:
            if step.name in skip_steps:
                logger.info(f"Skipping step: {step.name}")
                continue

            step_dir = (
                job_work_dir / step.working_dir if step.working_dir else job_work_dir
            )
            step_dir.mkdir(parents=True, exist_ok=True)

            _update_job_metadata(job, f"Processing {step.name}")
            process_step(step, step_dir)

        result = {
            "status": JobStatus.COMPLETED.value,
            "job_id": job_id,
            "download_url": f"/job-result/{job_id}",
        }
        _update_job_metadata(job, "Completed successfully", **result)
        return result

    except Exception as e:
        logger.exception(f"Job {job_id} failed: {str(e)}")
        _update_job_metadata(
            job,
            f"Failed: {str(e)}",
            status=JobStatus.FAILED.value,
            error=f"{type(e).__name__}: {str(e)}",
        )
        if job_work_dir and job_work_dir.exists():
            shutil.rmtree(job_work_dir, ignore_errors=True)
        raise RuntimeError(f"Job failed: {str(e)}") from e


class TSDHNJob:
    def __init__(
        self, redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 0
    ):
        self.redis = Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            socket_connect_timeout=5,
            socket_keepalive=True,
        )
        self.queue = Queue("tsdhn_queue", connection=self.redis)

    def enqueue_job(self, skip_steps: Optional[List[str]] = None) -> str:
        skip_steps = skip_steps or []
        _validate_skip_steps(skip_steps)
        try:
            job_id = str(uuid.uuid4())
            self.queue.enqueue(
                execute_tsdhn_commands,
                job_id,
                skip_steps=skip_steps,
                job_id=job_id,
                job_timeout="2h",
                result_ttl=86400,
                meta={
                    "status": JobStatus.QUEUED.value,
                    "details": "Waiting in queue",
                },
            )
            return job_id
        except ConnectionError as e:
            logger.error("Redis connection failed: %s", e)
            raise RuntimeError("Could not connect to job queue") from e
        except Exception as e:
            logger.exception("Job enqueue failed")
            raise RuntimeError(f"Enqueue failed: {str(e)}") from e

    def get_job_status(self, job_id: str) -> Dict:
        try:
            job = Job.fetch(job_id, connection=self.redis)
            status_map = {
                "queued": JobStatus.QUEUED.value,
                "started": JobStatus.RUNNING.value,
                "finished": JobStatus.COMPLETED.value,
                "failed": JobStatus.FAILED.value,
            }

            return {
                "status": status_map.get(job.get_status(), JobStatus.QUEUED.value),
                "details": job.meta.get("details"),
                "error": job.meta.get("error"),
                "download_url": job.meta.get("download_url"),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "ended_at": job.ended_at.isoformat() if job.ended_at else None,
            }
        except Exception as e:
            logger.exception(f"Status check failed for {job_id}")
            raise ValueError(f"Invalid job ID: {str(e)}") from e


tsdhn_queue = TSDHNJob()
