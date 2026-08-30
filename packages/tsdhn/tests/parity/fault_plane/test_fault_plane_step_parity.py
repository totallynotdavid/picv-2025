import pytest

from tsdhn_parity import Case, assert_parity, parity_cases

from .spec_binary import STEP_SPEC


@pytest.mark.parametrize("case", parity_cases(STEP_SPEC))
def test_fault_plane_step_matches_binary(case: Case) -> None:
    assert_parity(STEP_SPEC, case)
