from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations, product

type ParamValue = float | int | str | bool
type PairKey = tuple[int, ParamValue, int, ParamValue]


@dataclass(frozen=True)
class Case:
    id: str
    params: Mapping[str, ParamValue]


def exhaustive(**value_lists: Sequence[ParamValue]) -> list[Case]:
    """Return every combination of the named parameter values."""
    names = tuple(value_lists)
    return [
        _case_from_values(names, values)
        for values in product(*(value_lists[name] for name in names))
    ]


def pairwise(**value_lists: Sequence[ParamValue]) -> list[Case]:
    """Return cases that cover every pair of parameter values."""
    names = tuple(value_lists)
    if len(names) < 2:
        return exhaustive(**value_lists)

    values = {name: tuple(value_lists[name]) for name in names}
    uncovered = _all_pairs(names, values)
    covering_cases: list[tuple[ParamValue, ...]] = []
    while uncovered:
        seed = next(iter(uncovered))
        combo = _greedy_combination(names, values, uncovered, seed)
        covering_cases.append(combo)
        uncovered -= _pairs_in(names, combo)

    return [_case_from_values(names, combo) for combo in covering_cases]


def _case_from_values(names: tuple[str, ...], values: tuple[ParamValue, ...]) -> Case:
    params = dict(zip(names, values, strict=True))
    case_id = "_".join(f"{name}={params[name]}" for name in names)
    return Case(id=case_id, params=params)


def _all_pairs(
    names: tuple[str, ...], values: Mapping[str, tuple[ParamValue, ...]]
) -> set[PairKey]:
    return {
        (i, a, j, b)
        for i, j in combinations(range(len(names)), 2)
        for a in values[names[i]]
        for b in values[names[j]]
    }


def _pairs_in(names: tuple[str, ...], combo: tuple[ParamValue, ...]) -> set[PairKey]:
    return {(i, combo[i], j, combo[j]) for i, j in combinations(range(len(names)), 2)}


def _greedy_combination(
    names: tuple[str, ...],
    values: Mapping[str, tuple[ParamValue, ...]],
    uncovered: set[PairKey],
    seed: PairKey,
) -> tuple[ParamValue, ...]:
    """Build one case that covers `seed` and as many other pairs as possible."""
    seed_i, seed_a, seed_j, seed_b = seed
    assigned: dict[int, ParamValue] = {seed_i: seed_a, seed_j: seed_b}

    for index, name in enumerate(names):
        if index not in assigned:
            assigned[index] = _best_value(values[name], index, assigned, uncovered)

    return tuple(assigned[index] for index in range(len(names)))


def _best_value(
    candidates: tuple[ParamValue, ...],
    index: int,
    assigned: Mapping[int, ParamValue],
    uncovered: set[PairKey],
) -> ParamValue:
    def newly_covered(candidate: ParamValue) -> int:
        return sum(
            1
            for other_index, other_value in assigned.items()
            if _pair_key(other_index, other_value, index, candidate) in uncovered
        )

    return max(candidates, key=newly_covered)


def _pair_key(i: int, a: ParamValue, j: int, b: ParamValue) -> PairKey:
    return (i, a, j, b) if i < j else (j, b, i, a)
