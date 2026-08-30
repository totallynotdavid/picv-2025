import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from tsdhn_parity.cases import Case
from tsdhn_parity.trace import Checkpoint, Trace

SKIP_REASON = (
    "requires the real compiled toolchain (TSDHN_TOOLS_DIR); see mise run test-parity"
)


def read_checkpoint_text(path: Path) -> np.ndarray:
    return np.loadtxt(path)


def read_fixed_width_grid(width: int) -> Callable[[Path], np.ndarray]:
    """Read fixed-width Fortran output using the format's column width."""

    def read(path: Path) -> np.ndarray:
        return np.array(
            [
                [float(line[i : i + width]) for i in range(0, len(line), width)]
                for line in path.read_text().splitlines()
            ]
        )

    return read


def run_tool(executable: Path, working_dir: Path, args: tuple[str, ...] = ()) -> None:
    """Copy a legacy executable into its work directory and run it there.

    Legacy executables resolve paths relative to their working directory.
    """
    target = working_dir / executable.name
    shutil.copy2(executable, target)
    target.chmod(target.stat().st_mode | 0o111)
    subprocess.run(
        [f"./{executable.name}", *args],
        cwd=working_dir,
        check=True,
    )


@dataclass(frozen=True)
class FortranBinaryAdapter:
    """Run a legacy executable and read its declared checkpoints.

    The unit-specific `prepare` function writes the input files.
    """

    executable: str
    checkpoints: tuple[str, ...]
    prepare: Callable[[Case, Path], None]
    args: tuple[str, ...] = ()
    tools_dir: Path | None = None
    read_checkpoint: Callable[[Path], np.ndarray] = read_checkpoint_text

    def run(self, case: Case) -> Trace:
        binary = _resolve_executable(self.tools_dir, self.executable)
        if binary is None:
            pytest.skip(SKIP_REASON)

        with tempfile.TemporaryDirectory(prefix="tsdhn-parity-") as raw_dir:
            working_dir = Path(raw_dir)
            self.prepare(case, working_dir)
            run_tool(binary, working_dir, self.args)
            checkpoints = tuple(
                Checkpoint.of(name, self.read_checkpoint(working_dir / name))
                for name in self.checkpoints
            )
        return Trace(case_id=case.id, checkpoints=checkpoints)


def _resolve_executable(explicit: Path | None, executable: str) -> Path | None:
    tools_dir = explicit or _env_tools_dir()
    if tools_dir is None:
        return None
    candidate = tools_dir / executable
    return candidate if candidate.is_file() else None


def _env_tools_dir() -> Path | None:
    value = os.environ.get("TSDHN_TOOLS_DIR")
    return Path(value).resolve() if value else None
