"""model/tsunami1.for -> Python port (linear shallow-water propagation).

This is the Python port of the legacy `tsunami` executable: an explicit
finite-difference integration of the linear shallow-water equations in
spherical coordinates over the full IA=2461 x JA=2056 Pacific grid, KE=33602 steps
of DT=3 s (~28 h simulated). Per-step structure is MASS (continuity) ->
BOUT (open-boundary radiation) -> MMNT (momentum, no friction) -> CHAN
(time-level rotation), with tide-gauge sampling and the running maximum
taken every KD=20 steps.

tsunami1.for has no IMPLICIT DOUBLE PRECISION -- everything is default
REAL*4 -- so this module computes in np.float32 throughout, same as
tsdhn.deform. The per-step flush-to-zero (|value| < 1e-5 -> 0.0,
tsunami1.for:313/334/344) is part of the model, replicated exactly.

Dead code in tsunami1.for, verified against the source and deliberately
not ported:
- TMAX and its TMX/ZMX arrays: the zfolder/tmax_a.grd write is commented
  out (lines 119-122) and nothing else reads them.
- MOVIE (frame snapshots every KA steps): its call is commented out
  (line 109).
- JNQ (nested-grid boundary interpolation): never called from the main
  program -- this build propagates on grid A only.
- The tide-gauge location console check and the itime wall-clock report:
  console-only output.

The only live outputs are zfolder/green.dat (gauge mareograms,
WRITE(4,'(F7.1,100F7.3)')) and zfolder/zmax_a.grd (running maximum
elevation, FORMAT(4000F8.3)); both formats are replicated field-for-field
because downstream consumers (render/maxola.py, render/ttt_max.py, and
the golden-pipeline fingerprints) read these files.

Two time levels are kept as swapped buffer pairs instead of CHAN's full
copy. That is semantically identical because every level-2 cell either
gets fully rewritten each step (MASS/BOUT/MMNT cover their whole update
regions, writing 0.0 in their dry/else branches) or is never written
after the initial zeroing (the I=1/J=1 borders, M's I=IA column, N's
J=JA row) and therefore stays 0.0 in both buffers forever. The one place
Fortran reads level 2 *before* it is rewritten -- BOUT's M(:,:,2)/N(:,:,2)
-- sees values CHAN just made equal to level 1, so the port reads the
level-1 buffers there.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import cast

import numba
import numpy as np

from tsdhn.pipeline_version import PIPELINE_VERSION
from tsdhn.utils.file_utils import atomic_write

logger = logging.getLogger(__name__)

# numba ships no type stubs; prange is re-cast so the kernels below stay
# fully typed. numba resolves the aliased global back to numba.prange when
# compiling, so parallelization is unaffected.
prange = cast("Callable[[int, int], range]", numba.prange)


def _jit[F: Callable[..., None]](fn: F) -> F:
    # No fastmath: the kernels must keep IEEE float32 semantics in written
    # order to stay faithful to the REAL*4 Fortran arithmetic. parallel=True
    # only distributes independent per-cell writes (no reductions), so the
    # result is identical to the serial loop.
    return cast("F", numba.njit(cache=True, parallel=True)(fn))


# tsunami1.for:14-20 PARAMETER block (all default REAL*4 / INTEGER).
IA = 2461
JA = 2056
_DELTA = np.float32(240.0) / np.float32(3600.0)  # grid resolution (deg)
_DT = np.float32(3.0)  # time step (s)
KE = 33602  # total computation steps
KD = 20  # mareogram sampling ratio
NG = 17  # virtual tide gauges
_RT = np.float32(6.37e6)  # Earth radius (m)
# tsunami1.for:45 -- southern latitude edge of grid A (deg).
_BLATA = np.float32(-76.006)
# tsunami1.for:42/252 -- PI=4.0*ATAN(1.0), computed not literal, so this
# matches the exact float32 rounding the Fortran expression produces.
_PI = np.float32(4.0) * np.arctan(np.float32(1.0))
_DA = _PI * _DELTA / np.float32(180.0)  # tsunami1.for:48 -- grid step (rad)
_GG = np.float32(9.8)  # tsunami1.for:253
# tsunami1.for:313/334/344 -- small-value flush threshold.
_FLUSH = np.float32(1.0e-5)


def _read_xyo_dat(path: Path) -> tuple[int, int, int, int]:
    # tsunami1.for:37 -- READ(5,*)IDS,IDE,JDS,JDE consumes only 4 tokens;
    # fault_plane also writes IA/JA as harmless trailing padding.
    ids, ide, jds, jde = path.read_text().split()[:4]
    return int(float(ids)), int(float(ide)), int(float(jds)), int(float(jde))


def _read_tidal_dat(path: Path) -> tuple[np.ndarray, np.ndarray]:
    # tsunami1.for:56-58 -- READ(3,*)PNAME(IN),IP(IN),JP(IN). PNAME is
    # CHARACTER*1 and never used beyond the console check; only the grid
    # indices matter.
    ip = np.empty(NG, dtype=np.int64)
    jp = np.empty(NG, dtype=np.int64)
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    for gauge, line in enumerate(lines[:NG]):
        _name, i_text, j_text = line.split()[:3]
        ip[gauge] = int(i_text)
        jp[gauge] = int(j_text)
    return ip, jp


def _read_grid_a(path: Path) -> np.ndarray:
    # tsunami1.for:154-167 (INPUTA): bathymetry, one row per record, then
    # the shallow-water floor -- depths in (0, 10) m are raised to 10 m.
    grid = np.loadtxt(path, dtype=np.float32)
    if grid.shape != (IA, JA):
        raise ValueError(f"Unexpected grid_a.grd shape: {grid.shape}")
    grid[(grid > 0.0) & (grid < 10.0)] = np.float32(10.0)
    return grid


def _read_deform_a(path: Path, ids: int, ide: int, jds: int, jde: int) -> np.ndarray:
    # tsunami1.for:171-180 (DEFORMA): the initial elevation window. Written
    # by tsdhn.deform.write_deform_grid (F9.3-equivalent fixed width, always
    # whitespace-separable for |value| < 1000).
    values = np.array(path.read_text().split(), dtype=np.float32)
    rows = ide - ids + 1
    cols = jde - jds + 1
    if values.size != rows * cols:
        raise ValueError(
            f"Unexpected deform_a.grd size: {values.size} values, "
            f"expected {rows}x{cols} for window {ids}:{ide},{jds}:{jde}"
        )
    return values.reshape(rows, cols)


def _hmn(h: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """tsunami1.for:277-298 (HMN): depths at the staggered discharge nodes.

    HM averages along I (last row keeps H itself), HN along J (last column
    keeps H itself).
    """
    hm = np.empty_like(h)
    hn = np.empty_like(h)
    half = np.float32(0.5)
    hm[:-1, :] = half * (h[:-1, :] + h[1:, :])
    hm[-1, :] = h[-1, :]
    hn[:, :-1] = half * (h[:, :-1] + h[:, 1:])
    hn[:, -1] = h[:, -1]
    return hm, hn


def _prelim(
    hm: np.ndarray, hn: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """tsunami1.for:248-272 (PRELIM): latitude-dependent mass factors RX/CJ
    and the momentum factor grids XX/YY.

    RZ/RN advance by repeated float32 addition of DA in the Fortran loop --
    replicated as a scalar float32 walk (not linspace) so the accumulated
    rounding matches.
    """
    ja = hm.shape[1]
    rx = np.empty(ja, dtype=np.float32)
    cj = np.empty(ja, dtype=np.float32)
    rz = _BLATA * _PI / np.float32(180.0)
    rn = rz + _DA / np.float32(2.0)
    for j in range(ja):
        rx[j] = _DT / (_RT * np.cos(rz) * _DA)
        cj[j] = np.cos(rn)
        rz += _DA
        rn += _DA
    xx = (rx * _GG)[np.newaxis, :] * hm
    yy = _DT * _GG * hn / (_RT * _DA)
    return rx, cj, xx, yy


@_jit
def _mass(
    z1: np.ndarray,
    z2: np.ndarray,
    m1: np.ndarray,
    n1: np.ndarray,
    h: np.ndarray,
    rx: np.ndarray,
    cj: np.ndarray,
) -> None:
    """tsunami1.for:302-319 (MASS): continuity over the interior (I,J >= 2,
    1-indexed), with the |Z|<1e-5 flush; dry cells are forced to zero. The
    I=1/J=1 borders of z2 are never written (they stay 0.0 from init)."""
    ia, ja = h.shape
    zero = np.float32(0.0)
    for i in prange(1, ia):
        for j in range(1, ja):
            if h[i, j] > zero:
                z = (
                    z1[i, j]
                    - rx[j] * (m1[i, j] - m1[i - 1, j])
                    - rx[j] * (n1[i, j] * cj[j] - n1[i, j - 1] * cj[j - 1])
                )
                if abs(z) < _FLUSH:
                    z = zero
                z2[i, j] = z
            else:
                z2[i, j] = zero


@_jit
def _bout(
    z2: np.ndarray,
    m_prev: np.ndarray,
    n_prev: np.ndarray,
    h: np.ndarray,
) -> None:
    """tsunami1.for:355-390 (BOUT): open-boundary radiation on the four grid
    edges (rows J=2/JA then columns I=2/IA, in that order -- the corner
    cells written by both passes take the second write, like Fortran).

    Fortran reads M/N level 2 here, but CHAN made level 2 equal to level 1
    at the end of the previous step, so the buffer-swap port passes the
    level-1 (previous-step) momentum as m_prev/n_prev.
    """
    ia, ja = h.shape
    half = np.float32(0.5)
    zero = np.float32(0.0)
    for pass_index in range(2):
        j = 1 if pass_index == 0 else ja - 1
        for i in prange(1, ia - 1):
            if h[i, j] < zero:
                continue
            cc = np.sqrt(_GG * h[i, j])
            uu = half * abs(m_prev[i, j] + m_prev[i - 1, j])
            n_edge = n_prev[i, j] if pass_index == 0 else n_prev[i, j - 1]
            uu = np.sqrt(uu * uu + n_edge * n_edge)
            zz = uu / cc
            if (pass_index == 0 and n_edge > zero) or (
                pass_index == 1 and n_edge < zero
            ):
                zz = -zz
            z2[i, j] = zz
    for pass_index in range(2):
        i = 1 if pass_index == 0 else ia - 1
        for j in prange(1, ja - 1):
            if h[i, j] < zero:
                continue
            cc = np.sqrt(_GG * h[i, j])
            uu = half * abs(n_prev[i, j] + n_prev[i, j - 1])
            m_edge = m_prev[i, j] if pass_index == 0 else m_prev[i - 1, j]
            uu = np.sqrt(uu * uu + m_edge * m_edge)
            zz = uu / cc
            if (pass_index == 0 and m_edge > zero) or (
                pass_index == 1 and m_edge < zero
            ):
                zz = -zz
            z2[i, j] = zz


@_jit
def _mmnt(
    z2: np.ndarray,
    m1: np.ndarray,
    m2: np.ndarray,
    n1: np.ndarray,
    n2: np.ndarray,
    h: np.ndarray,
    xx: np.ndarray,
    yy: np.ndarray,
) -> None:
    """tsunami1.for:323-351 (MMNT): momentum from the *new* elevation; a
    discharge needs both flanking cells wet, else it is zeroed. M's last
    row (I=IA) and N's last column (J=JA) are never written (stay 0.0)."""
    ia, ja = h.shape
    zero = np.float32(0.0)
    for i in prange(1, ia - 1):
        for j in range(1, ja):
            if h[i, j] > zero and h[i + 1, j] > zero:
                m = m1[i, j] - xx[i, j] * (z2[i + 1, j] - z2[i, j])
                if abs(m) < _FLUSH:
                    m = zero
                m2[i, j] = m
            else:
                m2[i, j] = zero
    for i in prange(1, ia):
        for j in range(1, ja - 1):
            if h[i, j] > zero and h[i, j + 1] > zero:
                n = n1[i, j] - yy[i, j] * (z2[i, j + 1] - z2[i, j])
                if abs(n) < _FLUSH:
                    n = zero
                n2[i, j] = n
            else:
                n2[i, j] = zero


def _write_green_dat(path: Path, rows: list[tuple[float, np.ndarray]]) -> None:
    # tsunami1.for:100 -- WRITE(4,'(F7.1,100F7.3)'): fixed 7-char fields,
    # no separators beyond the field widths themselves.
    with atomic_write(path) as tmp_path, tmp_path.open("w") as handle:
        for minutes, gauges in rows:
            handle.write(
                f"{minutes:7.1f}" + "".join(f"{z:7.3f}" for z in gauges) + "\n"
            )


def _write_zmax_a(path: Path, zmxa: np.ndarray) -> None:
    # tsunami1.for:124-130 -- FORMAT(4000F8.3): fixed 8-char fields, one
    # grid row per line (same savetxt pattern as deform.write_deform_grid).
    with atomic_write(path) as tmp_path:
        np.savetxt(tmp_path, zmxa, fmt="%8.3f", delimiter="")


# Checkpoint often enough to bound restart work without writing the large
# solver state on every step.
_CHECKPOINT_INTERVAL = 2000


def _checkpoint_path(working_dir: Path) -> Path:
    return working_dir / "zfolder" / "_checkpoint.npz"


def _write_checkpoint(
    path: Path,
    k: int,
    z1: np.ndarray,
    z2: np.ndarray,
    m1: np.ndarray,
    m2: np.ndarray,
    n1: np.ndarray,
    n2: np.ndarray,
    zmxa: np.ndarray,
    gauge_rows: list[tuple[float, np.ndarray]],
) -> None:
    gauge_minutes = np.array([minutes for minutes, _ in gauge_rows], dtype=np.float64)
    gauge_values = (
        np.stack([gauges for _, gauges in gauge_rows])
        if gauge_rows
        else np.empty((0, 0), dtype=np.float32)
    )
    with atomic_write(path) as tmp_path, tmp_path.open("wb") as handle:
        np.savez(
            handle,
            pipeline_version=np.int64(PIPELINE_VERSION),
            k=np.int64(k),
            z1=z1,
            z2=z2,
            m1=m1,
            m2=m2,
            n1=n1,
            n2=n2,
            zmxa=zmxa,
            gauge_minutes=gauge_minutes,
            gauge_values=gauge_values,
        )


# A resumed run's state, or None if there is no usable checkpoint on disk.
type _TsunamiState = tuple[
    int,  # k, the last fully-completed step
    np.ndarray,  # z1
    np.ndarray,  # z2
    np.ndarray,  # m1
    np.ndarray,  # m2
    np.ndarray,  # n1
    np.ndarray,  # n2
    np.ndarray,  # zmxa
    list[tuple[float, np.ndarray]],  # gauge_rows
]


def _read_checkpoint(
    path: Path, *, ia: int, ja: int, n_gauges: int
) -> _TsunamiState | None:
    if not path.is_file():
        return None
    try:
        with np.load(path) as data:
            if int(data["pipeline_version"]) != PIPELINE_VERSION:
                raise ValueError("checkpoint predates a pipeline version bump")
            k = int(data["k"])
            z1, z2 = data["z1"], data["z2"]
            m1, m2 = data["m1"], data["m2"]
            n1, n2 = data["n1"], data["n2"]
            zmxa = data["zmxa"]
            gauge_minutes = data["gauge_minutes"]
            gauge_values = data["gauge_values"]

        for array in (z1, z2, m1, m2, n1, n2, zmxa):
            if array.shape != (ia, ja) or array.dtype != np.float32:
                raise ValueError("checkpoint array shape/dtype mismatch")
        if gauge_values.shape[0] and gauge_values.shape[1] != n_gauges:
            raise ValueError("checkpoint gauge count mismatch")
        if not (0 <= k <= KE):
            raise ValueError("checkpoint step index out of range")
    except Exception:
        logger.warning(
            "tsunami checkpoint at %s is unusable, starting from step 0", path
        )
        return None

    gauge_rows = list(zip(gauge_minutes.tolist(), gauge_values, strict=True))
    return k, z1, z2, m1, m2, n1, n2, zmxa, gauge_rows


def run_tsunami(working_dir: Path) -> None:
    """Run the tsunami step and write the gauge and maximum-height grids."""
    zfolder = working_dir / "zfolder"
    zfolder.mkdir(exist_ok=True)

    ids, ide, jds, jde = _read_xyo_dat(working_dir / "xyo.dat")
    ip, jp = _read_tidal_dat(working_dir / "tidal.dat")
    h = _read_grid_a(working_dir / "bathy" / "grid_a.grd")

    hm, hn = _hmn(h)
    rx, cj, xx, yy = _prelim(hm, hn)

    checkpoint_path = _checkpoint_path(working_dir)
    checkpoint = _read_checkpoint(checkpoint_path, ia=IA, ja=JA, n_gauges=len(ip))

    if checkpoint is not None:
        start_k, z1, z2, m1, m2, n1, n2, zmxa, gauge_rows = checkpoint
        logger.info("resuming tsunami run from step %d of %d", start_k, KE)
    else:
        start_k = 0
        # CEROS (tsunami1.for:493-507) zeroes both time levels; the
        # COMMON-block ZMXA starts zeroed by static storage. The I=1/J=1
        # borders (0-indexed row/col 0) are never written by any live
        # subroutine afterward.
        z1 = np.zeros((IA, JA), dtype=np.float32)
        z2 = np.zeros((IA, JA), dtype=np.float32)
        m1 = np.zeros((IA, JA), dtype=np.float32)
        m2 = np.zeros((IA, JA), dtype=np.float32)
        n1 = np.zeros((IA, JA), dtype=np.float32)
        n2 = np.zeros((IA, JA), dtype=np.float32)
        zmxa = np.zeros((IA, JA), dtype=np.float32)

        # DEFORMA: initial condition into level 1 (1-indexed IDS..IDE, JDS..JDE).
        z1[ids - 1 : ide, jds - 1 : jde] = _read_deform_a(
            working_dir / "deform_a.grd", ids, ide, jds, jde
        )

        gauge_rows = []

    gauge_i = ip - 1
    gauge_j = jp - 1

    for k in range(start_k + 1, KE + 1):
        kk = k - 1
        if k % 1000 == 0:
            logger.info("tsunami step %d of %d", k, KE)

        _mass(z1, z2, m1, n1, h, rx, cj)
        _bout(z2, m1, n1, h)
        _mmnt(z2, m1, m2, n1, n2, h, xx, yy)

        # Gauge sampling + ZMAX (tsunami1.for:96-103): both only every KD
        # steps -- ZMXA is the max over *sampled* fields, not every step.
        if kk % KD == 0:
            gauge_rows.append((kk * float(_DT) / 60.0, z2[gauge_i, gauge_j].copy()))
            np.maximum(zmxa, z2, out=zmxa)

        # CHAN (tsunami1.for:480-491): rotate time levels via buffer swap.
        z1, z2 = z2, z1
        m1, m2 = m2, m1
        n1, n2 = n2, n1

        if k % _CHECKPOINT_INTERVAL == 0:
            _write_checkpoint(
                checkpoint_path, k, z1, z2, m1, m2, n1, n2, zmxa, gauge_rows
            )

    _write_green_dat(zfolder / "green.dat", gauge_rows)
    _write_zmax_a(zfolder / "zmax_a.grd", zmxa)
    checkpoint_path.unlink(missing_ok=True)
