import subprocess
from pathlib import Path

from orchestrator.core.config import CompilerConfig


def compile_fortran(working_dir: Path, config: CompilerConfig) -> None:
    args = [config.compiler, *config.flags, config.source, "-o", config.output]
    subprocess.run(args, cwd=working_dir, check=True)
