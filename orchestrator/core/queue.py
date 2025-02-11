import logging
import subprocess
import uuid
from enum import Enum
from pathlib import Path
from typing import Dict

from redis import Redis
from rq import Queue
from rq.job import Job

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def execute_tsdhn_commands(job_id: str) -> Dict:
    """
    Synchronous function to execute TSDHN commands.
    This is what gets queued in RQ.
    """
    try:
        logger.info(f"Starting TSDHN execution for job {job_id}")
        model_dir = Path("model")

        # Execute commands sequentially
        commands = [
            ("fault_plane", "./fault_plane"),
            ("deform", "./deform"),
            ("tsunami", "./tsunami"),
            ("espejo", ""),
            ("maxola.csh", "./maxola.csh"),
            ("ttt_max", "./ttt_max"),
            ("mareograma.csh", ""),
            ("mareograma1.csh", ""),
            ("mareograma2.csh", ""),
        ]

        # Execute main commands
        for cmd_name, cmd_exec in commands:
            # Set permissions
            subprocess.run(["chmod", "775", cmd_name], cwd=model_dir, check=True)
            # Execute if there's a command
            if cmd_exec:
                subprocess.run(cmd_exec, cwd=model_dir, shell=True, check=True)

        # Handle TTT mundo directory
        ttt_mundo_dir = model_dir / "ttt_mundo"
        ttt_commands = [
            ("ttt_inverso", "./ttt_inverso"),
            ("inverse", ""),
            ("point_ttt", "./point_ttt"),
        ]

        for cmd_name, cmd_exec in ttt_commands:
            subprocess.run(["chmod", "775", cmd_name], cwd=ttt_mundo_dir, check=True)
            if cmd_exec:
                subprocess.run(cmd_exec, cwd=ttt_mundo_dir, shell=True, check=True)

        # Copy TTT file
        subprocess.run(["cp", "ttt.eps", "../ttt.eps"], cwd=ttt_mundo_dir, check=True)

        # Generate report
        subprocess.run(["chmod", "775", "reporte"], cwd=model_dir, check=True)
        subprocess.run(["./reporte"], cwd=model_dir, check=True)
        subprocess.run(["pdflatex", "reporte.tex"], cwd=model_dir, check=True)

        # Cleanup
        subprocess.run(
            ["rm", "-f", "reporte.aux", "reporte.log"], cwd=model_dir, check=True
        )

        return {"status": JobStatus.COMPLETED.value, "job_id": job_id}

    except subprocess.CalledProcessError as e:
        logger.exception(f"Command failed: {e.cmd}")
        raise RuntimeError(f"Command failed: {e.cmd}") from e
    except Exception:
        logger.exception("Error in TSDHN execution")
        raise


class TSDHNJob:
    def __init__(self):
        self.redis = Redis(host="localhost", port=6379, db=0)
        self.queue = Queue("tsdhn_queue", connection=self.redis)

    def enqueue_job(self) -> str:
        """Enqueue a new TSDHN job"""
        try:
            job_id = str(uuid.uuid4())

            # Enqueue the synchronous function
            job = self.queue.enqueue(
                execute_tsdhn_commands,
                job_id,
                job_timeout="2h",
                result_ttl=86400,  # Keep results for 24 hours
            )

            job.meta["status"] = JobStatus.QUEUED.value
            job.save_meta()

            return job_id

        except Exception:
            logger.exception("Failed to enqueue job")
            raise

    def get_job_status(self, job_id: str) -> Dict:
        """Get the status of a job"""
        try:
            job = Job.fetch(job_id, connection=self.redis)

            if not job:
                raise ValueError(f"Job {job_id} not found")

            status = job.meta.get("status", JobStatus.QUEUED.value)

            # Check if job is done but status wasn't updated
            if job.is_finished and status != JobStatus.COMPLETED.value:
                status = JobStatus.COMPLETED.value
                job.meta["status"] = status
                job.save_meta()

            return {
                "status": status,
                "error": job.meta.get("error"),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "ended_at": job.ended_at.isoformat() if job.ended_at else None,
            }

        except Exception:
            logger.exception(f"Error getting status for job {job_id}")
            raise
