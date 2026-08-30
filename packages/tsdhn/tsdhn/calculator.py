"""Source parameters and approximate port arrival times."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.io import loadmat

from tsdhn.constants import STANDARD_GRAVITY_M_PER_S2, TSUNAMI_MODEL_EARTH_RADIUS_KM
from tsdhn.domain import (
    CalculationResponse,
    EarthquakeInput,
    TsunamiTravelResponse,
)
from tsdhn.runtime import RuntimeContext, validate_model_dir
from tsdhn.utils.geo import (
    calculate_distance_to_coast,
    determine_epicenter_location,
    determine_tsunami_warning,
    format_arrival_time,
)

logger = logging.getLogger(__name__)

# Legacy corner formulas use 60 nautical miles per degree.
NM_CONVERSION = 60 * 1853

# Rigidity (N/m^2). Matches model/fault_plane.f90.
RIGIDITY_N_PER_M2 = 4.0e10


def rupture_dimensions(Mw: float) -> tuple[float, float]:
    """Return Papazachos et al. (2004) rupture length and width in km."""
    L = 10 ** (0.55 * Mw - 2.19)
    W = 10 ** (0.31 * Mw - 0.63)
    return L, W


def average_slip(Mw: float, L: float, W: float) -> tuple[float, float]:
    """Hanks and Kanamori moment magnitude relation, solved for slip.

    L, W in km. Returns (M0, D): seismic moment (N*m), average dislocation
    (m).
    """
    M0 = 10 ** (1.5 * Mw + 9.1)
    D = M0 / (RIGIDITY_N_PER_M2 * (L * 1000) * (W * 1000))
    return M0, D


@dataclass(frozen=True)
class Port:
    name: str
    lon: float
    lat: float


def parse_port_line(line: str) -> Port | None:
    data, _, comment = line.partition("%")
    parts = data.split()
    if len(parts) < 2:
        logger.warning("Insufficient coordinate data in port line: '%s'", line.strip())
        return None

    try:
        lon = float(parts[0])
        lat = float(parts[1])
    except ValueError:
        logger.warning("Invalid coordinate data in port line: '%s'", line.strip())
        return None

    name_parts = comment.split()
    if len(name_parts) > 1 and len(name_parts[-1]) == 1:
        name_parts = name_parts[:-1]
    name = " ".join(name_parts) or f"{lat:.4f},{lon:.4f}"
    return Port(name=name, lon=lon, lat=lat)


def calculate_rectangle_parameters(
    L: float,
    W: float,
    lon0: float,
    lat0: float,
    azimuth: float,
    dip: float,
    on_checkpoint: Callable[[str, Any], None] | None = None,
) -> tuple[dict[str, float], list[dict[str, float]]]:
    """Return the MATLAB-compatible fault-plane parameters and corners.

    The optional `on_checkpoint` callback receives each named intermediate in
    calculation order.
    """

    def checkpoint(name: str, value: Any) -> None:
        if on_checkpoint is not None:
            on_checkpoint(name, value)

    L1 = L * 1000
    checkpoint("L1", L1)
    W1 = W * 1000 * np.cos(np.deg2rad(dip))
    checkpoint("W1", W1)
    beta = np.degrees(np.arctan(W1 / L1))
    checkpoint("beta", beta)
    alfa = azimuth - 270
    checkpoint("alfa", alfa)
    h1 = np.hypot(L1, W1)
    checkpoint("h1", h1)

    # Keep the names used by the legacy report files.
    params = {
        "L1": L1,
        "W1": W1,
        "beta": beta,
        "alfa": alfa,
        "h1": h1,
        "a1": 0.5 * h1 * np.sin(np.deg2rad(alfa + beta)) / 1000,
        "b1": 0.5 * h1 * np.cos(np.deg2rad(alfa + beta)) / 1000,
        # Use the longitude frame expected by the legacy grid.
        "xo": lon0 + (0.5 * h1 * np.cos(np.deg2rad(alfa + beta)) / 1000) / 111.0,
        "yo": lat0 - (0.5 * h1 * np.sin(np.deg2rad(alfa + beta)) / 1000) / 111.0,
    }
    checkpoint("a1", params["a1"])
    checkpoint("b1", params["b1"])
    checkpoint("xo", params["xo"])
    checkpoint("yo", params["yo"])

    # Legacy geometry expresses fault-plane offsets in degree-space nautical miles.
    angles = -np.radians([(azimuth - 90), azimuth])

    r = np.array([L1, W1]) / NM_CONVERSION

    sx = (
        r[0] * np.cos(angles[0]) * np.array([0, 1, 1, 0, 0])
        + r[1] * np.cos(angles[1]) * np.array([0, 0, 1, 1, 0])
    ) + params["xo"]

    sy = (
        r[0] * np.sin(angles[0]) * np.array([0, 1, 1, 0, 0])
        + r[1] * np.sin(angles[1]) * np.array([0, 0, 1, 1, 0])
    ) + params["yo"]

    corners = [{"lon": x, "lat": y} for x, y in zip(sx, sy, strict=False)]
    checkpoint(
        "corners", np.array([[corner["lon"], corner["lat"]] for corner in corners])
    )

    return params, corners


class TsunamiCalculator:
    def __init__(self, model_dir: Path | None = None) -> None:
        self.model_dir = (
            validate_model_dir(model_dir.resolve())
            if model_dir is not None
            else RuntimeContext.resolve().model_dir
        )
        self.xa: np.ndarray
        self.ya: np.ndarray
        self.vlon: np.ndarray | None = None
        self.vlat: np.ndarray | None = None
        self.bathymetry: np.ndarray | None = None
        self.bathy_interpolator: RegularGridInterpolator | None = None
        self.maper1: np.ndarray | None = None
        self.mechanism_data: np.ndarray | None = None
        self.ports: list[str] | None = None
        self._ensure_data_loaded()

    def _ensure_data_loaded(self) -> None:
        self._load_geographic_data()
        self._load_static_files()

    def _load_geographic_data(self) -> None:
        try:
            pacifico_path = self.model_dir / "pacifico.mat"
            pacifico = loadmat(pacifico_path)

            self.xa = pacifico["xa"].flatten()
            self.ya = pacifico["ya"].flatten()
            self.bathymetry = pacifico["A"]

            # Model bathymetry uses 0..360 longitudes; inputs use -180..180.
            self.vlon = self.xa - 360
            self.vlat = self.ya
            if self.vlat[0] > self.vlat[-1]:
                self.vlat = self.vlat[::-1]
                self.bathymetry = self.bathymetry[::-1, :]

            self.bathy_interpolator = RegularGridInterpolator(
                (self.vlat, self.vlon),
                self.bathymetry,
                bounds_error=False,
                fill_value=None,
            )

            maper1_path = self.model_dir / "maper1.mat"
            self.maper1 = loadmat(maper1_path)["A"]
        except Exception as e:
            logger.exception("Failed to load bathymetric data")
            raise RuntimeError("Bathymetric data initialization failed") from e

    def _load_static_files(self) -> None:
        try:
            mech_path = self.model_dir / "mecfoc.dat"
            self.mechanism_data = np.loadtxt(mech_path)

            # CMT data uses eastern-positive longitudes; lookup uses western negatives.
            self.mechanism_data[:, 0] = np.where(
                self.mechanism_data[:, 0] > 0,
                self.mechanism_data[:, 0] - 360,
                self.mechanism_data[:, 0],
            )

            puertos_path = self.model_dir / "puertos.txt"
            with open(puertos_path) as f:
                self.ports = f.readlines()
        except Exception as e:
            logger.exception("Failed to load static files")
            raise RuntimeError("Static file initialization failed") from e

    def calculate_earthquake_parameters(
        self, data: EarthquakeInput, output_dir: Path | None = None
    ) -> CalculationResponse:
        """Calculate source parameters and write hypo.dat for the simulation."""
        try:
            L, W = rupture_dimensions(data.Mw)  # km
            M0, D = average_slip(data.Mw, L, W)  # N*m, m

            azimuth, dip = self._get_focal_mechanism(data.lon0, data.lat0)

            rect_params, rect_corners = calculate_rectangle_parameters(
                L, W, data.lon0, data.lat0, azimuth, dip
            )

            if self.maper1 is None:
                raise RuntimeError("Coastal data not loaded")

            distance_to_coast = calculate_distance_to_coast(
                self.maper1[:, :2], data.lon0, data.lat0
            )

            if self.bathy_interpolator is None:
                raise RuntimeError("Bathymetry interpolator not loaded")

            h0 = self.bathy_interpolator((data.lat0, data.lon0))

            location = determine_epicenter_location(h0, distance_to_coast)
            warning = determine_tsunami_warning(data.Mw, data.h, h0, distance_to_coast)

            self._write_hypo_dat(data, output_dir or Path.cwd())

            return CalculationResponse(
                length=L,
                width=W,
                dislocation=D,
                seismic_moment=M0,
                tsunami_warning=warning,
                distance_to_coast=distance_to_coast,
                azimuth=azimuth,
                dip=dip,
                epicenter_location=location,
                rectangle_parameters=rect_params,
                rectangle_corners=rect_corners,
            )
        except Exception as e:
            logger.exception("Earthquake parameter calculation failed")
            raise RuntimeError("Earthquake calculation error") from e

    def calculate_tsunami_travel_times(
        self, data: EarthquakeInput
    ) -> TsunamiTravelResponse:
        try:
            if self.ports is None:
                raise RuntimeError("Port data not loaded")
            if data.hhmm is None:
                raise RuntimeError("hhmm must be provided")

            arrival_times: dict[str, str] = {}
            distances: dict[str, float] = {}
            time0 = float(data.hhmm[:2]) + float(data.hhmm[2:]) / 60  # Decimal hours

            for port in self.ports:
                if len(port) < 15:
                    continue

                parsed_port = parse_port_line(port)
                if parsed_port is None:
                    continue

                try:
                    distance, travel_time = self._calculate_travel_time(
                        data.lon0,
                        data.lat0,
                        parsed_port.lon,
                        parsed_port.lat,
                        time0,
                    )

                    arrival_times[parsed_port.name] = format_arrival_time(
                        travel_time, cast(str, data.dia)
                    )
                    distances[parsed_port.name] = distance
                except ValueError, IndexError:
                    continue

            return TsunamiTravelResponse(
                arrival_times=arrival_times,
                distances=distances,
                epicenter_info={
                    "date": cast(str, data.dia),
                    "time": data.hhmm,
                    "latitude": f"{data.lat0:.2f}",
                    "longitude": f"{data.lon0:.2f}",
                    "depth": f"{data.h:.0f}",
                    "magnitude": f"{data.Mw:.1f}",
                },
            )
        except Exception as e:
            logger.exception("Travel time calculation failed")
            raise RuntimeError("Tsunami travel time error") from e

    def _get_focal_mechanism(self, lon0: float, lat0: float) -> tuple[float, float]:
        """Use the nearest Global CMT mechanism because inputs omit strike."""
        if self.mechanism_data is None:
            raise RuntimeError("Mechanism data not loaded")

        distances = np.sqrt(
            (self.mechanism_data[:, 0] - lon0) ** 2
            + (self.mechanism_data[:, 1] - lat0) ** 2
        )
        closest_idx = np.argmin(distances)
        return (
            self.mechanism_data[closest_idx, 2],
            self.mechanism_data[closest_idx, 3],
        )

    def _calculate_travel_time(
        self, lon0: float, lat0: float, port_lon: float, port_lat: float, time0: float
    ) -> tuple[float, float]:
        t1 = np.pi / 2 - np.radians(lat0)
        f1 = np.radians(lon0)
        t2 = np.pi / 2 - np.radians(port_lat)
        f2 = np.radians(port_lon)

        cos_alpha = np.sin(t1) * np.sin(t2) * np.cos(f1 - f2) + np.cos(t1) * np.cos(t2)
        alpha = np.arccos(np.clip(cos_alpha, -1, 1))
        distance = TSUNAMI_MODEL_EARTH_RADIUS_KM * alpha

        # Far-field and outside-Peru paths use empirical speed shortcuts.
        if distance >= 750:
            travel_time = distance / 790 + 0.2
        elif not (-19 <= lat0 <= 0):
            travel_time = distance / 700
        else:
            n_points = 100
            delta = np.degrees(alpha) / n_points
            vu = np.array([port_lon - lon0, port_lat - lat0]) / distance * 110

            indices = np.arange(n_points + 1)[:, None]

            # The interpolator takes (lat, lon), while path points are (lon, lat).
            path_points = np.array([lon0, lat0]) + indices * delta * vu
            bath_points = path_points[:, [1, 0]]

            if self.bathy_interpolator is None:
                raise RuntimeError("Bathymetry interpolator not loaded")

            h = np.abs(self.bathy_interpolator(bath_points))
            v = np.sqrt(STANDARD_GRAVITY_M_PER_S2 * h) * 3.6  # Velocity in km/h

            delta_dist = (alpha / n_points) * TSUNAMI_MODEL_EARTH_RADIUS_KM
            y = 1 / v
            integral = (
                delta_dist
                / 3
                * (y[0] + y[-1] + 4 * y[1:-1:2].sum() + 2 * y[2:-1:2].sum())
            )

            travel_time = 0.5 * integral

            # These inherited calibration rules have no source in the repository.
            if travel_time > 3.0:
                travel_time = distance / 733 + 0.25
            elif 1.4 < travel_time < 3.0:
                travel_time = distance / 690 + 0.2

        return distance, travel_time + time0

    def _write_hypo_dat(self, data: EarthquakeInput, output_dir: Path) -> None:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            hypo_path = output_dir / "hypo.dat"
            with hypo_path.open("w") as f:
                f.write(
                    "\n".join(
                        [
                            data.hhmm or "0000",
                            f"{data.lon0:.2f}",
                            f"{data.lat0:.2f}",
                            f"{data.h:.0f}",
                            f"{data.Mw:.1f}",
                        ]
                    )
                )
        except Exception as e:
            logger.exception("Failed to write hypo.dat")
            raise RuntimeError("Hypo.dat creation failed") from e
