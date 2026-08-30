"""Compare the Python shallow-water solver with the compiled Fortran output.

This test runs the full integration and is marked for explicit parity runs.
The output files use fixed-width fields, so the readers below use their
declared column widths. Tolerances account for output quantization and
float32 rounding during the integration.
"""

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from tsdhn.deform import run_deform
from tsdhn.fault_plane import run_fault_plane
from tsdhn.tsunami import run_tsunami
from tsdhn.utils.file_utils import prepare_simulation_workspace
from tsdhn_parity import (
    Case,
    FortranBinaryAdapter,
    OnCheckpoint,
    PythonCallableAdapter,
    Tolerance,
    UnitSpec,
    read_fixed_width_grid,
)

from ..conftest import MODEL_DIR

# Same scenario as the fault_plane/deform legs and test_numerical_values.py.
CASES = [
    Case(
        id="alaska_1964",
        params={
            "Mw": 9.0,
            "h": 12.0,
            "lat0": 56.0,
            "lon0": -156.0,
            "hhmm": "0000",
            "dia": "23",
        },
    ),
]

# model/tsunami1.for: green.dat is WRITE(4,'(F7.1,100F7.3)') -> 7-char
# columns; zmax_a.grd is FORMAT(4000F8.3) -> 8-char columns.
_READERS: dict[str, Callable[[Path], np.ndarray]] = {
    "green.dat": read_fixed_width_grid(7),
    "zmax_a.grd": read_fixed_width_grid(8),
}

_CHECKPOINTS = ("zfolder/green.dat", "zfolder/zmax_a.grd")

# Chained-input workspaces per scenario, built once and reused by both
# adapters so legacy and python integrate the exact same initial condition.
_chained: dict[str, Path] = {}


def _read_checkpoint(path: Path) -> np.ndarray:
    return _READERS[path.name](path)


def _write_hypo_dat(working_dir: Path, params: dict[str, Any]) -> None:
    (working_dir / "hypo.dat").write_text(
        "\n".join(
            [
                str(params["hhmm"]),
                f"{params['lon0']:.2f}",
                f"{params['lat0']:.2f}",
                f"{params['h']:.0f}",
                f"{params['Mw']:.1f}",
            ]
        )
    )


def _params_key(params: dict[str, Any]) -> str:
    return repr(sorted(params.items()))


def _chained_inputs(params: dict[str, Any]) -> Path:
    """Runs the Python fault_plane + deform ports once per scenario in a
    session-lifetime scratch dir; returns the dir holding deform_a.grd +
    xyo.dat."""
    key = _params_key(params)
    if key not in _chained:
        workspace = Path(tempfile.mkdtemp(prefix="tsdhn-parity-tsunami-chain-"))
        prepare_simulation_workspace(MODEL_DIR, workspace)
        _write_hypo_dat(workspace, params)
        run_fault_plane(workspace)
        run_deform(workspace)
        _chained[key] = workspace
    return _chained[key]


def _seed_tsunami_workspace(params: dict[str, Any], working_dir: Path) -> None:
    chained = _chained_inputs(params)
    (working_dir / "bathy").mkdir(parents=True, exist_ok=True)
    (working_dir / "zfolder").mkdir(exist_ok=True)
    shutil.copy2(
        MODEL_DIR / "bathy" / "grid_a.grd", working_dir / "bathy" / "grid_a.grd"
    )
    shutil.copy2(MODEL_DIR / "tidal.dat", working_dir / "tidal.dat")
    shutil.copy2(chained / "deform_a.grd", working_dir / "deform_a.grd")
    shutil.copy2(chained / "xyo.dat", working_dir / "xyo.dat")


def _prepare(case: Case, working_dir: Path) -> None:
    _seed_tsunami_workspace(dict(case.params), working_dir)


def _run(on_checkpoint: OnCheckpoint, **kwargs: Any) -> None:
    with tempfile.TemporaryDirectory(prefix="tsdhn-parity-tsunami-") as raw_dir:
        working_dir = Path(raw_dir)
        _seed_tsunami_workspace(kwargs, working_dir)
        run_tsunami(working_dir)
        for name in _CHECKPOINTS:
            on_checkpoint(name, _read_checkpoint(working_dir / name))


LEGACY = FortranBinaryAdapter(
    executable="tsunami",
    checkpoints=_CHECKPOINTS,
    prepare=_prepare,
    read_checkpoint=_read_checkpoint,
)

SPEC = UnitSpec(
    id="tsunami",
    cases=CASES,
    legacy=LEGACY,
    python=PythonCallableAdapter(fn=_run, result_checkpoint=None),
    tolerances={
        "zfolder/green.dat": Tolerance(atol=0.002),
        "zfolder/zmax_a.grd": Tolerance(atol=0.02),
    },
)
