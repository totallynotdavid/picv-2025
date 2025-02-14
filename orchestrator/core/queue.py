import logging
import subprocess
import uuid
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from redis import Redis
from rq import Queue
from rq.job import Job

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CompilerConfig:
    def __init__(
        self,
        source: str,
        output: str,
        compiler: str = "gfortran",
        flags: List[str] = None,
    ):
        self.source = source
        self.output = output
        self.compiler = compiler
        self.flags = flags or []


class ProcessingStep:
    def __init__(
        self,
        name: str,
        command: List[str],
        file_checks: List[Tuple[str, str]],
        compiler_config: Optional[CompilerConfig] = None,
        pre_execute_checks: List[Tuple[str, str]] = None,
        extra_executables: List[str] = None,
    ):
        self.name = name
        self.command = command
        self.file_checks = file_checks
        self.compiler_config = compiler_config
        self.pre_execute_checks = pre_execute_checks or []
        self.extra_executables = extra_executables or []


PROCESSING_PIPELINE = [
    ProcessingStep(
        "fault_plane",
        ["./fault_plane"],
        [("pfalla.inp", "Input file for deform not generated")],
        CompilerConfig("fault_plane.f90", "fault_plane"),
    ),
    ProcessingStep(
        "deform",
        ["./deform"],
        [("deform", "Deform executable missing")],
        CompilerConfig("def_oka.f", "deform"),
    ),
    ProcessingStep(
        "tsunami",
        ["./tsunami"],
        [
            ("zfolder/green.dat", "Green data file missing"),
            ("zfolder/zmax_a.grd", "Zmax grid file missing"),
        ],
    ),
    ProcessingStep(
        "maxola.csh",
        ["./maxola.csh"],
        [("maxola.eps", "Maxola output missing")],
        extra_executables=["espejo"],
    ),
    ProcessingStep(
        "ttt_max",
        ["./ttt_max"],
        [
            ("zfolder/green_rev.dat", "Scaled wave height data output missing"),
            ("ttt_max.dat", "TTT Max data output missing"),
        ],
        CompilerConfig("ttt_max.f90", "ttt_max"),
        pre_execute_checks=[("mareograma.csh", "mareograma.csh script missing")],
    ),
]

TTT_MUNDO_STEPS = [
    ProcessingStep(
        "ttt_inverso",
        ["./ttt_inverso"],
        [],
        CompilerConfig("ttt_inverso.f", "ttt_inverso"),
        extra_executables=["inverse"],
    ),
]


def make_executable(file_path: Path) -> None:
    """Make a file executable with proper error handling"""
    try:
        subprocess.run(["chmod", "775", str(file_path)], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to make {file_path} executable: {e}")
        raise


def compile_fortran(source_dir: Path, config: CompilerConfig) -> None:
    """Compile Fortran source with proper flags"""
    args = [
        config.compiler,
        *config.flags,
        config.source,
        "-o",
        config.output,
    ]
    subprocess.run(args, cwd=source_dir, check=True)


def validate_files(cwd: Path, checks: List[Tuple[str, str]]) -> None:
    """Validate multiple file existences with custom errors"""
    for filename, error_msg in checks:
        full_path = cwd / filename
        if not full_path.exists():
            logger.error(f"{error_msg} at {full_path}")
            raise FileNotFoundError(f"{full_path}: {error_msg}")


def process_step(step: ProcessingStep, working_dir: Path) -> None:
    """Process a single pipeline step"""
    # Compile if necessary
    if step.compiler_config:
        compile_fortran(working_dir, step.compiler_config)
        make_executable(working_dir / step.compiler_config.output)

    # Pre-execution checks
    if step.pre_execute_checks:
        validate_files(working_dir, step.pre_execute_checks)
        for check in step.pre_execute_checks:
            make_executable(working_dir / check[0])

    # Make additional executables executable
    for executable in step.extra_executables:
        make_executable(working_dir / executable)

    # Execute main command and validate
    make_executable(working_dir / step.command[0])
    subprocess.run(step.command, cwd=working_dir, check=True)
    validate_files(working_dir, step.file_checks)


def execute_tsdhn_commands(job_id: str) -> Dict:
    """Execute TSDHN workflow with accurate file validation"""
    try:
        logger.info(f"Starting TSDHN execution for job {job_id}")
        model_dir = Path("model")
        ttt_mundo_dir = model_dir / "ttt_mundo"

        # Main processing steps
        for step in PROCESSING_PIPELINE:
            process_step(step, model_dir)

        # TTT Mundo processing
        for step in TTT_MUNDO_STEPS:
            process_step(step, ttt_mundo_dir)

        # Final report generation
        report_config = CompilerConfig("reporte.f90", "reporte")
        compile_fortran(model_dir, report_config)
        make_executable(model_dir / "reporte")

        subprocess.run(["./reporte"], cwd=model_dir, check=True)
        validate_files(model_dir, [("salida.txt", "Report text output missing")])

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

    def __init__(self, redis_host="localhost", redis_port=6379, redis_db=0):
        self.redis = Redis(
            host=redis_host, port=redis_port, db=redis_db, socket_connect_timeout=5
        )
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
