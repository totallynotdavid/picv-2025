"""Python implementation of `model/fault_plane.f90`.

The implementation uses float64 for the scalar geometry calculations. The
compiled program stores the grid window as integers, so the port truncates
those values before the nearest-grid lookup. Longitudes stay in 0..360 space
after the initial conversion because that is the file format used by the
legacy step.
"""

import math
from pathlib import Path

import numpy as np

from tsdhn.calculator import (
    average_slip,
    calculate_rectangle_parameters,
    rupture_dimensions,
)
from tsdhn.utils.file_utils import atomic_write

_RAKE = 90.0  # fault_plane.f90:64 -- hardcoded, never read from mecfoc.dat
_IA = 2461  # fault_plane.f90:7 -- bathymetry grid dimensions (PARAMETER)
_JA = 2056


def _to_0_360(lon: float) -> float:
    """Convert a negative longitude to the legacy 0..360 convention."""
    return lon + 360.0 if lon < 0 else lon


def _read_hypo_dat(path: Path) -> tuple[str, float, float, float, float]:
    """Mirrors TsunamiCalculator._write_hypo_dat's 5-line format:
    hhmm, lon0, lat0, depth (km), Mw."""
    lines = path.read_text().splitlines()
    hhmm = lines[0].strip()
    lon0 = float(lines[1])
    lat0 = float(lines[2])
    zep_km = float(lines[3])
    mw = float(lines[4])
    return hhmm, lon0, lat0, zep_km, mw


def _nearest_mechanism(
    mecfoc: np.ndarray, xep: float, yep: float
) -> tuple[float, float]:
    """fault_plane.f90:52-64 -- nearest mecfoc.dat row by Euclidean distance
    in 0..360 longitude space. A separate lookup from calculator.py's
    TsunamiCalculator._get_focal_mechanism (which works in -180..180 space)
    -- they agree for alaska_1964 but are two different nearest-neighbor
    searches in different wrap frames, so they can in principle diverge near
    a frame-wrapping boundary."""
    lon = np.where(mecfoc[:, 0] < 0, mecfoc[:, 0] + 360.0, mecfoc[:, 0])
    lat = mecfoc[:, 1]
    dist = np.sqrt((lon - xep) ** 2 + (lat - yep) ** 2)
    pos = int(np.argmin(dist))
    return float(mecfoc[pos, 2]), float(mecfoc[pos, 3])


def _grid_snap(
    xa: np.ndarray, ya: np.ndarray, xo_grid: float, yo: float
) -> tuple[int, int]:
    """fault_plane.f90:96-99 -- nearest bathymetry grid index, 1-indexed to
    match Fortran's minloc."""
    i0 = int(np.argmin(np.abs(xa - xo_grid))) + 1
    j0 = int(np.argmin(np.abs(ya - yo))) + 1
    return i0, j0


def _grid_window(
    xa: np.ndarray, ya: np.ndarray, xep: float, yep: float, l_km: float, mw: float
) -> tuple[int, int, int, int]:
    """Return the legacy integer grid window before nearest-grid lookup."""
    cte = 1.4 if mw > 8.0 else 2.8
    off = cte * l_km / 111.0
    ids = int(np.argmin(np.abs(xa - int(xep - off)))) + 1
    ide = int(np.argmin(np.abs(xa - int(xep + off)))) + 1
    jds = int(np.argmin(np.abs(ya - int(yep - off)))) + 1
    jde = int(np.argmin(np.abs(ya - int(yep + off)))) + 1
    return ids, ide, jds, jde


def _recompute_depth(
    lon0: float, lat0: float, xo: float, yo: float, zep_km: float, az: float, dip: float
) -> float:
    """fault_plane.f90:101-108. Uses the continuous (unshifted) lon0/xo --
    only IDS/IDE/JDS/JDE are integer-typed in Fortran, not xo/yo."""
    delta_x = (lon0 - xo) * 111.0
    delta_y = (lat0 - yo) * 111.0
    h = zep_km - (
        delta_x * math.cos(math.radians(-az)) + delta_y * math.sin(math.radians(-az))
    ) * math.tan(math.radians(dip))
    h_m = h * 1000.0
    if h_m < 0:
        h_m = 5000.0
    return h_m


def _write_pfalla_inp(
    path: Path,
    i0: int,
    j0: int,
    d0_m: float,
    l0_m: float,
    w0_m: float,
    az: float,
    dip: float,
    rake: float,
    h_m: float,
) -> None:
    """fault_plane.f90:111-113. Only consumer is tsdhn.deform's
    _parse_pfalla_inp (whitespace-token parser) -- full formatting freedom.
    d0/l0/w0/h in meters, matching def_oka.f's own pfalla.inp contract."""
    with atomic_write(path) as tmp_path:
        tmp_path.write_text(f"{i0} {j0} {d0_m} {l0_m} {w0_m} {az} {dip} {rake} {h_m}\n")


def _write_xyo_dat(
    path: Path, ids: int, ide: int, jds: int, jde: int, ia: int = _IA, ja: int = _JA
) -> None:
    """fault_plane.f90:121,142. Must stay Fortran-list-directed-readable:
    model/tsunami1.for still reads this file (READ(5,*)IDS,IDE,JDS,JDE,
    only consumes 4 tokens; IA/JA are harmless trailing padding, kept for
    fidelity)."""
    with atomic_write(path) as tmp_path:
        tmp_path.write_text(f"{ids} {ide} {jds} {jde} {ia} {ja}\n")


def _write_meca_dat(
    path: Path,
    xep: float,
    lat0: float,
    zep_km: float,
    az: float,
    dip: float,
    mw: float,
    hhmm: str,
    rake: float = _RAKE,
) -> None:
    """Write the legacy fixed-width `meca.dat` record."""
    fields = "".join(f"{v:7.2f}" for v in (xep, lat0, zep_km, az, dip, rake, mw))
    with atomic_write(path) as tmp_path:
        tmp_path.write_text(f"{fields} 0 0 {hhmm}\n")


def run_fault_plane(working_dir: Path) -> None:
    """Read the workspace inputs and write the fault-plane files."""
    hhmm, lon0, lat0, zep_km, mw = _read_hypo_dat(working_dir / "hypo.dat")
    xep = _to_0_360(lon0)

    l_km, w_km = rupture_dimensions(mw)
    _, dislocation_m = average_slip(mw, l_km, w_km)

    mecfoc = np.loadtxt(working_dir / "mecfoc.dat")
    az, dip = _nearest_mechanism(mecfoc, xep, lat0)

    rect_params, _ = calculate_rectangle_parameters(l_km, w_km, lon0, lat0, az, dip)
    xo, yo = float(rect_params["xo"]), float(rect_params["yo"])

    xa = np.loadtxt(working_dir / "bathy/xa.dat")
    ya = np.loadtxt(working_dir / "bathy/ya.dat")

    if xep < xa[0]:
        raise RuntimeError(
            f"Epicenter is outside the computational grid (xep={xep} < xa[0]={xa[0]})"
        )

    xo_grid = _to_0_360(xo)
    i0, j0 = _grid_snap(xa, ya, xo_grid, yo)
    h_m = _recompute_depth(lon0, lat0, xo, yo, zep_km, az, dip)

    _write_pfalla_inp(
        working_dir / "pfalla.inp",
        i0,
        j0,
        dislocation_m,
        l_km * 1000.0,
        w_km * 1000.0,
        az,
        dip,
        _RAKE,
        h_m,
    )

    ids, ide, jds, jde = _grid_window(xa, ya, xep, lat0, l_km, mw)
    _write_xyo_dat(working_dir / "xyo.dat", ids, ide, jds, jde)

    _write_meca_dat(working_dir / "meca.dat", xep, lat0, zep_km, az, dip, mw, hhmm)
