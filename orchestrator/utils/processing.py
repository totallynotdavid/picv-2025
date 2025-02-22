import subprocess
from pathlib import Path

from orchestrator.core.config import ProcessingStep
from orchestrator.utils.compiler import compile_fortran
from orchestrator.utils.file_utils import make_executable, validate_files


def process_step(step: ProcessingStep, working_dir: Path) -> None:
    if step.python_callable:
        step.python_callable(working_dir)
    else:
        handle_command_step(step, working_dir)
    validate_files(working_dir, step.file_checks)


def handle_command_step(step: ProcessingStep, working_dir: Path) -> None:
    if step.compiler_config:
        compile_fortran(working_dir, step.compiler_config)
        make_executable(working_dir / step.compiler_config.output)

    for exe in step.extra_executables:
        make_executable(working_dir / exe)

    cmd_path = working_dir / step.command[0]
    make_executable(cmd_path)
    subprocess.run(step.command, cwd=working_dir, check=True)
