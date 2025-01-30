import logging
from typing import Tuple

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


class TsunamiCalculator:
    def __init__(self):
        """Initialize the TsunamiCalculator with necessary constants and data."""
        self.data_path = MODEL_DIR
        self.g = GRAVITY
        self.R = EARTH_RADIUS
        self._load_data()

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

            # Load maper1.mat
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

    def calculate_earthquake_parameters(
        self, data: EarthquakeInput
    ) -> CalculationResponse:
        """
        Calculate earthquake parameters and assess tsunami risk.

        Args:
            data: EarthquakeInput object containing earthquake data

        Returns:
            CalculationResponse object with computed parameters
        """
        try:
            # Calculate basic earthquake parameters
            L = 10 ** (0.55 * data.Mw - 2.19)  # length
            W = 10 ** (0.31 * data.Mw - 0.63)  # width
            M0 = 10 ** (1.5 * data.Mw + 9.1)  # seismic moment
            u = 4.5e10  # rigidity
            D = M0 / (u * (L * 1000) * (W * 1000))  # dislocation

            # Get additional parameters
            azimuth, dip = self._get_focal_mechanism(data.lon0, data.lat0)
            distance_to_coast = calculate_distance_to_coast(
                self.maper1[:, :2], data.lon0, data.lat0
            )

            # Get bathymetry at epicenter
            h0 = self.bathy_interpolator((data.lat0, data.lon0))

            # Determine location and warning
            location = determine_epicenter_location(h0, distance_to_coast)
            warning = determine_tsunami_warning(data.Mw, data.h, h0, distance_to_coast)

            # Write hypo.dat file
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
            )

        except Exception:
            logger.exception("Error calculating earthquake parameters")
            raise

    def calculate_tsunami_travel_times(
        self, data: EarthquakeInput
    ) -> TsunamiTravelResponse:
        """
        Calculate tsunami travel times to various ports.

        Args:
            data: EarthquakeInput object containing earthquake data

        Returns:
            TsunamiTravelResponse object with arrival times and distances
        """
        try:
            arrival_times = {}
            distances = {}
            time0 = float(data.hhmm[:2]) + float(data.hhmm[2:]) / 60

            # Read ports data
            with open(self.data_path / "puertos.txt", "r") as f:
                ports = f.readlines()

            # Calculate for each port
            for port in ports:
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

            # Prepare epicenter information
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
            mech_data = np.loadtxt(self.data_path / "mecfoc.dat")
            distances = np.sqrt(
                (mech_data[:, 0] - lon0) ** 2 + (mech_data[:, 1] - lat0) ** 2
            )
            closest_idx = np.argmin(distances)

            return mech_data[closest_idx, 2], 18.0

        except Exception:
            logger.exception("Error getting focal mechanism")
            raise

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
            t1 = np.pi / 2 - lat0 * np.pi / 180
            f1 = lon0 * np.pi / 180
            t2 = np.pi / 2 - port_lat * np.pi / 180
            f2 = port_lon * np.pi / 180

            # Calculate great circle distance
            cosen = np.sin(t1) * np.sin(t2) * np.cos(f1 - f2) + np.cos(t1) * np.cos(t2)
            alfa = np.arccos(cosen)
            distance = self.R * alfa

            # Determine travel time based on distance and location
            if distance >= 750:
                travel_time = distance / 790 + 0.2
            elif (lat0 > 0 or lat0 < -19) and distance < 750:
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
            # Calculate velocity vector
            vu = np.array([port_lon - lon0, port_lat - lat0]) / distance * 110
            n = 100
            delta = alfa * 180 / np.pi / n

            # Calculate depths along path
            P0 = np.array([lon0, lat0])
            h = [abs(self.bathy_interpolator((lat0, lon0)))]

            for i in range(n):
                P = P0 + (i + 1) * delta * vu
                h.append(abs(self.bathy_interpolator((P[1], P[0]))))

            h = np.array(h)
            v = np.sqrt(self.g * h) * 3.6

            # Simpson's rule integration
            delta = alfa / n * self.R
            y = 1 / v
            integral = (delta / 3) * (
                y[0] + y[-1] + 4 * np.sum(y[1:-1:2]) + 2 * np.sum(y[2:-1:2])
            )

            travel_time = 0.50 * integral

            # Adjust travel time based on empirical thresholds
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
                f.write(f"{data.hhmm}\n")
                f.write(f"{data.lon0:.2f}\n")
                f.write(f"{data.lat0:.2f}\n")
                f.write(f"{data.h:.0f}\n")
                f.write(f"{data.Mw:.1f}\n")

        except Exception:
            logger.exception("Error writing hypo.dat")
            raise
