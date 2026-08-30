"""Compare rectangle geometry with the captured MATLAB trace.

The binary parity spec covers the grid lookup conversion and full output
files. This spec compares only the geometry intermediates shared with MATLAB.
"""

from pathlib import Path
from typing import Any

from tsdhn.calculator import calculate_rectangle_parameters
from tsdhn_parity import (
    Case,
    FrozenFixtureAdapter,
    OnCheckpoint,
    PythonCallableAdapter,
    UnitSpec,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# These parameters match calculate_rectangle_parameters's signature.
CASES = [
    Case(
        id="alaska_1964",
        params={
            "L": 575.439937,
            "W": 144.543977,
            "lon0": -156.0,
            "lat0": 56.0,
            "azimuth": 247.0,
            "dip": 18.0,
        },
    ),
]

GEOMETRY_CHECKPOINTS = ("L1", "W1", "beta", "alfa", "h1", "a1", "b1")


def _geometry_only(on_checkpoint: OnCheckpoint, **kwargs: Any) -> None:
    def filtered(name: str, value: Any) -> None:
        if name in GEOMETRY_CHECKPOINTS:
            on_checkpoint(name, value)

    calculate_rectangle_parameters(on_checkpoint=filtered, **kwargs)


SPEC = UnitSpec(
    id="fault_plane",
    cases=CASES,
    legacy=FrozenFixtureAdapter(fixtures_dir=FIXTURES_DIR),
    python=PythonCallableAdapter(fn=_geometry_only, result_checkpoint=None),
)
