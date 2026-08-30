import contextlib
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tsdhn.pipeline.types import ProcessingStep

WORKSPACE_DIRS: tuple[str, ...] = ("bathy", "ttt_mundo", "zfolder")
WORKSPACE_INPUTS: tuple[str, ...] = (
    "mecfoc.dat",
    "tidal.dat",
    "bathy/grid_a.grd",
    "bathy/xa.dat",
    "bathy/ya.dat",
    "ttt_mundo/cortado.i2",
)


def make_executable(file_path: Path) -> None:
    file_path.chmod(file_path.stat().st_mode | 0o111)


@contextlib.contextmanager
def atomic_write(path: Path) -> Iterator[Path]:
    """Yield a sibling temp path; rename it onto `path` only on clean exit.

    A killed writer must not leave a truncated file that passes the existence
    check used by resume and skip logic. `os.replace` is atomic on POSIX, so
    readers see the old file, no file, or the complete new file.
    """
    tmp_path = path.parent / f"{path.name}.tmp"
    try:
        yield tmp_path
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    else:
        os.replace(tmp_path, path)


def validate_outputs(working_dir: Path, step: ProcessingStep) -> None:
    """Raise if any of `step`'s declared outputs is absent from disk.

    Paths are resolved relative to `working_dir`, which is the step's own
    directory (see ProcessingStep.outputs).
    """
    missing = [name for name in step.outputs if not (working_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Step '{step.name}' did not produce: {', '.join(missing)}"
        )


def prepare_simulation_workspace(
    model_dir: Path, work_dir: Path, *, resume: bool = False
) -> None:
    """Create a clean simulation workspace, unless `resume` is true."""
    if work_dir.exists() and not resume:
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    for dirname in WORKSPACE_DIRS:
        (work_dir / dirname).mkdir(exist_ok=True)

    for relative_name in WORKSPACE_INPUTS:
        source = model_dir / relative_name
        if not source.is_file():
            raise FileNotFoundError(f"Required model input missing: {source}")
        destination = work_dir / relative_name
        if not destination.exists():
            _link_or_copy(source, destination)


def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.symlink_to(source)
    except OSError:
        shutil.copy2(source, destination)


def sanitize_for_log(value: str) -> str:
    """Log values cannot contain control characters that could forge entries."""
    if value is None:
        return "None"

    value_str = str(value)

    sanitized = value_str.replace("\n", "\\n").replace("\r", "\\r")

    # Log fields are capped so malicious ids cannot flood API logs.
    max_length = 100
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."

    return sanitized
