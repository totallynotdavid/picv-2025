from collections.abc import Mapping, Sequence

from tsdhn_parity.cases import Case, ParamValue, exhaustive, pairwise


def test_exhaustive_is_full_cartesian_product() -> None:
    cases = exhaustive(a=[1, 2], b=["x", "y", "z"])

    assert len(cases) == 6
    assert all(isinstance(case, Case) for case in cases)
    seen = {(case.params["a"], case.params["b"]) for case in cases}
    assert seen == {(1, "x"), (1, "y"), (1, "z"), (2, "x"), (2, "y"), (2, "z")}


def test_exhaustive_case_ids_are_unique() -> None:
    cases = exhaustive(a=[1, 2], b=[1, 2])

    assert len({case.id for case in cases}) == len(cases)


def test_pairwise_covers_every_two_parameter_combination() -> None:
    value_lists: dict[str, Sequence[ParamValue]] = {
        "a": [1, 2],
        "b": ["x", "y"],
        "c": [True, False],
    }

    cases = pairwise(**value_lists)

    assert len(cases) < len(exhaustive(**value_lists))
    assert _every_pair_covered(cases, value_lists)


def test_pairwise_with_fewer_than_two_params_matches_exhaustive() -> None:
    assert pairwise(a=[1, 2, 3]) == exhaustive(a=[1, 2, 3])


def _every_pair_covered(
    cases: list[Case], value_lists: Mapping[str, Sequence[ParamValue]]
) -> bool:
    names = list(value_lists)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            required = {
                (a, b) for a in value_lists[names[i]] for b in value_lists[names[j]]
            }
            covered = {(case.params[names[i]], case.params[names[j]]) for case in cases}
            if not required <= covered:
                return False
    return True
