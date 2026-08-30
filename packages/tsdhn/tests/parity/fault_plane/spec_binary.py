"""Compare fault-plane calculations with the compiled Fortran output.

The executable is the reference for dislocation and for the full
`pfalla.inp`, `xyo.dat`, and `meca.dat` step outputs. The MATLAB spec covers
only the geometry intermediates that share the same convention.
"""

import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from tsdhn.calculator import TsunamiCalculator
from tsdhn.domain import EarthquakeInput
from tsdhn.fault_plane import run_fault_plane
from tsdhn.utils.file_utils import prepare_simulation_workspace
from tsdhn_parity import (
    Case,
    FortranBinaryAdapter,
    OnCheckpoint,
    PythonCallableAdapter,
    UnitSpec,
)

from ..conftest import MODEL_DIR

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


def _write_hypo_dat(working_dir: Path, params: Mapping[str, Any]) -> None:
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


def _prepare(case: Case, working_dir: Path) -> None:
    prepare_simulation_workspace(MODEL_DIR, working_dir)
    _write_hypo_dat(working_dir, case.params)


def _read_slip(path: Path) -> np.ndarray:
    # List-directed Fortran output may wrap. Read whitespace-separated tokens.
    tokens = path.read_text().split()
    return np.asarray(float(tokens[2]))


def _run(on_checkpoint: OnCheckpoint, **kwargs: Any) -> None:
    calculator = TsunamiCalculator(MODEL_DIR)
    response = calculator.calculate_earthquake_parameters(EarthquakeInput(**kwargs))
    on_checkpoint("pfalla.inp", np.asarray(response.dislocation))


SPEC = UnitSpec(
    id="fault_plane_binary",
    cases=CASES,
    legacy=FortranBinaryAdapter(
        executable="fault_plane",
        checkpoints=("pfalla.inp",),
        prepare=_prepare,
        read_checkpoint=_read_slip,
    ),
    python=PythonCallableAdapter(fn=_run, result_checkpoint=None),
)


_STEP_CHECKPOINTS = ("pfalla.inp", "xyo.dat", "meca.dat")


def _read_fault_plane_checkpoint(path: Path) -> np.ndarray:
    # List-directed Fortran output may wrap. Read whitespace-separated tokens.
    tokens = path.read_text().split()
    if path.name == "pfalla.inp":
        return np.asarray([float(t) for t in tokens[:9]])
    if path.name == "xyo.dat":
        return np.asarray([float(t) for t in tokens[:4]])
    if path.name == "meca.dat":
        return np.asarray([float(t) for t in tokens[:7]])
    raise ValueError(f"no checkpoint reader for {path.name}")


def _run_step(on_checkpoint: OnCheckpoint, **kwargs: Any) -> None:
    with tempfile.TemporaryDirectory(prefix="tsdhn-parity-") as raw_dir:
        working_dir = Path(raw_dir)
        prepare_simulation_workspace(MODEL_DIR, working_dir)
        _write_hypo_dat(working_dir, kwargs)
        run_fault_plane(working_dir)
        for name in _STEP_CHECKPOINTS:
            on_checkpoint(name, _read_fault_plane_checkpoint(working_dir / name))


STEP_SPEC = UnitSpec(
    id="fault_plane_step",
    cases=CASES,
    legacy=FortranBinaryAdapter(
        executable="fault_plane",
        checkpoints=_STEP_CHECKPOINTS,
        prepare=_prepare,
        read_checkpoint=_read_fault_plane_checkpoint,
    ),
    python=PythonCallableAdapter(fn=_run_step, result_checkpoint=None),
)
