from pathlib import Path

import numpy as np
import pytest

import tsdhn.deform as deform_module
from tsdhn.deform import (
    _udip_gz,
    _ustrike_fz,
    clip_anomalous_values,
    compute_deform_grid,
    write_deform_grid,
)


def test_clip_anomalous_values_uses_greater_equal_threshold() -> None:
    # Values at or beyond 20 m are outliers, not values subject to a small
    # value floor. Keep the examples away from the float32 boundary.
    grid = np.array([19.9, 20.1, -19.9, -20.1, 0.5], dtype=np.float32)
    result = clip_anomalous_values(grid)
    np.testing.assert_allclose(result, [19.9, 0.0, -19.9, 0.0, 0.5], atol=1e-4)


def test_ustrike_fz_and_udip_gz_finite_away_from_fault() -> None:
    q = np.array([1234.5], dtype=np.float32)
    cs = np.float32(0.9)
    sn = np.float32(0.3)
    xi = np.array([500.0], dtype=np.float32)
    et = np.array([300.0], dtype=np.float32)
    eps = np.float32(1.0e-8)
    rmu = np.float32(0.5)

    fz = _ustrike_fz(eps, rmu, q, cs, sn, xi, et)
    gz = _udip_gz(eps, rmu, q, cs, sn, xi, et)
    assert np.all(np.isfinite(fz))
    assert np.all(np.isfinite(gz))


def test_udip_gz_handles_q_near_zero() -> None:
    q = np.array([0.0], dtype=np.float32)
    cs = np.float32(0.9)
    sn = np.float32(0.3)
    xi = np.array([100.0], dtype=np.float32)
    et = np.array([200.0], dtype=np.float32)
    eps = np.float32(1.0e-8)
    rmu = np.float32(0.5)

    gz = _udip_gz(eps, rmu, q, cs, sn, xi, et)
    assert np.all(np.isfinite(gz))


def test_ustrike_fz_handles_ret_singular() -> None:
    # Exercise RET=R+ET=0, including the RDH branch.
    q = np.array([0.0], dtype=np.float32)
    cs = np.float32(0.9)
    sn = np.float32(0.3)
    xi = np.array([0.0], dtype=np.float32)
    et = np.array([-5.0], dtype=np.float32)
    eps = np.float32(1.0e-8)
    rmu = np.float32(0.5)

    fz = _ustrike_fz(eps, rmu, q, cs, sn, xi, et)
    assert np.all(np.isfinite(fz))


def _read_fixed_width_9(path: Path) -> np.ndarray:
    # Independent reimplementation (not tsdhn_parity's reader) so this
    # round-trip test doesn't share a bug with the code it's checking.
    return np.array(
        [
            [float(line[i : i + 9]) for i in range(0, len(line), 9)]
            for line in path.read_text().splitlines()
        ]
    )


def test_write_deform_grid_round_trips_fixed_width_9(tmp_path: Path) -> None:
    grid = np.array([[1.5, -0.001, 123.457], [0.02, -12.3, 0.0]], dtype=np.float32)
    path = tmp_path / "deform_a.grd"
    write_deform_grid(path, grid)
    read_back = _read_fixed_width_9(path)
    assert read_back.shape == grid.shape
    np.testing.assert_allclose(read_back, grid, atol=5e-4)


def test_compute_deform_grid_alaska_1964_shape() -> None:
    grid = compute_deform_grid(
        I0=1180,
        J0=1988,
        D0=11.965752308065987,
        L0=575439.9373371573,
        W0=144543.97707459278,
        TH=247.0,
        DL=18.0,
        RD=90.0,
        HH=5000.0,
        IDS=1032,
        IDE=1249,
        JDS=1872,
        JDE=2056,
    )
    expected_rows = 1249 - 1032 + 1
    expected_cols = 2056 - 1872 + 1
    assert grid.shape == (expected_rows, expected_cols)
    assert np.all(np.isfinite(grid))
    assert grid.dtype == np.float32


def test_compute_deform_grid_accepts_a_zero_strike() -> None:
    grid = compute_deform_grid(
        I0=1180,
        J0=1988,
        D0=11.965752308065987,
        L0=575439.9373371573,
        W0=144543.97707459278,
        TH=0.0,
        DL=18.0,
        RD=90.0,
        HH=5000.0,
        IDS=1032,
        IDE=1034,
        JDS=1872,
        JDE=1874,
    )

    assert grid.shape == (3, 3)
    assert np.all(np.isfinite(grid))


def test_run_deform_reads_workspace_inputs_and_clips_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pfalla.inp").write_text(
        "1180 1987 11.96 575439.9 144543.9 247 8 90 1941.7\n",
        encoding="utf-8",
    )
    (tmp_path / "xyo.dat").write_text("1 2 1 2\n", encoding="utf-8")
    monkeypatch.setattr(
        deform_module,
        "compute_deform_grid",
        lambda **kwargs: np.array([[19.5, 20.0], [-20.0, -19.5]], dtype=np.float32),
    )

    deform_module.run_deform(tmp_path)

    np.testing.assert_allclose(
        np.loadtxt(tmp_path / "deform_a.grd"),
        [[19.5, 0.0], [0.0, -19.5]],
    )
