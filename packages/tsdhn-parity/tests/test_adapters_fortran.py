from pathlib import Path

import numpy as np
import pytest

from tsdhn.utils.file_utils import make_executable
from tsdhn_parity.adapters.fortran import FortranBinaryAdapter, read_fixed_width_grid
from tsdhn_parity.cases import Case

# Use the same copy, execute, and read-back contract as a legacy binary.
FIXTURE_PROGRAM = """#!/bin/sh
value=$(cat input.txt)
echo $((value * 2)) > output.txt
"""


@pytest.fixture
def tools_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "tools"
    directory.mkdir()
    program = directory / "double"
    program.write_text(FIXTURE_PROGRAM)
    make_executable(program)
    return directory


def _write_input(case: Case, working_dir: Path) -> None:
    (working_dir / "input.txt").write_text(str(case.params["value"]))


def test_runs_binary_and_reads_declared_checkpoints_in_order(tools_dir: Path) -> None:
    adapter = FortranBinaryAdapter(
        executable="double",
        checkpoints=("output.txt",),
        prepare=_write_input,
        tools_dir=tools_dir,
    )

    trace = adapter.run(Case(id="value_21", params={"value": 21}))

    assert trace.case_id == "value_21"
    assert [checkpoint.name for checkpoint in trace.checkpoints] == ["output.txt"]
    assert np.asarray(trace.checkpoints[0].value).item() == pytest.approx(42.0)


def test_skips_when_executable_is_missing_from_tools_dir(tmp_path: Path) -> None:
    empty_tools_dir = tmp_path / "empty"
    empty_tools_dir.mkdir()
    adapter = FortranBinaryAdapter(
        executable="double",
        checkpoints=("output.txt",),
        prepare=_write_input,
        tools_dir=empty_tools_dir,
    )

    with pytest.raises(pytest.skip.Exception):
        adapter.run(Case(id="value_1", params={"value": 1}))


def test_read_fixed_width_grid_handles_touching_columns(tmp_path: Path) -> None:
    # Fixed-width output can place adjacent fields without a separator.
    path = tmp_path / "grid.dat"
    path.write_text("123.4-56.7\n  0.0  1.2\n")

    grid = read_fixed_width_grid(5)(path)

    assert grid.tolist() == [[123.4, -56.7], [0.0, 1.2]]
