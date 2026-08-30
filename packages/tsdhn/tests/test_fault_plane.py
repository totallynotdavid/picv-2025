from pathlib import Path

import numpy as np
import pytest

from tsdhn.fault_plane import (
    _grid_window,
    _nearest_mechanism,
    _recompute_depth,
    _to_0_360,
    _write_meca_dat,
    _write_pfalla_inp,
    _write_xyo_dat,
    run_fault_plane,
)
from tsdhn.utils.file_utils import prepare_simulation_workspace

MODEL_DIR = Path(__file__).resolve().parents[3] / "model"


def test_to_0_360_shifts_only_negative_longitudes() -> None:
    assert _to_0_360(-156.0) == pytest.approx(204.0)
    assert _to_0_360(156.0) == pytest.approx(156.0)
    assert _to_0_360(0.0) == pytest.approx(0.0)


def test_grid_window_truncates_target_before_snapping() -> None:
    # fault_plane.f90's IDS/IDE/JDS/JDE are implicitly INTEGER (I/J-prefix
    # rule), so the real-valued target truncates toward zero *before* the
    # grid-snap loop runs. A grid spaced finer than 1 degree makes the
    # truncation's effect on the chosen index observable directly: a target
    # of 10.9 must snap to the cell nearest 10 (truncated), not 11 (rounded).
    xa = np.array([9.0, 10.0, 11.0, 12.0])
    ya = np.array([9.0, 10.0, 11.0, 12.0])
    # xep=10.9, off=0.0 -> IDS target truncates int(10.9)=10, not round(10.9)=11.
    ids, ide, jds, jde = _grid_window(xa, ya, xep=10.9, yep=10.9, l_km=0.0, mw=9.0)
    assert (ids, ide, jds, jde) == (2, 2, 2, 2)


def test_nearest_mechanism_matches_real_mecfoc_alaska_1964() -> None:
    # Independently corroborated by the real, git-tracked model/pfalla.inp
    # and model/meca.dat, which both show Az=247.0, dip=8.0 for this case.
    mecfoc = np.loadtxt(MODEL_DIR / "mecfoc.dat")
    az, dip = _nearest_mechanism(mecfoc, xep=204.0, yep=56.0)
    assert az == pytest.approx(247.0)
    assert dip == pytest.approx(8.0)


def test_recompute_depth_clamps_negative_to_5000() -> None:
    # fault_plane.f90:106-108 -- if the recomputed depth to the fault's
    # upper edge goes negative, clamp to a fixed 5000m floor.
    h_m = _recompute_depth(
        lon0=-156.0, lat0=56.0, xo=-153.36, yo=56.42, zep_km=0.1, az=247.0, dip=8.0
    )
    assert h_m == pytest.approx(5000.0)


def test_write_pfalla_inp_is_nine_whitespace_tokens(tmp_path: Path) -> None:
    path = tmp_path / "pfalla.inp"
    _write_pfalla_inp(
        path, 1180, 1987, 11.96, 575439.9, 144543.9, 247.0, 8.0, 90.0, 1941.7
    )
    tokens = path.read_text().split()
    assert len(tokens) == 9
    assert int(tokens[0]) == 1180
    assert int(tokens[1]) == 1987


def test_write_xyo_dat_includes_trailing_ia_ja_padding(tmp_path: Path) -> None:
    path = tmp_path / "xyo.dat"
    _write_xyo_dat(path, 1021, 1246, 1861, 2056)
    tokens = path.read_text().split()
    assert tokens == ["1021", "1246", "1861", "2056", "2461", "2056"]


def test_write_meca_dat_matches_real_captured_format(tmp_path: Path) -> None:
    # Byte-for-byte against the real, git-tracked model/meca.dat for the
    # alaska_1964 scenario.
    path = tmp_path / "meca.dat"
    _write_meca_dat(path, 204.0, 56.0, 12.0, 247.0, 8.0, 9.0, "0000")
    real = (MODEL_DIR / "meca.dat").read_text().strip()
    assert path.read_text().strip() == real


def test_run_fault_plane_matches_real_captured_alaska_1964(tmp_path: Path) -> None:
    # Compare the Python port with the checked-in reference files.
    prepare_simulation_workspace(MODEL_DIR, tmp_path)
    (tmp_path / "hypo.dat").write_text(
        "\n".join(["0000", "-156.00", "56.00", "12", "9.0"])
    )

    run_fault_plane(tmp_path)

    (
        real_i0,
        real_j0,
        real_slip,
        real_l,
        real_w,
        real_az,
        real_dip,
        real_rake,
        real_h,
    ) = (float(t) for t in (MODEL_DIR / "pfalla.inp").read_text().split())
    (
        mine_i0,
        mine_j0,
        mine_slip,
        mine_l,
        mine_w,
        mine_az,
        mine_dip,
        mine_rake,
        mine_h,
    ) = (float(t) for t in (tmp_path / "pfalla.inp").read_text().split())
    assert mine_i0 == real_i0
    assert mine_j0 == real_j0
    assert mine_az == real_az
    assert mine_dip == real_dip
    assert mine_rake == real_rake
    np.testing.assert_allclose(
        [mine_slip, mine_l, mine_w, mine_h],
        [real_slip, real_l, real_w, real_h],
        rtol=2e-4,
    )

    assert (tmp_path / "xyo.dat").read_text().split() == (
        MODEL_DIR / "xyo.dat"
    ).read_text().split()
    assert (tmp_path / "meca.dat").read_text().strip() == (
        MODEL_DIR / "meca.dat"
    ).read_text().strip()
