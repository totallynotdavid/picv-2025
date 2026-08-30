import math
from pathlib import Path

import numpy as np
import pytest

import tsdhn.tsunami as tsunami_module
from tsdhn.tsunami import (
    _bout,
    _hmn,
    _mass,
    _mmnt,
    _prelim,
    _read_deform_a,
    _read_grid_a,
    _read_tidal_dat,
    _read_xyo_dat,
    _write_green_dat,
    _write_zmax_a,
    run_tsunami,
)

MODEL_DIR = Path(__file__).resolve().parents[3] / "model"


def test_hmn_staggered_averages_and_edges() -> None:
    h = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], dtype=np.float32)
    hm, hn = _hmn(h)
    np.testing.assert_array_equal(
        hm, np.array([[2.0, 3.0], [4.0, 5.0], [5.0, 6.0]], dtype=np.float32)
    )
    np.testing.assert_array_equal(
        hn, np.array([[1.5, 2.0], [3.5, 4.0], [5.5, 6.0]], dtype=np.float32)
    )


def test_prelim_factors_match_formulas() -> None:
    hm = np.full((3, 4), 1000.0, dtype=np.float32)
    hn = np.full((3, 4), 2000.0, dtype=np.float32)
    rx, cj, xx, yy = _prelim(hm, hn)

    delta = 240.0 / 3600.0
    da = math.pi * delta / 180.0
    rz0 = math.radians(-76.006)
    assert rx[0] == pytest.approx(3.0 / (6.37e6 * math.cos(rz0) * da), rel=1e-5)
    assert cj[0] == pytest.approx(math.cos(rz0 + da / 2.0), rel=1e-5)
    # A later latitude catches changes to the repeated float32 angle step.
    assert rx[3] == pytest.approx(
        3.0 / (6.37e6 * math.cos(rz0 + 3 * da) * da), rel=1e-5
    )

    np.testing.assert_allclose(xx, rx[np.newaxis, :4] * np.float32(9.8) * hm, rtol=1e-6)
    np.testing.assert_allclose(yy, 3.0 * 9.8 * hn / (6.37e6 * da), rtol=1e-5)


def test_mass_step_hand_computed() -> None:
    # These values are calculated directly from the continuity equation.
    h = np.full((3, 3), 100.0, dtype=np.float32)
    h[2, 2] = -5.0
    rx = np.full(3, 0.5, dtype=np.float32)
    cj = np.ones(3, dtype=np.float32)
    z1 = np.zeros((3, 3), dtype=np.float32)
    m1 = np.zeros((3, 3), dtype=np.float32)
    n1 = np.zeros((3, 3), dtype=np.float32)
    m1[1, 1] = 1.0
    m1[2, 1] = 2.0
    z2 = np.full((3, 3), 9.0, dtype=np.float32)
    _mass(z1, z2, m1, n1, h, rx, cj)

    assert z2[1, 1] == np.float32(-0.5)
    assert z2[2, 1] == np.float32(-0.5)
    assert z2[1, 2] == np.float32(0.0)
    assert z2[2, 2] == np.float32(0.0)
    # Sentinels show that the first Fortran row and column were not written.
    assert np.all(z2[0, :] == np.float32(9.0))
    assert np.all(z2[:, 0] == np.float32(9.0))


def test_mass_flushes_small_values_to_zero() -> None:
    h = np.full((3, 3), 100.0, dtype=np.float32)
    rx = np.full(3, 0.5, dtype=np.float32)
    cj = np.ones(3, dtype=np.float32)
    z1 = np.zeros((3, 3), dtype=np.float32)
    m1 = np.zeros((3, 3), dtype=np.float32)
    n1 = np.zeros((3, 3), dtype=np.float32)
    m1[1, 1] = np.float32(1.6e-5)
    z2 = np.empty((3, 3), dtype=np.float32)
    _mass(z1, z2, m1, n1, h, rx, cj)
    assert z2[1, 1] == np.float32(0.0)


def test_mmnt_wet_pair_condition_and_flush() -> None:
    h = np.full((3, 3), 100.0, dtype=np.float32)
    h[2, 2] = -5.0
    xx = np.full((3, 3), 0.25, dtype=np.float32)
    yy = np.full((3, 3), 0.125, dtype=np.float32)
    z2 = np.zeros((3, 3), dtype=np.float32)
    z2[2, 1] = 2.0
    z2[1, 2] = 4.0
    m1 = np.zeros((3, 3), dtype=np.float32)
    n1 = np.zeros((3, 3), dtype=np.float32)
    m2 = np.full((3, 3), 9.0, dtype=np.float32)
    n2 = np.full((3, 3), 9.0, dtype=np.float32)
    _mmnt(z2, m1, m2, n1, n2, h, xx, yy)

    assert m2[1, 1] == np.float32(-0.5)
    assert m2[1, 2] == np.float32(0.0)
    assert n2[1, 1] == np.float32(-0.5)
    assert n2[2, 1] == np.float32(0.0)
    # Sentinels protect the two staggered outer edges from unexpected writes.
    assert np.all(m2[2, :] == np.float32(9.0))
    assert np.all(n2[:, 2] == np.float32(9.0))


def test_bout_radiation_sign_and_corner_order() -> None:
    # Outgoing flow radiates positive elevation and incoming flow flips the
    # sign. At corners, the second edge pass wins.
    ia = ja = 4
    h = np.full((ia, ja), 100.0, dtype=np.float32)
    m_prev = np.zeros((ia, ja), dtype=np.float32)
    n_prev = np.zeros((ia, ja), dtype=np.float32)
    n_prev[1, 1] = 7.0
    n_prev[2, 1] = -7.0
    z2 = np.zeros((ia, ja), dtype=np.float32)
    _bout(z2, m_prev, n_prev, h)

    cc = math.sqrt(9.8 * 100.0)
    assert z2[2, 1] == pytest.approx(7.0 / cc, rel=1e-6)
    # The second edge pass overwrites the corner with its independent value.
    assert z2[1, 1] == pytest.approx(3.5 / cc, rel=1e-6)


def test_bout_skips_dry_cells() -> None:
    ia = ja = 4
    h = np.full((ia, ja), 100.0, dtype=np.float32)
    h[2, 1] = -50.0
    h[1, 2] = -50.0
    m_prev = np.zeros((ia, ja), dtype=np.float32)
    n_prev = np.zeros((ia, ja), dtype=np.float32)
    z2 = np.full((ia, ja), 0.25, dtype=np.float32)
    _bout(z2, m_prev, n_prev, h)
    assert z2[2, 1] == np.float32(0.25)
    assert z2[1, 2] == np.float32(0.25)


def test_read_tidal_dat_real_file() -> None:
    ip, jp = _read_tidal_dat(MODEL_DIR / "tidal.dat")
    assert ip.shape == (17,)
    assert (ip[0], jp[0]) == (2272, 1088)
    assert (ip[-1], jp[-1]) == (2425, 864)


def test_read_xyo_dat_real_file() -> None:
    # The captured file includes grid dimensions after the four consumed fields.
    assert _read_xyo_dat(MODEL_DIR / "xyo.dat") == (1021, 1246, 1861, 2056)


def test_read_deform_a_real_file() -> None:
    grid = _read_deform_a(MODEL_DIR / "deform_a.grd", 1021, 1246, 1861, 2056)
    assert grid.shape == (226, 196)
    assert grid.dtype == np.float32
    assert np.all(np.isfinite(grid))


def test_write_green_dat_fixed_width_format(tmp_path: Path) -> None:
    path = tmp_path / "green.dat"
    _write_green_dat(
        path,
        [
            (0.0, np.array([0.123, -0.5], dtype=np.float32)),
            (1680.0, np.array([12.345, 0.0], dtype=np.float32)),
        ],
    )
    lines = path.read_text().splitlines()
    assert lines[0] == "    0.0  0.123 -0.500"
    assert lines[1] == " 1680.0 12.345  0.000"


def test_write_zmax_a_fixed_width_format(tmp_path: Path) -> None:
    path = tmp_path / "zmax_a.grd"
    _write_zmax_a(path, np.array([[0.0, 14.441], [-0.5, 1.0]], dtype=np.float32))
    lines = path.read_text().splitlines()
    assert lines[0] == "   0.000  14.441"
    assert lines[1] == "  -0.500   1.000"


def test_read_grid_a_applies_shallow_water_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tsunami_module, "IA", 2)
    monkeypatch.setattr(tsunami_module, "JA", 2)
    path = tmp_path / "grid_a.grd"
    path.write_text("5.0 -3.0\n0.0 20.0\n")
    np.testing.assert_array_equal(
        _read_grid_a(path),
        np.array([[10.0, -3.0], [0.0, 20.0]], dtype=np.float32),
    )


def test_run_tsunami_mini_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tsunami_module, "IA", 6)
    monkeypatch.setattr(tsunami_module, "JA", 5)
    monkeypatch.setattr(tsunami_module, "KE", 4)
    monkeypatch.setattr(tsunami_module, "KD", 2)
    monkeypatch.setattr(tsunami_module, "NG", 2)

    (tmp_path / "bathy").mkdir()
    rows = []
    for _ in range(6):
        rows.append(" ".join("1000.0" for _ in range(5)))
    (tmp_path / "bathy" / "grid_a.grd").write_text("\n".join(rows) + "\n")
    (tmp_path / "tidal.dat").write_text("1 3 3\n2 4 4\n")
    (tmp_path / "xyo.dat").write_text("2 3 2 3\n")
    (tmp_path / "deform_a.grd").write_text("1.0 1.0\n1.0 1.0\n")

    run_tsunami(tmp_path)

    green = (tmp_path / "zfolder" / "green.dat").read_text().splitlines()
    assert green == [
        "    0.0  1.000  0.000",
        "    0.1  0.837  0.000",
    ]

    zmax = np.loadtxt(tmp_path / "zfolder" / "zmax_a.grd", dtype=np.float32)
    np.testing.assert_allclose(
        zmax,
        np.array(
            [
                [0.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.007, 0.292, 0.003, 0.0],
                [0.0, 0.076, 1.0, 0.005, 0.0],
                [0.0, 0.003, 0.078, 0.0, 0.0],
                [0.0, 0.0, 0.001, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        ),
        atol=0.001,
    )


def _write_toy_grid_inputs(work_dir: Path) -> None:
    (work_dir / "bathy").mkdir()
    rows = [" ".join("1000.0" for _ in range(5)) for _ in range(6)]
    (work_dir / "bathy" / "grid_a.grd").write_text("\n".join(rows) + "\n")
    (work_dir / "tidal.dat").write_text("1 3 3\n2 4 4\n")
    (work_dir / "xyo.dat").write_text("2 3 2 3\n")
    (work_dir / "deform_a.grd").write_text("1.0 1.0\n1.0 1.0\n")


def test_run_tsunami_resumes_from_checkpoint_after_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A crash after a checkpoint must resume with the same outputs as a fresh
    # run.
    monkeypatch.setattr(tsunami_module, "IA", 6)
    monkeypatch.setattr(tsunami_module, "JA", 5)
    monkeypatch.setattr(tsunami_module, "KE", 8)
    monkeypatch.setattr(tsunami_module, "KD", 2)
    monkeypatch.setattr(tsunami_module, "NG", 2)
    monkeypatch.setattr(tsunami_module, "_CHECKPOINT_INTERVAL", 2)

    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    _write_toy_grid_inputs(reference_dir)
    run_tsunami(reference_dir)
    reference_green = (reference_dir / "zfolder" / "green.dat").read_text()
    reference_zmax = np.loadtxt(
        reference_dir / "zfolder" / "zmax_a.grd", dtype=np.float32
    )

    resumed_dir = tmp_path / "resumed"
    resumed_dir.mkdir()
    _write_toy_grid_inputs(resumed_dir)

    real_mmnt = tsunami_module._mmnt
    call_count = 0

    def flaky_mmnt(
        z2: np.ndarray,
        m1: np.ndarray,
        m2: np.ndarray,
        n1: np.ndarray,
        n2: np.ndarray,
        h: np.ndarray,
        xx: np.ndarray,
        yy: np.ndarray,
    ) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 4:
            raise RuntimeError("simulated worker crash")
        real_mmnt(z2, m1, m2, n1, n2, h, xx, yy)

    monkeypatch.setattr(tsunami_module, "_mmnt", flaky_mmnt)
    with pytest.raises(RuntimeError, match="simulated worker crash"):
        run_tsunami(resumed_dir)

    checkpoint_path = resumed_dir / "zfolder" / "_checkpoint.npz"
    assert checkpoint_path.is_file()

    monkeypatch.setattr(tsunami_module, "_mmnt", real_mmnt)
    run_tsunami(resumed_dir)

    assert not checkpoint_path.exists()
    resumed_green = (resumed_dir / "zfolder" / "green.dat").read_text()
    resumed_zmax = np.loadtxt(resumed_dir / "zfolder" / "zmax_a.grd", dtype=np.float32)

    assert resumed_green == reference_green
    np.testing.assert_array_equal(resumed_zmax, reference_zmax)


def test_read_checkpoint_rejects_stale_pipeline_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zeros = np.zeros((6, 5), dtype=np.float32)
    checkpoint_path = tmp_path / "checkpoint.npz"

    monkeypatch.setattr(tsunami_module, "PIPELINE_VERSION", 999)
    tsunami_module._write_checkpoint(
        checkpoint_path, 5, zeros, zeros, zeros, zeros, zeros, zeros, zeros, []
    )

    monkeypatch.setattr(tsunami_module, "PIPELINE_VERSION", 1)
    result = tsunami_module._read_checkpoint(checkpoint_path, ia=6, ja=5, n_gauges=2)

    assert result is None


def test_read_grid_a_rejects_the_wrong_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tsunami_module, "IA", 2)
    monkeypatch.setattr(tsunami_module, "JA", 2)
    path = tmp_path / "grid_a.grd"
    path.write_text("5.0 -3.0 1.0\n")

    with pytest.raises(ValueError, match=r"Unexpected grid_a\.grd shape"):
        _read_grid_a(path)


def test_read_deform_a_rejects_a_window_size_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "deform_a.grd"
    path.write_text("1.0 1.0 1.0\n")

    with pytest.raises(ValueError, match=r"Unexpected deform_a\.grd size"):
        _read_deform_a(path, ids=1, ide=2, jds=1, jde=2)


def test_read_checkpoint_rejects_an_array_shape_mismatch(tmp_path: Path) -> None:
    wrong_shape = np.zeros((3, 3), dtype=np.float32)
    checkpoint_path = tmp_path / "checkpoint.npz"
    tsunami_module._write_checkpoint(
        checkpoint_path,
        5,
        wrong_shape,
        wrong_shape,
        wrong_shape,
        wrong_shape,
        wrong_shape,
        wrong_shape,
        wrong_shape,
        [],
    )

    result = tsunami_module._read_checkpoint(checkpoint_path, ia=6, ja=5, n_gauges=2)

    assert result is None


def test_read_checkpoint_rejects_a_gauge_count_mismatch(tmp_path: Path) -> None:
    zeros = np.zeros((6, 5), dtype=np.float32)
    checkpoint_path = tmp_path / "checkpoint.npz"
    gauges = np.zeros(6, dtype=np.float32)
    tsunami_module._write_checkpoint(
        checkpoint_path,
        5,
        zeros,
        zeros,
        zeros,
        zeros,
        zeros,
        zeros,
        zeros,
        [(0.0, gauges)],
    )

    result = tsunami_module._read_checkpoint(checkpoint_path, ia=6, ja=5, n_gauges=2)

    assert result is None


def test_read_checkpoint_rejects_a_step_index_out_of_range(tmp_path: Path) -> None:
    zeros = np.zeros((6, 5), dtype=np.float32)
    checkpoint_path = tmp_path / "checkpoint.npz"
    tsunami_module._write_checkpoint(
        checkpoint_path,
        tsunami_module.KE + 1,
        zeros,
        zeros,
        zeros,
        zeros,
        zeros,
        zeros,
        zeros,
        [],
    )

    result = tsunami_module._read_checkpoint(checkpoint_path, ia=6, ja=5, n_gauges=2)

    assert result is None
