import shutil
from pathlib import Path
from typing import List, Tuple


def make_executable(file_path: Path) -> None:
    file_path.chmod(file_path.stat().st_mode | 0o111)


def validate_files(cwd: Path, checks: List[Tuple[str, str]]) -> None:
    missing = []
    for filename, msg in checks:
        if not (cwd / filename).exists():
            missing.append(f"{filename}: {msg}")
    if missing:
        raise FileNotFoundError("\n".join(missing))


def setup_workspace(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
