import logging
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from redis import Redis
from redis.exceptions import ConnectionError
from rq import Queue, get_current_job
from rq.job import Job

from orchestrator.modules.reporte import generate_reports
from orchestrator.modules.ttt_max import process_tsunami_data

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
    command: Optional[List[str]] = None
    python_callable: Optional[Callable[[Path], None]] = None
    file_checks: List[Tuple[str, str]] = field(default_factory=list)
    compiler_config: Optional[CompilerConfig] = None
    pre_execute_checks: List[Tuple[str, str]] = field(default_factory=list)
    extra_executables: List[str] = field(default_factory=list)
    working_dir: Optional[str] = None  # Subdirectory for execution if needed

    def __post_init__(self):
        if not (self.command is None) ^ (self.python_callable is None):
            raise ValueError(
                "ProcessingStep must have either command or python_callable"
            )

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


def generate_reports_wrapper(working_dir: Path) -> None:
    generate_reports(working_dir)

    for _ in range(2):  # Compile twice to resolve references
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "reporte.tex"],
            cwd=working_dir,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    for f in ["reporte.aux", "reporte.out", "reporte.log", "reporte.tex"]:
        (working_dir / f).unlink(missing_ok=True)

    validate_pdf(working_dir / "reporte.pdf")


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
        python_callable=process_tsunami_data,
        file_checks=[
            ("zfolder/green_rev.dat", "Scaled wave height data output missing"),
            ("ttt_max.dat", "TTT Max data output missing"),
            ("mareograma.eps", "Mareogram plot missing"),
        ],
    ),
]

TTT_MUNDO_STEPS = [
    ProcessingStep(
        name="ttt_inverso",
        command=["./ttt_inverso"],
        compiler_config=CompilerConfig("ttt_inverso.f", "ttt_inverso"),
        extra_executables=["inverse"],
        working_dir="ttt_mundo",
        file_checks=[("ttt_mundo.dat", "TTT inverso output missing")],
    ),
    ProcessingStep(
        name="point_ttt",
        command=["./point_ttt"],
        working_dir="ttt_mundo",
        extra_executables=["point_ttt"],
        file_checks=[("ttt.eps", "ttt.eps not generated")],
    ),
    ProcessingStep(
        name="copy_ttt_eps",
        command=["cp", "ttt.eps", "../ttt.eps"],
        working_dir="ttt_mundo",
        file_checks=[("../ttt.eps", "ttt.eps not copied to parent directory")],
    ),
]

REPORT_STEPS = [
    ProcessingStep(
        name="generate_reports",
        python_callable=generate_reports_wrapper,
        file_checks=[("reporte.pdf", "Final report PDF missing")],
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
        subprocess.run(args, cwd=source_dir, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Compilation failed for {config.source}:\n{e.stderr.decode()}")
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


def validate_pdf(filepath: Path) -> None:
    if not filepath.exists():
        raise FileNotFoundError(f"PDF file {filepath} not found")
    if filepath.stat().st_size < 1024:
        raise ValueError(f"PDF file {filepath} seems corrupted")


def _update_job_metadata(job: Optional[Job], details: str, **kwargs) -> None:
    if job:
        job.meta.update({"details": details, **kwargs})
        job.save_meta()


def process_step(step: ProcessingStep, working_dir: Path) -> None:
    logger.info(f"Processing step: {step.name}")

    if step.python_callable:
        step.python_callable(working_dir)
    else:
        step.handle_compilation(working_dir)
        step.validate_pre_execute(working_dir)
        step.prepare_executables(working_dir)

        # Make main command executable
        command_path = step.get_command_path(working_dir)
        make_executable(command_path)

        # Execute the command
        subprocess.run(
            step.command,
            cwd=working_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    validate_files(working_dir, step.file_checks)


def check_dependencies() -> None:
    required_commands = ["gfortran", "pdflatex", "csh"]
    missing = [cmd for cmd in required_commands if not shutil.which(cmd)]

    if missing:
        error_msg = f"Missing required system commands: {', '.join(missing)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


def execute_tsdhn_commands(job_id: str, skip_steps: List[str] = None) -> Dict:
    job = get_current_job()
    job_work_dir = None

    try:
        # Initialize job metadata
        _update_job_metadata(
            job, "Initializing environment", status=JobStatus.RUNNING.value
        )
        logger.info(f"Starting TSDHN execution for job {job_id}")
        check_dependencies()

        # Setup isolated workspace
        repo_root = Path(__file__).resolve().parent.parent.parent
        base_model_dir = repo_root / "model"
        job_work_dir = repo_root / "jobs" / job_id

        if job_work_dir.exists():
            shutil.rmtree(job_work_dir)
        shutil.copytree(base_model_dir, job_work_dir)

        logger.info(f"Processing job {job_id} in {job_work_dir}")
        skip_steps = skip_steps or []

        # Validate skip steps
        all_step_names = [
            step.name for step in PROCESSING_PIPELINE + TTT_MUNDO_STEPS + REPORT_STEPS
        ]
        if invalid := set(skip_steps) - set(all_step_names):
            raise ValueError(f"Invalid skip steps: {invalid}")

        # Process main pipeline
        for step in PROCESSING_PIPELINE:
            if step.name in skip_steps:
                logger.info(f"Skipping step: {step.name}")
                continue

            step_dir = (
                job_work_dir / step.working_dir if step.working_dir else job_work_dir
            )
            step_dir.mkdir(parents=True, exist_ok=True)

            _update_job_metadata(job, f"Processing {step.name}")
            process_step(step, step_dir)

        # Process TTT Mundo steps
        for step in TTT_MUNDO_STEPS:
            if step.name in skip_steps:
                logger.info(f"Skipping step: {step.name}")
                continue

            step_dir = job_work_dir / "ttt_mundo"
            step_dir.mkdir(parents=True, exist_ok=True)
            _update_job_metadata(job, f"Processing {step.name}")
            process_step(step, step_dir)

        # Process report steps
        for step in REPORT_STEPS:
            if step.name in skip_steps:
                logger.info(f"Skipping step: {step.name}")
                continue

            step_dir = job_work_dir
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
            f"Failed at: {job.meta.get('details') if job else 'Unknown step'}",
            status=JobStatus.FAILED.value,
            error=f"{type(e).__name__}: {str(e)}",
        )

        if job_work_dir and job_work_dir.exists():
            shutil.rmtree(job_work_dir, ignore_errors=True)

        raise RuntimeError(f"Job failed: {str(e)}") from e


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
            # Validate skip steps before queuing
            all_step_names = [
                step.name
                for step in PROCESSING_PIPELINE + TTT_MUNDO_STEPS + REPORT_STEPS
            ]
            if invalid := set(skip_steps or []) - set(all_step_names):
                raise ValueError(f"Invalid skip steps: {invalid}")

            job_id = str(uuid.uuid4())
            self.queue.enqueue(
                execute_tsdhn_commands,
                job_id,
                skip_steps=skip_steps or [],
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
