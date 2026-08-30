"""Okada-based vertical-displacement port of `model/def_oka.f`."""

import logging
from pathlib import Path

import numpy as np

from tsdhn.utils.file_utils import atomic_write

logger = logging.getLogger(__name__)

# The legacy grid uses the same spacing on both axes.
_DX = np.float32(7412.9951096)
# These velocities feed the dimensionless rigidity term.
_VP = np.float32(4.82e3)
_VS = np.float32(2.78e3)
_RMU = _VS * _VS / (_VP * _VP - _VS * _VS)
_EPS = np.float32(1.0e-8)
# Compute pi through float32 asin to match the legacy arithmetic.
_PI = np.float32(2.0) * np.arcsin(np.float32(1.0))
_DEG2RAD = _PI / np.float32(180.0)


def _ustrike_fz(
    eps: np.floating,
    rmu: np.floating,
    q: np.ndarray,
    cs: np.floating,
    sn: np.floating,
    xi: np.ndarray,
    et: np.ndarray,
) -> np.ndarray:
    """Compute the vertical displacement from the strike component."""
    dh = et * sn - q * cs
    r = np.sqrt(xi**2 + et**2 + q**2)
    ret = r + et
    rdh = r + dh

    ret_regular = np.abs(ret) >= eps
    cs_regular = np.abs(cs) >= eps
    rdh_regular = np.abs(rdh) >= eps

    with np.errstate(divide="ignore", invalid="ignore"):
        xi4_reg_csreg = rmu * (np.log(r + dh) - sn * np.log(r + et)) / cs
        xi4_reg_cssing = -rmu * q / (r + dh)
        xi4_reg = np.where(cs_regular, xi4_reg_csreg, xi4_reg_cssing)

        xi4_sing_csreg_rdhreg = rmu * (np.log(r + dh) + sn * np.log(r - et)) / cs
        xi4_sing_csreg_rdhsing = rmu * (-np.log(r - dh) + sn * np.log(r - et)) / cs
        xi4_sing_csreg = np.where(
            rdh_regular, xi4_sing_csreg_rdhreg, xi4_sing_csreg_rdhsing
        )
        xi4_sing_cssing_rdhreg = -rmu * q / (r + dh)
        xi4_sing_cssing_rdhsing = np.zeros_like(r)
        xi4_sing_cssing = np.where(
            rdh_regular, xi4_sing_cssing_rdhreg, xi4_sing_cssing_rdhsing
        )
        xi4_sing = np.where(cs_regular, xi4_sing_csreg, xi4_sing_cssing)

        xi4 = np.where(ret_regular, xi4_reg, xi4_sing)

        suz1 = np.where(ret_regular, dh * q / (r * (r + et)), 0.0)
        suz2 = np.where(ret_regular, q * sn / (r + et), 0.0)
        suz3 = xi4 * sn
        fz = suz1 + suz2 + suz3

    return np.asarray(fz, dtype=np.float32)


def _udip_gz(
    eps: np.floating,
    rmu: np.floating,
    q: np.ndarray,
    cs: np.floating,
    sn: np.floating,
    xi: np.ndarray,
    et: np.ndarray,
) -> np.ndarray:
    """Compute the vertical displacement from the dip component."""
    dh = et * sn - q * cs
    r = np.sqrt(xi**2 + et**2 + q**2)
    ret = r + et
    xx = np.sqrt(xi**2 + q**2)

    ret_regular = np.abs(ret) >= eps
    cs_regular = np.abs(cs) >= eps
    xi_regular = np.abs(xi) >= eps
    r_plus_xi_regular = np.abs(r + xi) >= eps
    q_regular = np.abs(q) >= eps

    with np.errstate(divide="ignore", invalid="ignore"):
        xi5in = (et * (xx + q * cs) + xx * (r + xx) * sn) / (xi * (r + xx) * cs)
        xi5_cs_regular_generic = rmu * 2.0 * np.arctan(xi5in) / cs

        xi5_reg_csreg = np.where(xi_regular, xi5_cs_regular_generic, 0.0)
        xi5_reg_cssing = np.where(xi_regular, -rmu * xi * sn / (r + dh), 0.0)
        xi5_reg = np.where(cs_regular, xi5_reg_csreg, xi5_reg_cssing)

        xi5_sing_csreg = np.where(xi_regular, xi5_cs_regular_generic, 0.0)
        xi5_sing_cssing = np.where(xi_regular, -rmu * xi * sn / (r + dh), 0.0)
        xi5_sing = np.where(cs_regular, xi5_sing_csreg, xi5_sing_cssing)

        xi5 = np.where(ret_regular, xi5_reg, xi5_sing)

        uz1 = np.where(r_plus_xi_regular, dh * q / (r * (r + xi)), 0.0)
        uz2 = np.where(q_regular, sn * np.arctan(xi * et / (q * r)), 0.0)
        uz3 = -xi5 * sn * cs
        gz = uz1 + uz2 + uz3

    return np.asarray(gz, dtype=np.float32)


def compute_deform_grid(
    I0: int,
    J0: int,
    D0: float,
    L0: float,
    W0: float,
    TH: float,
    DL: float,
    RD: float,
    HH: float,
    IDS: int,
    IDE: int,
    JDS: int,
    JDE: int,
) -> np.ndarray:
    """Compute vertical displacement over the requested grid window."""
    ia = IDE - IDS + 1
    ja = JDE - JDS + 1
    i0 = I0 - IDS + 1
    j0 = J0 - JDS + 1

    st = np.float32(TH)
    # The reference offsets these exact strikes to avoid a singular transform.
    if st == 0.0 or st == 360.0:
        st = st + np.float32(0.001)
    di = np.float32(DL)
    sl = np.float32(RD)
    d0 = np.float32(D0)
    l0 = np.float32(L0)
    w0 = np.float32(W0)
    hh = np.float32(HH)

    str_ = (np.float32(90.0) - st) * _DEG2RAD
    dir_ = di * _DEG2RAD
    slr = sl * _DEG2RAD

    cs = np.cos(dir_)
    sn = np.sin(dir_)
    de = hh + w0 * sn

    dst = d0 * np.cos(slr)
    ddp = d0 * np.sin(slr)

    cos_str = np.cos(str_)
    sin_str = np.sin(str_)
    tan_str = np.tan(str_)

    ii = np.arange(ia, dtype=np.float32).reshape(-1, 1)
    jj = np.arange(ja, dtype=np.float32).reshape(1, -1)
    x0 = (ii - i0) * _DX
    y0 = (jj - j0) * _DX
    x = x0 / cos_str + (y0 - x0 * tan_str) * sin_str
    y = y0 * cos_str - x0 * sin_str + w0 * cs

    p = y * cs + de * sn
    q = y * sn - de * cs

    with np.errstate(divide="ignore", invalid="ignore"):
        fz1 = _ustrike_fz(_EPS, _RMU, q, cs, sn, x, p)
        fz2 = _ustrike_fz(_EPS, _RMU, q, cs, sn, x, p - w0)
        fz3 = _ustrike_fz(_EPS, _RMU, q, cs, sn, x - l0, p)
        fz4 = _ustrike_fz(_EPS, _RMU, q, cs, sn, x - l0, p - w0)

        gz1 = _udip_gz(_EPS, _RMU, q, cs, sn, x, p)
        gz2 = _udip_gz(_EPS, _RMU, q, cs, sn, x, p - w0)
        gz3 = _udip_gz(_EPS, _RMU, q, cs, sn, x - l0, p)
        gz4 = _udip_gz(_EPS, _RMU, q, cs, sn, x - l0, p - w0)

    uzst = -(fz1 - fz2 - fz3 + fz4) * dst / (2.0 * _PI)
    uzdp = -(gz1 - gz2 - gz3 + gz4) * ddp / (2.0 * _PI)
    return np.asarray(uzst + uzdp, dtype=np.float32)


def clip_anomalous_values(grid: np.ndarray, threshold: float = 20.0) -> np.ndarray:
    """Apply the inherited `def_oka.f` outlier guard."""
    anomalous = np.abs(grid) >= threshold
    if np.any(anomalous):
        logger.warning(
            "clip_anomalous_values: %d cell(s) exceeded |Z|>=%.1f, zeroed",
            int(np.count_nonzero(anomalous)),
            threshold,
        )
    return np.asarray(np.where(anomalous, np.float32(0.0), grid), dtype=np.float32)


def write_deform_grid(path: Path, grid: np.ndarray) -> None:
    """Write the fixed-width grid consumed by the legacy tsunami step."""
    with atomic_write(path) as tmp_path:
        np.savetxt(tmp_path, grid, fmt="%9.3f", delimiter="")


def _parse_pfalla_inp(
    path: Path,
) -> tuple[int, int, float, float, float, float, float, float, float]:
    # List-directed Fortran output may wrap a record, so parse tokens globally.
    tokens = path.read_text().split()
    i0, j0, d0, l0, w0, th, dl, rd, hh = tokens[:9]
    return (
        int(float(i0)),
        int(float(j0)),
        float(d0),
        float(l0),
        float(w0),
        float(th),
        float(dl),
        float(rd),
        float(hh),
    )


def _parse_xyo_dat(path: Path) -> tuple[int, int, int, int]:
    # The legacy reader consumes four tokens; trailing grid dimensions are
    # padding written by the fault-plane step.
    ids, ide, jds, jde = path.read_text().split()[:4]
    return int(float(ids)), int(float(ide)), int(float(jds)), int(float(jde))


def run_deform(working_dir: Path) -> None:
    """Read fault-plane files and write the deformation grid."""
    I0, J0, D0, L0, W0, TH, DL, RD, HH = _parse_pfalla_inp(working_dir / "pfalla.inp")
    IDS, IDE, JDS, JDE = _parse_xyo_dat(working_dir / "xyo.dat")
    grid = compute_deform_grid(
        I0=I0,
        J0=J0,
        D0=D0,
        L0=L0,
        W0=W0,
        TH=TH,
        DL=DL,
        RD=RD,
        HH=HH,
        IDS=IDS,
        IDE=IDE,
        JDS=JDS,
        JDE=JDE,
    )
    grid = clip_anomalous_values(grid)
    write_deform_grid(working_dir / "deform_a.grd", grid)
