"""Compare the Python Okada port with the compiled Fortran output.

Both sides write F9.3 grids, so the comparison reads the formatted files.
The explicit tolerance accounts for float32 rounding and the 0.001 output
quantization.
"""

import tempfile
from pathlib import Path
from typing import Any

from tsdhn.deform import clip_anomalous_values, compute_deform_grid, write_deform_grid
from tsdhn_parity import (
    Case,
    FortranBinaryAdapter,
    OnCheckpoint,
    PythonCallableAdapter,
    Tolerance,
    UnitSpec,
    read_fixed_width_grid,
)

_ALASKA_1964_WINDOW = {
    "IDS": 1032,
    "IDE": 1249,
    "JDS": 1872,
    "JDE": 2056,
    "IA": 2461,
    "JA": 2056,
}

CASES = [
    Case(
        id="alaska_1964",
        params={
            "I0": 1180,
            "J0": 1988,
            "D0": 11.965752308065987,  # slip (m), using the legacy rigidity
            "L0": 575439.9373371573,  # length (m)
            "W0": 144543.97707459278,  # width (m)
            "TH": 247.0,  # strike / azimuth (deg)
            "DL": 18.0,  # dip (deg)
            "RD": 90.0,  # rake (degrees)
            "HH": 5000.0,  # depth to top of fault (m)
            **_ALASKA_1964_WINDOW,
        },
    ),
    Case(
        id="alaska_1964_rd45",
        params={
            "I0": 1180,
            "J0": 1988,
            "D0": 11.965752308065987,
            "L0": 575439.9373371573,
            "W0": 144543.97707459278,
            "TH": 247.0,
            "DL": 18.0,
            "RD": 45.0,  # covers a different strike-slip/dip-slip split
            "HH": 5000.0,
            **_ALASKA_1964_WINDOW,
        },
    ),
]

# The deformation step ignores the grid dimensions after the requested window.
_UNUSED_PARAMS = ("IA", "JA")
_READ_GRID = read_fixed_width_grid(9)  # Legacy deformation grids use F9.3 fields.


def _prepare(case: Case, working_dir: Path) -> None:
    p = case.params
    (working_dir / "pfalla.inp").write_text(
        f"{p['I0']} {p['J0']} {p['D0']} {p['L0']} {p['W0']} "
        f"{p['TH']} {p['DL']} {p['RD']} {p['HH']}\n"
    )
    (working_dir / "xyo.dat").write_text(
        f"{p['IDS']} {p['IDE']} {p['JDS']} {p['JDE']} {p['IA']} {p['JA']}\n"
    )


LEGACY = FortranBinaryAdapter(
    executable="deform",
    checkpoints=("deform_a.grd",),
    prepare=_prepare,
    read_checkpoint=_READ_GRID,
)


def _run(on_checkpoint: OnCheckpoint, **kwargs: Any) -> None:
    params = {k: v for k, v in kwargs.items() if k not in _UNUSED_PARAMS}
    grid = clip_anomalous_values(compute_deform_grid(**params))
    with tempfile.TemporaryDirectory(prefix="tsdhn-parity-deform-") as raw_dir:
        path = Path(raw_dir) / "deform_a.grd"
        write_deform_grid(path, grid)
        on_checkpoint("deform_a.grd", _READ_GRID(path))


SPEC = UnitSpec(
    id="deform",
    cases=CASES,
    legacy=LEGACY,
    python=PythonCallableAdapter(fn=_run, result_checkpoint=None),
    tolerances={"deform_a.grd": Tolerance(atol=0.02)},
)
