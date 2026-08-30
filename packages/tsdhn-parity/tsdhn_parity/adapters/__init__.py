from typing import Protocol

from tsdhn_parity.adapters.fortran import (
    FortranBinaryAdapter,
    read_checkpoint_text,
    read_fixed_width_grid,
)
from tsdhn_parity.adapters.frozen_fixture import FrozenFixtureAdapter, write_fixture
from tsdhn_parity.adapters.python_callable import PythonCallableAdapter
from tsdhn_parity.cases import Case
from tsdhn_parity.trace import Trace

__all__ = [
    "FortranBinaryAdapter",
    "FrozenFixtureAdapter",
    "LegacyAdapter",
    "PythonAdapter",
    "PythonCallableAdapter",
    "read_checkpoint_text",
    "read_fixed_width_grid",
    "write_fixture",
]


class LegacyAdapter(Protocol):
    def run(self, case: Case) -> Trace:
        """Replay the reference implementation and record its checkpoints."""


class PythonAdapter(Protocol):
    def run(self, case: Case) -> Trace:
        """Run the ported implementation and record its checkpoints."""
