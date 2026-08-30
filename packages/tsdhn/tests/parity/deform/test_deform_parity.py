import pytest

from tsdhn_parity import Case, assert_parity, parity_cases

from .spec import SPEC


@pytest.mark.parametrize("case", parity_cases(SPEC))
def test_deform_matches_binary(case: Case) -> None:
    assert_parity(SPEC, case)
