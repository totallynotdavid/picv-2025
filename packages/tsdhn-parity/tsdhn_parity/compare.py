from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np

from tsdhn_parity.trace import Checkpoint, Trace

type CheckpointStatus = Literal[
    "match", "diverge", "missing_in_legacy", "missing_in_python"
]


@dataclass(frozen=True)
class Tolerance:
    rtol: float = 1e-4
    atol: float = 1e-9


DEFAULT_TOLERANCE = Tolerance()


@dataclass(frozen=True)
class CheckpointDiff:
    name: str
    status: CheckpointStatus
    max_abs_diff: float | None = None
    max_rel_diff: float | None = None

    @property
    def ok(self) -> bool:
        return self.status == "match"


@dataclass(frozen=True)
class ComparisonResult:
    case_id: str
    diffs: tuple[CheckpointDiff, ...]

    @property
    def first_divergence(self) -> CheckpointDiff | None:
        return next((diff for diff in self.diffs if not diff.ok), None)

    @property
    def ok(self) -> bool:
        return all(diff.ok for diff in self.diffs)


def compare(
    legacy: Trace,
    python: Trace,
    tolerances: Mapping[str, Tolerance] | None = None,
    default: Tolerance = DEFAULT_TOLERANCE,
) -> ComparisonResult:
    """Compare checkpoints by name and keep their first-seen order."""
    tolerances = tolerances or {}
    legacy_by_name = legacy.by_name()
    python_by_name = python.by_name()

    diffs = tuple(
        _diff_checkpoint(
            name,
            legacy_by_name.get(name),
            python_by_name.get(name),
            tolerances.get(name, default),
        )
        for name in _ordered_names(legacy.checkpoints, python.checkpoints)
    )
    return ComparisonResult(case_id=legacy.case_id, diffs=diffs)


def _ordered_names(
    legacy_checkpoints: tuple[Checkpoint, ...],
    python_checkpoints: tuple[Checkpoint, ...],
) -> list[str]:
    seen: dict[str, None] = {}
    for checkpoint in (*legacy_checkpoints, *python_checkpoints):
        seen.setdefault(checkpoint.name, None)
    return list(seen)


def _diff_checkpoint(
    name: str,
    legacy: Checkpoint | None,
    python: Checkpoint | None,
    tolerance: Tolerance,
) -> CheckpointDiff:
    if legacy is None:
        return CheckpointDiff(name=name, status="missing_in_legacy")
    if python is None:
        return CheckpointDiff(name=name, status="missing_in_python")
    if legacy.value.shape != python.value.shape:
        # A shape mismatch cannot use an element-wise comparison.
        return CheckpointDiff(name=name, status="diverge")

    legacy_values = legacy.value.astype(float)
    python_values = python.value.astype(float)
    abs_diff = np.abs(legacy_values - python_values)
    denominator = np.maximum(np.abs(legacy_values), tolerance.atol)

    matches = np.allclose(
        legacy_values, python_values, rtol=tolerance.rtol, atol=tolerance.atol
    )
    return CheckpointDiff(
        name=name,
        status="match" if matches else "diverge",
        max_abs_diff=float(np.max(abs_diff)),
        max_rel_diff=float(np.max(abs_diff / denominator)),
    )
