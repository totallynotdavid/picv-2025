import logging
from typing import Dict, List, Tuple

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.io import loadmat

from orchestrator.core.config import EARTH_RADIUS, GRAVITY, MODEL_DIR
from orchestrator.models.schemas import (
    CalculationResponse,
    EarthquakeInput,
    TsunamiTravelResponse,
)
from orchestrator.utils.geo import (
    calculate_distance_to_coast,
    determine_epicenter_location,
    determine_tsunami_warning,
    format_arrival_time,
)

logger = logging.getLogger(__name__)

# Define a constant for converting rupture dimensions to nautical miles
# This constant is used in rectangle corner calculations
NM_CONVERSION = 60 * 1853


class TsunamiCalculator:
    def __init__(self):
        """Initialize the TsunamiCalculator with necessary constants and data."""
        self.data_path = MODEL_DIR
        self.g = GRAVITY
        self.R = EARTH_RADIUS
        self._load_data()
        self._load_static_files()

    def _load_data(self):
        """Load and preprocess required data files for calculations."""
        try:
            # Load and process pacifico.mat
            pacifico_path = self.data_path / "pacifico.mat"
            pacifico = loadmat(pacifico_path)

            self.xa = pacifico["xa"].flatten()
            self.ya = pacifico["ya"].flatten()
            self.bathymetry = pacifico["A"]

            self.vlon = self.xa - 360
            self.vlat = self.ya

            # Ensure correct orientation of latitude data
            if self.vlat[0] > self.vlat[-1]:
                self.vlat = self.vlat[::-1]
                self.bathymetry = self.bathymetry[::-1, :]

            # Create bathymetry interpolator
            self.bathy_interpolator = RegularGridInterpolator(
                (self.vlat, self.vlon),
                self.bathymetry,
                bounds_error=False,
                fill_value=None,
            )

            # Load maper1.mat (used for coastal points)
            maper1_path = self.data_path / "maper1.mat"
            maper1 = loadmat(maper1_path)
            self.maper1 = maper1["A"]

            logger.debug("Data loaded successfully")
        except FileNotFoundError as e:
            logger.exception(f"Required data file not found: {e}")
            raise
        except Exception as e:
            logger.exception(f"Error loading data: {e}")
            raise

    def _load_static_files(self):
        """
        Preload static files that are reused on every calculation:
        - Focal mechanism file (mecfoc.dat)
        - Ports file (puertos.txt)
        """
        try:
            # Load focal mechanism data once
            mech_path = self.data_path / "mecfoc.dat"
            self.mechanism_data = np.loadtxt(mech_path)

            # Adjust longitudes if needed
            self.mechanism_data[:, 0] = np.where(
                self.mechanism_data[:, 0] > 0,
                self.mechanism_data[:, 0] - 360,
                self.mechanism_data[:, 0],
            )

            # Load ports data once
            puertos_path = self.data_path / "puertos.txt"
            with open(puertos_path, "r") as f:
                self.ports = f.readlines()

            logger.debug("Static files loaded successfully")
        except Exception as e:
            logger.exception("Error loading static files: %s", e)
            raise

    def calculate_earthquake_parameters(
        self, data: EarthquakeInput
    ) -> CalculationResponse:
        """
        Calculate earthquake parameters and assess tsunami risk.
        """
        try:
            # Calculate basic earthquake parameters
            L = 10 ** (0.55 * data.Mw - 2.19)  # length in km
            W = 10 ** (0.31 * data.Mw - 0.63)  # width in km
            M0 = 10 ** (1.5 * data.Mw + 9.1)  # seismic moment (N*m)
            u = 4.5e10  # rigidity (N/m^2)
            D = M0 / (u * (L * 1000) * (W * 1000))  # dislocation (m)

            # Get additional parameters from focal mechanism (using preloaded data)
            azimuth, dip = self._get_focal_mechanism(data.lon0, data.lat0)

            # Calculate rectangle parameters (fault plane)
            rect_params, rect_corners = self._calculate_rectangle_parameters(
                L, W, data.lon0, data.lat0, azimuth, dip
            )

            distance_to_coast = calculate_distance_to_coast(
                self.maper1[:, :2], data.lon0, data.lat0
            )

            # Get bathymetry at epicenter
            h0 = self.bathy_interpolator((data.lat0, data.lon0))

            # Determine location and warning
            location = determine_epicenter_location(h0, distance_to_coast)
            warning = determine_tsunami_warning(data.Mw, data.h, h0, distance_to_coast)

            # Write hypo.dat file (for model execution)
            self._write_hypo_dat(data)

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

        except Exception:
            logger.exception("Error calculating earthquake parameters")
            raise

    def calculate_tsunami_travel_times(
        self, data: EarthquakeInput
    ) -> TsunamiTravelResponse:
        """
        Calculate tsunami travel times to various ports.
        """
        try:
            arrival_times = {}
            distances = {}
            time0 = float(data.hhmm[:2]) + float(data.hhmm[2:]) / 60

            for port in self.ports:
                if len(port) < 15:
                    continue

                parts = port.split()
                if len(parts) < 3:
                    logger.warning(f"Insufficient data in port line: '{port.strip()}'")
                    continue

                try:
                    port_name = port[:15].strip()
                    port_lon = float(parts[0])
                    port_lat = float(parts[1])

                    distance, travel_time = self._calculate_travel_time(
                        data.lon0, data.lat0, port_lon, port_lat, time0
                    )

                    arrival_times[port_name] = format_arrival_time(
                        travel_time, data.dia
                    )
                    distances[port_name] = distance

                except ValueError as e:
                    logger.error(f"Error processing port data '{port.strip()}': {e}")
                    continue

            epicenter_info = {
                "date": data.dia,
                "time": data.hhmm,
                "latitude": f"{data.lat0:.2f}",
                "longitude": f"{data.lon0:.2f}",
                "depth": f"{data.h:.0f}",
                "magnitude": f"{data.Mw:.1f}",
            }

            return TsunamiTravelResponse(
                arrival_times=arrival_times,
                distances=distances,
                epicenter_info=epicenter_info,
            )

        except Exception:
            logger.exception("Error calculating tsunami travel times")
            raise

    def _get_focal_mechanism(self, lon0: float, lat0: float) -> Tuple[float, float]:
        """
        Get focal mechanism parameters for given coordinates.

        Args:
            lon0: Longitude of epicenter
            lat0: Latitude of epicenter

        Returns:
            Tuple of (azimuth, dip)
        """
        try:
            mech_data = self.mechanism_data
            distances = np.sqrt(
                (mech_data[:, 0] - lon0) ** 2 + (mech_data[:, 1] - lat0) ** 2
            )
            closest_idx = np.argmin(distances)

            return mech_data[closest_idx, 2], 18.0
        except Exception:
            logger.exception("Error getting focal mechanism")
            raise

    def _calculate_rectangle_parameters(
        self, L: float, W: float, lon0: float, lat0: float, azimuth: float, dip: float
    ) -> Tuple[Dict[str, float], List[Dict[str, float]]]:
        """
        Calculate rectangle (fault plane) parameters and its corner coordinates.

        Args:
            L: Rupture length in km.
            W: Rupture width in km.
            lon0: Epicenter longitude.
            lat0: Epicenter latitude.
            azimuth: Fault strike in degrees.
            dip: Dip angle in degrees (fixed at 18 in MATLAB).

        Returns:
            A tuple containing:
            - A dictionary of rectangle parameters:
              L1, W1, beta, alfa, h1, a1, b1, xo, yo.
            - A list of dictionaries for the rectangle corners
              (each with 'lon' and 'lat').
        """
        # Convert rupture dimensions from km to m
        L1 = L * 1000  # length in m
        W1 = W * 1000 * np.cos(np.deg2rad(dip))
        beta = np.degrees(np.arctan(W1 / L1))
        alfa = azimuth - 270
        h1 = np.sqrt(L1**2 + W1**2)
        a1 = 0.5 * h1 * np.sin(np.deg2rad(alfa + beta)) / 1000  # in km
        b1 = 0.5 * h1 * np.cos(np.deg2rad(alfa + beta)) / 1000  # in km
        xo = lon0 + b1 / 110
        yo = lat0 - a1 / 110

        rect_params = {
            "L1": L1,
            "W1": W1,
            "beta": beta,
            "alfa": alfa,
            "h1": h1,
            "a1": a1,
            "b1": b1,
            "xo": xo,
            "yo": yo,
        }

        # Calculate rectangle corners using vectorized operations
        a1_prime = -np.radians(azimuth - 90)
        a2_prime = -np.radians(azimuth)
        r1 = L1 / NM_CONVERSION
        r2 = W1 / NM_CONVERSION

        sx = (
            np.array(
                [
                    0,
                    r1 * np.cos(a1_prime),
                    r1 * np.cos(a1_prime) + r2 * np.cos(a2_prime),
                    r2 * np.cos(a2_prime),
                    0,
                ]
            )
            + xo
        )

        sy = (
            np.array(
                [
                    0,
                    r1 * np.sin(a1_prime),
                    r1 * np.sin(a1_prime) + r2 * np.sin(a2_prime),
                    r2 * np.sin(a2_prime),
                    0,
                ]
            )
            + yo
        )

        rectangle_corners = [
            {"lon": lon, "lat": lat} for lon, lat in zip(sx, sy, strict=False)
        ]
        return rect_params, rectangle_corners

    def _calculate_travel_time(
        self, lon0: float, lat0: float, port_lon: float, port_lat: float, time0: float
    ) -> Tuple[float, float]:
        """
        Calculate tsunami travel time between two points.

        Args:
            lon0: Source longitude
            lat0: Source latitude
            port_lon: Destination longitude
            port_lat: Destination latitude
            time0: Initial time

        Returns:
            Tuple of (distance, travel_time)
        """
        try:
            # Convert to radians
            t1 = np.pi / 2 - np.radians(lat0)
            f1 = np.radians(lon0)
            t2 = np.pi / 2 - np.radians(port_lat)
            f2 = np.radians(port_lon)

            # Calculate great circle distance using spherical law of cosines
            cosen = np.sin(t1) * np.sin(t2) * np.cos(f1 - f2) + np.cos(t1) * np.cos(t2)
            alfa = np.arccos(cosen)
            distance = self.R * alfa

            # Determine travel time based on distance and location
            if distance >= 750:
                travel_time = distance / 790 + 0.2
            elif not (-19 <= lat0 <= 0) and distance < 750:
                travel_time = distance / 700
            else:
                travel_time = self._calculate_detailed_travel_time(
                    lon0, lat0, port_lon, port_lat, distance, alfa
                )

            return distance, travel_time + time0

        except Exception:
            logger.exception("Error calculating travel time")
            raise

    def _calculate_detailed_travel_time(
        self,
        lon0: float,
        lat0: float,
        port_lon: float,
        port_lat: float,
        distance: float,
        alfa: float,
    ) -> float:
        """
        Calculate detailed tsunami travel time using bathymetry data.

        Args:
            lon0: Source longitude
            lat0: Source latitude
            port_lon: Destination longitude
            port_lat: Destination latitude
            distance: Great circle distance
            alfa: Angular distance

        Returns:
            Calculated travel time
        """
        try:
            # Compute unit velocity vector
            # (direction scaled to 110 for geographic conversion)
            vu = np.array([port_lon - lon0, port_lat - lat0]) / distance * 110
            n = 100
            delta = (alfa * 180 / np.pi) / n  # step size in degrees

            # Vectorize the computation of positions along the path
            indices = np.arange(0, n + 1).reshape(-1, 1)  # shape (n+1, 1)
            P0 = np.array([lon0, lat0])  # starting point (lon, lat)

            # Each row: P = P0 + (i * delta) * vu
            positions = P0 + indices * delta * vu  # shape (n+1, 2)

            # The interpolator expects (lat, lon), so swap columns:
            points = positions[:, [1, 0]]

            # Get absolute bathymetry values along the path
            h = np.abs(self.bathy_interpolator(points))

            # Compute tsunami velocity (converted to km/h)
            v = np.sqrt(self.g * h) * 3.6

            # Simpson's rule integration
            delta_distance = (alfa / n) * self.R
            y = 1 / v

            # Simpson integration: endpoints + weighted sums for even/odd indices
            integral = (delta_distance / 3) * (
                y[0] + y[-1] + 4 * np.sum(y[1:-1:2]) + 2 * np.sum(y[2:-1:2])
            )

            travel_time = 0.50 * integral

            # Empirical adjustments to travel time
            if travel_time > 3.0:
                travel_time = distance / 733 + 0.25
            elif 1.4 < travel_time < 3.0:
                travel_time = distance / 690 + 0.2

            return travel_time

        except Exception:
            logger.exception("Error calculating detailed travel time")
            raise

    def _write_hypo_dat(self, data: EarthquakeInput):
        """
        Write earthquake parameters to hypo.dat file.

        Args:
            data: EarthquakeInput object containing earthquake data
        """
        try:
            with open("hypo.dat", "w") as f:
                f.writelines(
                    [
                        f"{data.hhmm}\n",
                        f"{data.lon0:.2f}\n",
                        f"{data.lat0:.2f}\n",
                        f"{data.h:.0f}\n",
                        f"{data.Mw:.1f}\n",
                    ]
                )
        except Exception:
            logger.exception("Error writing hypo.dat")
            raise
