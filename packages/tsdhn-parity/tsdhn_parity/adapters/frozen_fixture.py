from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tsdhn_parity.cases import Case
from tsdhn_parity.trace import Checkpoint, Trace

_ORDER_KEY = "__order__"


@dataclass(frozen=True)
class FrozenFixtureAdapter:
    """Load a captured MATLAB trace from an `.npz` fixture.

    The fixture stores checkpoint order explicitly.
    """

    fixtures_dir: Path

    def run(self, case: Case) -> Trace:
        path = self.fixtures_dir / f"{case.id}.npz"
        if not path.is_file():
            raise FileNotFoundError(
                f"No captured fixture for case '{case.id}' at {path}. "
                "Run scripts/capture_matlab_fixtures.py to generate it."
            )
        with np.load(path) as data:
            order = list(data[_ORDER_KEY])
            checkpoints = tuple(Checkpoint.of(name, data[name]) for name in order)
        return Trace(case_id=case.id, checkpoints=checkpoints)


def write_fixture(path: Path, trace: Trace) -> None:
    """Write a trace as a compressed NumPy fixture."""
    order = np.array([checkpoint.name for checkpoint in trace.checkpoints])
    arrays = {checkpoint.name: checkpoint.value for checkpoint in trace.checkpoints}
    arrays[_ORDER_KEY] = order
    path.parent.mkdir(parents=True, exist_ok=True)
    # mypy can't prove `arrays` excludes the "allow_pickle" keyword savez_compressed
    # also accepts, so it checks **arrays against that bool-typed parameter too.
    np.savez_compressed(path, **arrays)  # type: ignore[arg-type]
