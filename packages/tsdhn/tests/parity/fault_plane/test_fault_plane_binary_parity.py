import pytest

from tsdhn_parity import Case, assert_parity, parity_cases

from .spec_binary import SPEC


@pytest.mark.parametrize("case", parity_cases(SPEC))
def test_fault_plane_dislocation_matches_binary(case: Case) -> None:
    assert_parity(SPEC, case)
