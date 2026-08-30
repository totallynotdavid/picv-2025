"""Python port of `model/def_oka.f` (Okada 1985 dislocation model).

`model/def_oka.f` is the source for the legacy `deform` executable. Both
deploy/api.Dockerfile and scripts/setup.sh compile
`ifx ... model/def_oka.f -o .../deform`. model/deform.for (Mansinha &
Smylie 1971) looks similar (same pfalla.inp/xyo.dat/deform_a.grd file
formats) but is a different model that model/Makefile still references;
the build does not compile it.

def_oka.f has no IMPLICIT DOUBLE PRECISION -- every variable, including
its PARAMETER constants, is Fortran's default REAL*4 -- so this module
computes in np.float32 throughout to match the legacy output consumed by the
tsunami step.

NP (number of fault segments) is a compile-time PARAMETER fixed at 1 in
def_oka.f, so this port specializes the single-segment case directly.
Similarly, only Z (surface uplift/subsidence) is written to deform_a.grd.
def_oka.f also computes UX/UY, but does not write them. USTRIKE/UDIP are
ported here as
Z-component-only (`_ustrike_fz`/`_udip_gz`), which also verifiably never
depend on the horizontal-displacement intermediates.
"""

import logging
from pathlib import Path

import numpy as np

from tsdhn.utils.file_utils import atomic_write

logger = logging.getLogger(__name__)

# def_oka.f:38 -- DX=DY, both grid axes use the same spacing.
_DX = np.float32(7412.9951096)
# def_oka.f:42 -- P-wave / S-wave velocities feeding the Poisson-ratio-like
# RMU term (dimensionless, so the mismatch with the "km/sec" comment in the
# source doesn't affect the result as long as both use the same unit).
_VP = np.float32(4.82e3)
_VS = np.float32(2.78e3)
_RMU = _VS * _VS / (_VP * _VP - _VS * _VS)
_EPS = np.float32(1.0e-8)  # def_oka.f:44 -- singular-point threshold
# def_oka.f:83 -- PI=2.0*ASIN(1.0), not a literal, so this matches the
# exact float32 rounding ifx's ASIN would produce.
_PI = np.float32(2.0) * np.arcsin(np.float32(1.0))
_DEG2RAD = _PI / np.float32(180.0)
# E2 (eccentricity^2) and RE (equatorial radius) are declared in def_oka.f's
# PARAMETER list but never referenced in the main program or any
# subroutine -- verified against the source, not ported.


def _ustrike_fz(
    eps: np.floating,
    rmu: np.floating,
    q: np.ndarray,
    cs: np.floating,
    sn: np.floating,
    xi: np.ndarray,
    et: np.ndarray,
) -> np.ndarray:
    """def_oka.f:189-343 (USTRIKE), Z-component only.

    P/L0/W0 are formal parameters in the Fortran signature but never
    referenced in the body -- dropped. FX/FY (and the XI1/XI2/XI3/Q-branch
    intermediates they alone depend on) are dead for this pipeline since
    only Z is written to deform_a.grd -- verified: FZ's only dependency
    among XI1..XI5 is XI4, and XI4's formula in every branch below is
    self-contained (never references XI1/XI2/XI3/XI5).
    """
    dh = et * sn - q * cs
    r = np.sqrt(xi**2 + et**2 + q**2)
    ret = r + et
    rdh = r + dh

    ret_regular = np.abs(ret) >= eps
    cs_regular = np.abs(cs) >= eps
    rdh_regular = np.abs(rdh) >= eps

    with np.errstate(divide="ignore", invalid="ignore"):
        # RET regular (def_oka.f:201-229)
        xi4_reg_csreg = rmu * (np.log(r + dh) - sn * np.log(r + et)) / cs
        xi4_reg_cssing = -rmu * q / (r + dh)
        xi4_reg = np.where(cs_regular, xi4_reg_csreg, xi4_reg_cssing)

        # RET singular (def_oka.f:231-286)
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

        # Final FZ (def_oka.f:310-313, 334-337)
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
    """def_oka.f:345-455 (UDIP), Z-component only.

    P/L0/W0 dropped, same as USTRIKE. GZ's only dependency among
    XI1/XI3/XI5 is XI5, self-contained in every branch. Unlike USTRIKE,
    UDIP's RET-singular branch has no further RDH sub-branch (def_oka.f
    :386-416 has no RDH check at all) -- verified against the source, not
    assumed symmetric with USTRIKE.
    """
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

        # RET regular (def_oka.f:361-384)
        xi5_reg_csreg = np.where(xi_regular, xi5_cs_regular_generic, 0.0)
        xi5_reg_cssing = np.where(xi_regular, -rmu * xi * sn / (r + dh), 0.0)
        xi5_reg = np.where(cs_regular, xi5_reg_csreg, xi5_reg_cssing)

        # RET singular, no RDH branch (def_oka.f:391-414)
        xi5_sing_csreg = np.where(xi_regular, xi5_cs_regular_generic, 0.0)
        xi5_sing_cssing = np.where(xi_regular, -rmu * xi * sn / (r + dh), 0.0)
        xi5_sing = np.where(cs_regular, xi5_sing_csreg, xi5_sing_cssing)

        xi5 = np.where(ret_regular, xi5_reg, xi5_sing)

        # Final GZ (def_oka.f:438-451)
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
    """def_oka.f:32-187 (main program, NP=1 specialized), vectorized over
    the (IA, JA) grid.

    Field names match pfalla.inp's own order and tsdhn.deform's earlier
    deform.for-based naming (I0,J0,D0,L0,W0,TH,DL,RD,HH); def_oka.f's own
    names for the same fields are ST (=TH, strike), DI (=DL, dip),
    SL (=RD, rake).
    """
    ia = IDE - IDS + 1
    ja = JDE - JDS + 1
    i0 = I0 - IDS + 1  # def_oka.f:93
    j0 = J0 - JDS + 1  # def_oka.f:94

    st = np.float32(TH)
    if st == 0.0 or st == 360.0:  # def_oka.f:77-78
        st = st + np.float32(0.001)
    di = np.float32(DL)
    sl = np.float32(RD)
    d0 = np.float32(D0)
    l0 = np.float32(L0)
    w0 = np.float32(W0)
    hh = np.float32(HH)

    str_ = (np.float32(90.0) - st) * _DEG2RAD  # def_oka.f:100
    dir_ = di * _DEG2RAD  # def_oka.f:101
    slr = sl * _DEG2RAD  # def_oka.f:102

    cs = np.cos(dir_)  # def_oka.f:104
    sn = np.sin(dir_)  # def_oka.f:105
    de = hh + w0 * sn  # def_oka.f:106

    dst = d0 * np.cos(slr)  # def_oka.f:108
    ddp = d0 * np.sin(slr)  # def_oka.f:109

    cos_str = np.cos(str_)
    sin_str = np.sin(str_)
    tan_str = np.tan(str_)

    ii = np.arange(ia, dtype=np.float32).reshape(-1, 1)
    jj = np.arange(ja, dtype=np.float32).reshape(1, -1)
    x0 = (ii - i0) * _DX  # def_oka.f:113
    y0 = (jj - j0) * _DX  # def_oka.f:114 (DY == DX)
    x = x0 / cos_str + (y0 - x0 * tan_str) * sin_str  # def_oka.f:115
    y = y0 * cos_str - x0 * sin_str + w0 * cs  # def_oka.f:116

    p = y * cs + de * sn  # def_oka.f:118
    q = y * sn - de * cs  # def_oka.f:119

    with np.errstate(divide="ignore", invalid="ignore"):
        fz1 = _ustrike_fz(_EPS, _RMU, q, cs, sn, x, p)
        fz2 = _ustrike_fz(_EPS, _RMU, q, cs, sn, x, p - w0)
        fz3 = _ustrike_fz(_EPS, _RMU, q, cs, sn, x - l0, p)
        fz4 = _ustrike_fz(_EPS, _RMU, q, cs, sn, x - l0, p - w0)

        gz1 = _udip_gz(_EPS, _RMU, q, cs, sn, x, p)
        gz2 = _udip_gz(_EPS, _RMU, q, cs, sn, x, p - w0)
        gz3 = _udip_gz(_EPS, _RMU, q, cs, sn, x - l0, p)
        gz4 = _udip_gz(_EPS, _RMU, q, cs, sn, x - l0, p - w0)

    uzst = -(fz1 - fz2 - fz3 + fz4) * dst / (2.0 * _PI)  # def_oka.f:141
    uzdp = -(gz1 - gz2 - gz3 + gz4) * ddp / (2.0 * _PI)  # def_oka.f:145
    # def_oka.f:149 -- NP=1, so the output is one accumulated displacement.
    return np.asarray(uzst + uzdp, dtype=np.float32)


def clip_anomalous_values(grid: np.ndarray, threshold: float = 20.0) -> np.ndarray:
    """Apply def_oka.f's large-value outlier guard."""
    anomalous = np.abs(grid) >= threshold
    if np.any(anomalous):
        logger.warning(
            "clip_anomalous_values: %d cell(s) exceeded |Z|>=%.1f "
            "(def_oka.f:150-153), zeroed",
            int(np.count_nonzero(anomalous)),
            threshold,
        )
    return np.asarray(np.where(anomalous, np.float32(0.0), grid), dtype=np.float32)


def write_deform_grid(path: Path, grid: np.ndarray) -> None:
    """def_oka.f:167-181: FORMAT(4000F9.3) -- fixed 9-char fields, 3
    decimals, no separator between fields, one row per line."""
    with atomic_write(path) as tmp_path:
        np.savetxt(tmp_path, grid, fmt="%9.3f", delimiter="")


def _parse_pfalla_inp(
    path: Path,
) -> tuple[int, int, float, float, float, float, float, float, float]:
    # Tokenize the whole file, not line-by-line: Fortran list-directed
    # WRITE can wrap a record near column 80 (same issue documented in
    # fault_plane/spec_binary.py's _read_slip).
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
    # def_oka.f's own READ(1,*)IDS,IDE,JDS,JDE only consumes 4 tokens even
    # though fault_plane.f90 writes 6 (model/fault_plane.f90:142) -- IA/JA
    # are harmless trailing padding, ignored here too.
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
