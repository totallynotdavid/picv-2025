"""Linear shallow-water propagation port of `model/tsunami1.for`."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import cast

import numba
import numpy as np

from tsdhn.pipeline_version import PIPELINE_VERSION
from tsdhn.utils.file_utils import atomic_write

logger = logging.getLogger(__name__)

# Numba lacks type stubs for prange; keep this alias typed for mypy.
prange = cast("Callable[[int, int], range]", numba.prange)


def _jit[F: Callable[..., None]](fn: F) -> F:
    # Keep IEEE float32 evaluation order. Parallel writes are independent.
    return cast("F", numba.njit(cache=True, parallel=True)(fn))


IA = 2461
JA = 2056
_DELTA = np.float32(240.0) / np.float32(3600.0)
_DT = np.float32(3.0)
KE = 33602
KD = 20
NG = 17
_RT = np.float32(6.37e6)
_BLATA = np.float32(-76.006)
# Compute pi through float32 atan to match legacy Fortran arithmetic (like deform.py).
_PI = np.float32(4.0) * np.arctan(np.float32(1.0))
_DA = _PI * _DELTA / np.float32(180.0)
_GG = np.float32(9.8)
_FLUSH = np.float32(1.0e-5)


def _read_xyo_dat(path: Path) -> tuple[int, int, int, int]:
    # Parse the first four tokens; trailing values are padding from fault-plane.
    ids, ide, jds, jde = path.read_text().split()[:4]
    return int(float(ids)), int(float(ide)), int(float(jds)), int(float(jde))


def _read_tidal_dat(path: Path) -> tuple[np.ndarray, np.ndarray]:
    # The solver uses gauge indices. Gauge names are metadata only.
    ip = np.empty(NG, dtype=np.int64)
    jp = np.empty(NG, dtype=np.int64)
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    for gauge, line in enumerate(lines[:NG]):
        _name, i_text, j_text = line.split()[:3]
        ip[gauge] = int(i_text)
        jp[gauge] = int(j_text)
    return ip, jp


def _read_grid_a(path: Path) -> np.ndarray:
    # Preserve the legacy shallow-water floor for positive depths below 10 m.
    grid = np.loadtxt(path, dtype=np.float32)
    if grid.shape != (IA, JA):
        raise ValueError(f"Unexpected grid_a.grd shape: {grid.shape}")
    grid[(grid > 0.0) & (grid < 10.0)] = np.float32(10.0)
    return grid


def _read_deform_a(path: Path, ids: int, ide: int, jds: int, jde: int) -> np.ndarray:
    # The file contains the initial elevation for the requested grid window.
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
    """Return depths at the staggered discharge nodes.

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
    """Build latitude and momentum factors for the solver.

    RZ and RN advance by repeated float32 addition of DA. The scalar walk
    preserves the accumulated rounding of the reference solver.
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
    """Apply continuity to wet interior cells and flush small elevations."""
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
    """Apply open-boundary radiation on the four grid edges.

    The edge passes run in a fixed order, so the second pass owns a corner.
    The buffer-swap port passes previous-step momentum explicitly.
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
    """Update momentum from the new elevation across wet cells."""
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
    # Reports read the legacy fixed-width gauge format.
    with atomic_write(path) as tmp_path, tmp_path.open("w") as handle:
        for minutes, gauges in rows:
            handle.write(
                f"{minutes:7.1f}" + "".join(f"{z:7.3f}" for z in gauges) + "\n"
            )


def _write_zmax_a(path: Path, zmxa: np.ndarray) -> None:
    # Reports read the legacy fixed-width maximum-height grid.
    with atomic_write(path) as tmp_path:
        np.savetxt(tmp_path, zmxa, fmt="%8.3f", delimiter="")


# Checkpoints contain every time level needed to resume after a worker restart.
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
        # The first Fortran row and column remain outside the interior update.
        z1 = np.zeros((IA, JA), dtype=np.float32)
        z2 = np.zeros((IA, JA), dtype=np.float32)
        m1 = np.zeros((IA, JA), dtype=np.float32)
        m2 = np.zeros((IA, JA), dtype=np.float32)
        n1 = np.zeros((IA, JA), dtype=np.float32)
        n2 = np.zeros((IA, JA), dtype=np.float32)
        zmxa = np.zeros((IA, JA), dtype=np.float32)

        # Deformation occupies only the one-based window written by fault_plane.
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

        # The maximum grid is sampled with gauges, not at every solver step.
        if kk % KD == 0:
            gauge_rows.append((kk * float(_DT) / 60.0, z2[gauge_i, gauge_j].copy()))
            np.maximum(zmxa, z2, out=zmxa)

        # Boundary radiation has already read the previous momentum buffers.
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
