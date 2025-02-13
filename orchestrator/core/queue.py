import logging
import subprocess
import uuid
from enum import Enum
from pathlib import Path
from typing import Dict, List, Tuple

from redis import Redis
from rq import Queue
from rq.job import Job

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


PROCESSING_PIPELINE = [
    (
        "fault_plane",
        ["./fault_plane"],
        [("pfalla.inp", "Input file for deform not generated")],
    ),
    (
        "deform",
        ["./deform"],
        [("deform", "Deform executable missing")],
    ),
    (
        "tsunami",
        ["./tsunami"],
        [
            ("zfolder/green.dat", "Green data file missing"),
            ("zfolder/zmax_a.grd", "Zmax grid file missing"),
        ],
    ),
    (
        "maxola.csh",
        ["./maxola.csh"],
        [("maxola.eps", "Maxola output missing")],
    ),
    (
        "ttt_max",
        ["./ttt_max"],
        [
            ("zfolder/green_rev.dat", "Scaled wave height data output missing"),
            ("ttt_max.dat", "TTT Max data output missing"),
        ],
    ),
]


def compile_fortran(source_dir: Path, config: dict) -> None:
    """Compile Fortran source with proper flags"""
    args = [
        config["compiler"],
        *config["flags"],
        config["source"],
        "-o",
        config["output"],
    ]
    subprocess.run(args, cwd=source_dir, check=True)


def validate_files(cwd: Path, checks: List[Tuple[str, str]]) -> None:
    """Validate multiple file existences with custom errors"""
    for filename, error_msg in checks:
        full_path = cwd / filename
        if not full_path.exists():
            logger.error(f"{error_msg} at {full_path}")
            raise FileNotFoundError(f"{full_path}: {error_msg}")


def execute_tsdhn_commands(job_id: str) -> Dict:
    """Execute TSDHN workflow with accurate file validation"""
    try:
        logger.info(f"Starting TSDHN execution for job {job_id}")
        model_dir = Path("model")
        ttt_mundo_dir = model_dir / "ttt_mundo"

        # Main processing steps
        for step_name, cmd, file_checks in PROCESSING_PIPELINE:
            # Compile if necessary
            if step_name == "fault_plane":
                compile_fortran(
                    model_dir,
                    {
                        "compiler": "gfortran",
                        "flags": [],
                        "source": "fault_plane.f90",
                        "output": "fault_plane",
                    },
                )
            elif step_name == "deform":
                compile_fortran(
                    model_dir,
                    {
                        "compiler": "gfortran",
                        "flags": [],
                        "source": "def_oka.f",
                        "output": "deform",
                    },
                )
            elif step_name == "ttt_max":
                compile_fortran(
                    model_dir,
                    {
                        "compiler": "gfortran",
                        "flags": [],
                        "source": "ttt_max.f90",
                        "output": "ttt_max",
                    },
                )

            # Additional pre-execution steps
            if step_name == "ttt_max":
                validate_files(
                    model_dir, [("mareograma.csh", "mareograma.csh script missing")]
                )
                subprocess.run(
                    ["chmod", "775", "mareograma.csh"], cwd=model_dir, check=True
                )

            # Execute and validate
            subprocess.run(["chmod", "775", cmd[0]], cwd=model_dir, check=True)
            subprocess.run(cmd, cwd=model_dir, check=True)
            validate_files(model_dir, file_checks)

        # TTT Mundo processing
        ttt_mundo_dir = model_dir / "ttt_mundo"

        # We have to make sure that inverse (csh)
        # is executable before ttt_inverso runs as
        # it is called from within the script
        inverse_script = ttt_mundo_dir / "inverse"
        if not inverse_script.exists():
            raise FileNotFoundError(f"inverse script not found at {inverse_script}")
        subprocess.run(["chmod", "775", "inverse"], cwd=ttt_mundo_dir, check=True)

        ttt_steps = [
            (
                "ttt_inverso",
                ["./ttt_inverso"],
                [],
            ),
        ]

        for step_name, cmd, file_checks in ttt_steps:
            if step_name == "ttt_inverso":
                compile_fortran(
                    ttt_mundo_dir,
                    {
                        "compiler": "gfortran",
                        "flags": [],
                        "source": "ttt_inverso.f",
                        "output": "ttt_inverso",
                    },
                )
            subprocess.run(["chmod", "775", cmd[0]], cwd=ttt_mundo_dir, check=True)
            subprocess.run(cmd, cwd=ttt_mundo_dir, check=True)
            validate_files(ttt_mundo_dir, file_checks)

        # Final report generation
        compile_fortran(
            model_dir,
            {
                "compiler": "gfortran",
                "flags": [],
                "source": "reporte.f90",
                "output": "reporte",
            },
        )
        subprocess.run(["chmod", "775", "reporte"], cwd=model_dir, check=True)
        subprocess.run(["./reporte"], cwd=model_dir, check=True)
        validate_files(model_dir, [("reporte.txt", "Report text output missing")])

        subprocess.run(["pdflatex", "reporte.tex"], cwd=model_dir, check=True)
        validate_files(model_dir, [("reporte.pdf", "PDF report not generated")])

        # Cleanup
        subprocess.run(
            ["rm", "-f", "reporte.aux", "reporte.log"], cwd=model_dir, check=True
        )

        return {"status": JobStatus.COMPLETED.value, "job_id": job_id}

    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.cmd}\nExit code: {e.returncode}")
        raise RuntimeError(f"Process failed at step {e.cmd}") from e
    except FileNotFoundError as e:
        logger.error(f"Critical file missing: {str(e)}")
        raise
    except Exception as e:
        logger.exception("Unhandled error in TSDHN execution")
        raise RuntimeError("Job failed due to unexpected error") from e


class TSDHNJob:
    """Main job handler class with Redis integration"""

    def __init__(self):
        self.redis = Redis(host="localhost", port=6379, db=0, socket_connect_timeout=5)
        self.queue = Queue("tsdhn_queue", connection=self.redis)

    def enqueue_job(self) -> str:
        """Enqueue a new TSDHN job with Redis connection handling"""
        try:
            job_id = str(uuid.uuid4())
            self.queue.enqueue(
                execute_tsdhn_commands,
                job_id,
                job_id=job_id,
                job_timeout="2h",
                result_ttl=86400,
                meta={"status": JobStatus.QUEUED.value},
            )
            return job_id
        except Redis.exceptions.ConnectionError:
            logger.error("Failed to connect to Redis")
            raise
        except Exception:
            logger.exception("Job enqueue failed")
            raise

    def get_job_status(self, job_id: str) -> Dict:
        """Get job status with proper error handling"""
        try:
            job = Job.fetch(job_id, connection=self.redis)
            status = job.meta.get("status", JobStatus.QUEUED.value)

            # Update status based on RQ's internal state
            if job.is_failed:
                status = JobStatus.FAILED.value
                job.meta.setdefault("error", "Job failed without specific error")
            elif job.is_finished and status != JobStatus.COMPLETED.value:
                status = JobStatus.COMPLETED.value

            # Persist status changes
            job.meta["status"] = status
            job.save_meta()

            return {
                "status": status,
                "error": job.meta.get("error"),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "ended_at": job.ended_at.isoformat() if job.ended_at else None,
            }
        except Exception as e:
            logger.exception(f"Status check failed for job {job_id}")
            raise ValueError(f"Invalid job ID or system error: {str(e)}") from e
