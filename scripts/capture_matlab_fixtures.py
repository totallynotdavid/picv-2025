"""Capture MATLAB checkpoints as committed NumPy fixtures.

Run this script by hand. Pytest reads the resulting fixture through
`FrozenFixtureAdapter` and does not start MATLAB.

Usage:
    uv run python scripts/capture_matlab_fixtures.py fault_plane
    uv run python scripts/capture_matlab_fixtures.py fault_plane --case alaska_1964
    uv run python scripts/capture_matlab_fixtures.py fault_plane --runtime podman

Each parity unit provides `spec.py` and `capture.m` under
`packages/tsdhn/tests/parity/<unit>/`. The script imports `CASES` from
`spec.py`, runs `capture.m`, and converts `checkpoints.mat` to one `.npz` file
per case. Use `--from-mat` to convert a file from a manual MATLAB run.
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

from scipy.io import loadmat

from tsdhn_parity.adapters.frozen_fixture import write_fixture
from tsdhn_parity.cases import Case
from tsdhn_parity.trace import Checkpoint, Trace

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "packages" / "tsdhn" / "tests"
PARITY_DIR = TESTS_DIR / "parity"

MATLAB_IMAGE = "mathworks/matlab:r2026a"
MATLAB_CONFIG_VOLUME = "matlab-config"
MATLAB_CONFIG_MOUNT = "/home/matlab/.matlab/MATLAB_R2026a"


def main() -> None:
    args = _parse_args()
    unit_dir = PARITY_DIR / args.unit
    fixtures_dir = unit_dir / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)

    if args.from_mat is not None:
        if args.case is None:
            raise SystemExit("--from-mat requires --case (one .mat is one case)")
        _write_fixture_from_mat(fixtures_dir, args.case, args.from_mat)
        return

    driver = unit_dir / "capture.m"
    if not driver.is_file():
        raise SystemExit(
            f"{driver} does not exist. Nothing to capture for '{args.unit}'. "
            "Add a capture.m next to spec.py first; see this script's docstring."
        )

    for case in _select_cases(unit_dir, args.case):
        print(f"[{args.unit}] capturing case '{case.id}' ...")
        checkpoints_mat = _run_matlab(driver, case, runtime=args.runtime)
        _write_fixture_from_mat(fixtures_dir, case.id, checkpoints_mat)


def _write_fixture_from_mat(
    fixtures_dir: Path, case_id: str, checkpoints_mat: Path
) -> None:
    trace = _trace_from_mat(case_id, checkpoints_mat)
    out = fixtures_dir / f"{case_id}.npz"
    write_fixture(out, trace)
    print(f"wrote {out}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "unit", help="unit directory name under packages/tsdhn/tests/parity/"
    )
    parser.add_argument(
        "--case", help="capture only this case id (default: every case in spec.py)"
    )
    parser.add_argument("--runtime", default="docker", choices=["docker", "podman"])
    parser.add_argument(
        "--from-mat",
        type=Path,
        default=None,
        help=(
            "skip MATLAB and convert this existing checkpoints.mat instead "
            "(requires --case)"
        ),
    )
    return parser.parse_args()


def _select_cases(unit_dir: Path, only_case_id: str | None) -> list[Case]:
    spec_module = _import_unit_spec(unit_dir.name)
    cases: list[Case] = list(spec_module.CASES)  # type: ignore[attr-defined]
    if only_case_id is None:
        return cases
    matching = [case for case in cases if case.id == only_case_id]
    if not matching:
        raise SystemExit(f"no case '{only_case_id}' in {unit_dir / 'spec.py'}")
    return matching


def _import_unit_spec(unit: str) -> ModuleType:
    # Import through the parity package so relative imports work as they do
    # under pytest.
    sys.path.insert(0, str(TESTS_DIR))
    try:
        return importlib.import_module(f"parity.{unit}.spec")
    finally:
        sys.path.remove(str(TESTS_DIR))


def _run_matlab(driver: Path, case: Case, *, runtime: str) -> Path:
    run_dir = Path(tempfile.mkdtemp(prefix="tsdhn-parity-matlab-"))
    (run_dir / "capture.m").write_text(driver.read_text())
    (run_dir / "case_params.json").write_text(json.dumps(dict(case.params)))

    subprocess.run(
        [
            runtime,
            "run",
            "--rm",
            "--volume",
            f"{run_dir}:/work",
            "--volume",
            f"{MATLAB_CONFIG_VOLUME}:{MATLAB_CONFIG_MOUNT}",
            "--workdir",
            "/work",
            MATLAB_IMAGE,
            "-batch",
            "run('capture.m')",
        ],
        check=True,
    )

    checkpoints_mat = run_dir / "checkpoints.mat"
    if not checkpoints_mat.is_file():
        raise RuntimeError(
            f"capture.m did not produce {checkpoints_mat} for case '{case.id}'"
        )
    return checkpoints_mat


def _trace_from_mat(case_id: str, checkpoints_mat: Path) -> Trace:
    data = loadmat(checkpoints_mat)
    names = [
        name for name in data if not (name.startswith("__") and name.endswith("__"))
    ]
    checkpoints = tuple(Checkpoint.of(name, data[name]) for name in names)
    return Trace(case_id=case_id, checkpoints=checkpoints)


if __name__ == "__main__":
    main()
