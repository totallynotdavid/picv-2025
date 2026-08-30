from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from tsdhn_parity.adapters import LegacyAdapter, PythonAdapter
from tsdhn_parity.cases import Case
from tsdhn_parity.compare import CheckpointDiff, ComparisonResult, Tolerance, compare


@dataclass(frozen=True)
class UnitSpec:
    id: str
    cases: Sequence[Case]
    legacy: LegacyAdapter
    python: PythonAdapter
    tolerances: Mapping[str, Tolerance] = field(default_factory=dict)
    default_tolerance: Tolerance = field(default_factory=Tolerance)


def parity_cases(spec: UnitSpec) -> list[Any]:
    """Return pytest parameters named by case ID."""
    return [pytest.param(case, id=case.id) for case in spec.cases]


def assert_parity(spec: UnitSpec, case: Case) -> ComparisonResult:
    """Run both adapters and fail at the first divergent checkpoint."""
    legacy_trace = spec.legacy.run(case)
    python_trace = spec.python.run(case)
    result = compare(
        legacy_trace, python_trace, spec.tolerances, spec.default_tolerance
    )
    divergence = result.first_divergence
    if divergence is not None:
        raise AssertionError(_failure_message(spec, result, divergence))
    return result


def _failure_message(
    spec: UnitSpec, result: ComparisonResult, divergence: CheckpointDiff
) -> str:
    lines = [
        f"parity check failed for unit '{spec.id}', case '{result.case_id}'",
        f"first divergence at checkpoint '{divergence.name}': {divergence.status}",
    ]
    if divergence.max_abs_diff is not None:
        lines.append(f"  max_abs_diff = {divergence.max_abs_diff:.6g}")
    if divergence.max_rel_diff is not None:
        lines.append(f"  max_rel_diff = {divergence.max_rel_diff:.6g}")

    later_diverging = [
        diff.name
        for diff in result.diffs
        if not diff.ok and diff.name != divergence.name
    ]
    if later_diverging:
        lines.append(f"  also diverges later at: {', '.join(later_diverging)}")

    return "\n".join(lines)
