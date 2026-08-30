from tsdhn_parity.compare import Tolerance, compare
from tsdhn_parity.trace import Checkpoint, Trace


def _trace(case_id: str, **checkpoints: object) -> Trace:
    return Trace(
        case_id=case_id,
        checkpoints=tuple(
            Checkpoint.of(name, value) for name, value in checkpoints.items()
        ),
    )


def test_matching_traces_compare_ok() -> None:
    legacy = _trace("c1", step_a=[1.0, 2.0], step_b=3.0)
    python = _trace("c1", step_a=[1.0, 2.0], step_b=3.0)

    result = compare(legacy, python)

    assert result.ok
    assert result.first_divergence is None


def test_diverging_checkpoint_is_reported() -> None:
    legacy = _trace("c1", step_a=[1.0, 2.0], step_b=3.0)
    python = _trace("c1", step_a=[1.0, 2.0], step_b=30.0)

    result = compare(legacy, python)

    assert not result.ok
    divergence = result.first_divergence
    assert divergence is not None
    assert divergence.name == "step_b"
    assert divergence.status == "diverge"
    assert divergence.max_abs_diff == 27.0


def test_earliest_divergence_wins_when_multiple_checkpoints_diverge() -> None:
    legacy = _trace("c1", step_a=1.0, step_b=1.0)
    python = _trace("c1", step_a=9.0, step_b=9.0)

    result = compare(legacy, python)

    divergence = result.first_divergence
    assert divergence is not None
    assert divergence.name == "step_a"


def test_missing_checkpoint_on_either_side_is_reported() -> None:
    legacy = _trace("c1", only_legacy=1.0)
    python = _trace("c1", only_python=1.0)

    result = compare(legacy, python)

    statuses = {diff.name: diff.status for diff in result.diffs}
    assert statuses["only_legacy"] == "missing_in_python"
    assert statuses["only_python"] == "missing_in_legacy"


def test_shape_mismatch_is_a_divergence_not_a_crash() -> None:
    legacy = _trace("c1", grid=[1.0, 2.0, 3.0])
    python = _trace("c1", grid=[1.0, 2.0])

    result = compare(legacy, python)

    divergence = result.first_divergence
    assert divergence is not None
    assert divergence.status == "diverge"
    assert divergence.max_abs_diff is None


def test_per_checkpoint_tolerance_overrides_default() -> None:
    legacy = _trace("c1", noisy=1.0)
    python = _trace("c1", noisy=1.2)

    tight = compare(legacy, python, default=Tolerance(rtol=1e-6))
    loose = compare(
        legacy,
        python,
        tolerances={"noisy": Tolerance(rtol=0.5)},
        default=Tolerance(rtol=1e-6),
    )

    assert not tight.ok
    assert loose.ok
