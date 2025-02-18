import logging
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from redis import Redis
from redis.exceptions import ConnectionError
from rq import Queue, get_current_job
from rq.job import Job

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class CompilerConfig:
    source: str
    output: str
    compiler: str = "gfortran"
    flags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProcessingStep:
    name: str
    command: List[str]
    file_checks: List[Tuple[str, str]]
    compiler_config: Optional[CompilerConfig] = None
    pre_execute_checks: List[Tuple[str, str]] = field(default_factory=list)
    extra_executables: List[str] = field(default_factory=list)

    def get_command_path(self, working_dir: Path) -> Path:
        return working_dir / self.command[0]

    def handle_compilation(self, working_dir: Path) -> None:
        if self.compiler_config:
            compile_fortran(working_dir, self.compiler_config)
            output_path = working_dir / self.compiler_config.output
            make_executable(output_path)

    def validate_pre_execute(self, working_dir: Path) -> None:
        if self.pre_execute_checks:
            validate_files(working_dir, self.pre_execute_checks)
            for filename, _ in self.pre_execute_checks:
                make_executable(working_dir / filename)

    def prepare_executables(self, working_dir: Path) -> None:
        for exe in self.extra_executables:
            exe_path = working_dir / exe
            if exe_path.exists():
                make_executable(exe_path)
            else:
                raise FileNotFoundError(f"Extra executable {exe_path} not found")


PROCESSING_PIPELINE = [
    ProcessingStep(
        name="fault_plane",
        command=["./fault_plane"],
        file_checks=[("pfalla.inp", "Input file for deform not generated")],
        compiler_config=CompilerConfig("fault_plane.f90", "fault_plane"),
    ),
    ProcessingStep(
        name="deform",
        command=["./deform"],
        file_checks=[("deform", "Deform executable missing")],
        compiler_config=CompilerConfig("def_oka.f", "deform"),
    ),
    ProcessingStep(
        name="tsunami",
        command=["./tsunami"],
        file_checks=[
            ("zfolder/green.dat", "Green data file missing"),
            ("zfolder/zmax_a.grd", "Zmax grid file missing"),
        ],
    ),
    ProcessingStep(
        name="maxola.csh",
        command=["./maxola.csh"],
        file_checks=[("maxola.eps", "Maxola output missing")],
        extra_executables=["espejo"],
    ),
    ProcessingStep(
        name="ttt_max",
        command=["./ttt_max"],
        file_checks=[
            ("zfolder/green_rev.dat", "Scaled wave height data output missing"),
            ("ttt_max.dat", "TTT Max data output missing"),
        ],
        compiler_config=CompilerConfig("ttt_max.f90", "ttt_max"),
        pre_execute_checks=[("mareograma.csh", "mareograma.csh script missing")],
    ),
]

TTT_MUNDO_STEPS = [
    ProcessingStep(
        name="ttt_inverso",
        command=["./ttt_inverso"],
        file_checks=[],
        compiler_config=CompilerConfig("ttt_inverso.f", "ttt_inverso"),
        extra_executables=["inverse"],
    ),
]


def make_executable(file_path: Path) -> None:
    try:
        current_mode = file_path.stat().st_mode
        file_path.chmod(current_mode | 0o111)
    except (PermissionError, FileNotFoundError) as e:
        logger.error(f"Failed to make {file_path} executable: {e}")
        raise


def compile_fortran(source_dir: Path, config: CompilerConfig) -> None:
    args = [
        config.compiler,
        *config.flags,
        config.source,
        "-o",
        config.output,
    ]
    try:
        subprocess.run(args, cwd=source_dir, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Compilation failed for {config.source}: {e}")
        raise


def validate_files(cwd: Path, checks: List[Tuple[str, str]]) -> None:
    missing = []
    for filename, error_msg in checks:
        full_path = cwd / filename
        if not full_path.exists():
            missing.append((full_path, error_msg))

    if missing:
        error_details = "\n".join([f"{path}: {msg}" for path, msg in missing])
        logger.error(f"Missing required files:\n{error_details}")
        raise FileNotFoundError(f"Missing files:\n{error_details}")


def process_step(step: ProcessingStep, working_dir: Path) -> None:
    logger.info(f"Processing step: {step.name}")

    step.handle_compilation(working_dir)
    step.validate_pre_execute(working_dir)
    step.prepare_executables(working_dir)

    # Make main command executable
    command_path = step.get_command_path(working_dir)
    make_executable(command_path)

    # Execute the command
    subprocess.run(step.command, cwd=working_dir, check=True)
    validate_files(working_dir, step.file_checks)


def check_dependencies() -> None:
    required_commands = ["gfortran", "pdflatex", "csh"]
    missing = []
    for cmd in required_commands:
        if not shutil.which(cmd):
            missing.append(cmd)

    if missing:
        error_msg = f"Missing required system commands: {', '.join(missing)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


def execute_tsdhn_commands(job_id: str, skip_steps: List[str] = None) -> Dict:
    job = get_current_job()
    try:
        # Setup job context
        if job:
            job.meta.update(
                {
                    "status": JobStatus.RUNNING.value,
                    "details": "Initializing job environment",
                }
            )
            job.save_meta()

        logger.info(f"Starting TSDHN execution for job {job_id}")
        check_dependencies()

        # Setup isolated workspace
        repo_root = Path(__file__).resolve().parent.parent.parent
        base_model_dir = repo_root / "model"
        job_work_dir = base_model_dir.parent / "jobs" / job_id

        if job_work_dir.exists():
            shutil.rmtree(job_work_dir)
        shutil.copytree(base_model_dir, job_work_dir)

        logger.info(f"Using isolated workspace: {job_work_dir}")
        skip_steps = skip_steps or []

        # Validate skip_steps parameter
        all_steps = [step.name for step in PROCESSING_PIPELINE + TTT_MUNDO_STEPS]
        if invalid := set(skip_steps) - set(all_steps):
            raise ValueError(f"Invalid steps to skip: {invalid}")

        # Main processing pipeline
        for step in PROCESSING_PIPELINE:
            if step.name in skip_steps:
                logger.info(f"Skipping step: {step.name}")
                continue

            if job:
                job.meta["details"] = f"Processing {step.name}"
                job.save_meta()

            process_step(step, job_work_dir)

        # TTT Mundo processing
        ttt_mundo_dir = job_work_dir / "ttt_mundo"
        for step in TTT_MUNDO_STEPS:
            if step.name in skip_steps:
                logger.info(f"Skipping step: {step.name}")
                continue

            if job:
                job.meta["details"] = f"Processing {step.name}"
                job.save_meta()

            process_step(step, ttt_mundo_dir)

        # Final report generation
        if job:
            job.meta["details"] = "Generating final report"
            job.save_meta()

        report_config = CompilerConfig("reporte.f90", "reporte")
        compile_fortran(job_work_dir, report_config)
        make_executable(job_work_dir / "reporte")

        subprocess.run(["./reporte"], cwd=job_work_dir, check=True)
        validate_files(job_work_dir, [("salida.txt", "Report text output missing")])

        subprocess.run(["pdflatex", "reporte.tex"], cwd=job_work_dir, check=True)
        validate_files(job_work_dir, [("reporte.pdf", "PDF report not generated")])

        # Cleanup temporary files
        for f in ["reporte.aux", "reporte.log"]:
            (job_work_dir / f).unlink(missing_ok=True)

        download_url = f"/job-result/{job_id}"
        result = {
            "status": JobStatus.COMPLETED.value,
            "job_id": job_id,
            "download_url": download_url,
        }

        if job:
            job.meta.update(result)
            job.meta["status"] = JobStatus.COMPLETED.value
            job.meta["details"] = "Job completed successfully"
            job.save_meta()

        return result

    except Exception as e:
        logger.exception(f"Job {job_id} failed")
        error_msg = f"{type(e).__name__}: {str(e)}"

        if job:
            job.meta.update(
                {
                    "status": JobStatus.FAILED.value,
                    "error": error_msg,
                    "details": f"Failed at step: {job.meta.get('details')}",
                }
            )
            job.save_meta()

        raise RuntimeError(error_msg) from e


class TSDHNJob:
    def __init__(self, redis_host="localhost", redis_port=6379, redis_db=0):
        self.redis = Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            socket_connect_timeout=5,
            socket_keepalive=True,
        )
        self.queue = Queue("tsdhn_queue", connection=self.redis)

    def enqueue_job(self, skip_steps: List[str] = None) -> str:
        try:
            # Validate steps before queuing
            all_steps = [step.name for step in PROCESSING_PIPELINE + TTT_MUNDO_STEPS]
            if invalid := set(skip_steps or []) - set(all_steps):
                raise ValueError(f"Invalid steps to skip: {invalid}")

            job_id = str(uuid.uuid4())
            self.queue.enqueue(
                execute_tsdhn_commands,
                job_id,
                skip_steps=skip_steps or [],
                job_id=job_id,
                job_timeout="2h",
                result_ttl=86400,
                meta={"status": JobStatus.QUEUED.value, "details": "Waiting in queue"},
            )
            return job_id
        except ConnectionError:
            logger.error("Failed to connect to Redis")
            raise
        except Exception as e:
            logger.exception("Job enqueue failed")
            raise RuntimeError(f"Job submission failed: {str(e)}") from e

    def get_job_status(self, job_id: str) -> Dict:
        try:
            job = Job.fetch(job_id, connection=self.redis)
            status = job.get_status()

            status_map = {
                "queued": JobStatus.QUEUED.value,
                "started": JobStatus.RUNNING.value,
                "finished": JobStatus.COMPLETED.value,
                "failed": JobStatus.FAILED.value,
            }

            return {
                "status": status_map.get(status, JobStatus.QUEUED.value),
                "details": job.meta.get("details"),
                "error": job.meta.get("error"),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "ended_at": job.ended_at.isoformat() if job.ended_at else None,
                "download_url": job.meta.get("download_url"),
            }
        except Exception as e:
            logger.exception(f"Status check failed for job {job_id}")
            raise ValueError(f"Invalid job ID or system error: {str(e)}") from e


tsdhn_queue = TSDHNJob()
