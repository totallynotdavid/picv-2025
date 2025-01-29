import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from scipy.interpolate import RegularGridInterpolator
from scipy.io import loadmat

# Configure logging
logging.basicConfig(
    filename="tsunami_api.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Tsunami Analysis API")


class EarthquakeInput(BaseModel):
    Mw: float  # Magnitude
    h: float  # Depth
    lat0: float  # Latitude
    lon0: float  # Longitude
    dia: Optional[str] = "00"  # Day
    hhmm: Optional[str] = "0000"  # Time

    @field_validator("lon0")
    def convert_longitude(cls, v):
        return v - 360 if v > 0 else v

    @field_validator("hhmm")
    def validate_time(cls, v):
        if len(v) == 0 or len(v) < 4:
            return "0000"
        if ":" in v:
            return v.replace(":", "")
        return v


class CalculationResponse(BaseModel):
    length: float
    width: float
    dislocation: float
    seismic_moment: float
    tsunami_warning: str
    distance_to_coast: float
    azimuth: float
    dip: float
    epicenter_location: str


class TsunamiTravelResponse(BaseModel):
    arrival_times: Dict[str, str]
    distances: Dict[str, float]
    epicenter_info: Dict[str, str]


class TsunamiCalculator:
    def __init__(self):
        self.data_path = Path("model")
        self.g = 9.81  # acceleration due to gravity (m/s²)
        self.R = 6370.8  # Earth radius (km)
        self._load_data()

    def _load_data(self):
        try:
            pacifico_path = self.data_path / "pacifico.mat"
            pacifico = loadmat(pacifico_path)

            self.xa = pacifico["xa"].flatten()
            self.ya = pacifico["ya"].flatten()
            self.bathymetry = pacifico["A"]

            logger.debug("xa: %s", self.xa)
            logger.debug("ya: %s", self.ya)
            logger.debug("bathymetry shape: %s", self.bathymetry.shape)

            self.vlon = self.xa - 360
            self.vlat = self.ya

            logger.debug("vlon: %s", self.vlon)
            logger.debug("vlat: %s", self.vlat)

            if self.vlat[0] > self.vlat[-1]:
                self.vlat = self.vlat[::-1]
                self.bathymetry = self.bathymetry[::-1, :]

            self.bathy_interpolator = RegularGridInterpolator(
                (self.vlat, self.vlon),
                self.bathymetry,
                bounds_error=False,
                fill_value=None,
            )

            maper1_path = self.data_path / "maper1.mat"
            maper1 = loadmat(maper1_path)
            self.maper1 = maper1["A"]

            logger.debug("Data loaded successfully.")

        except FileNotFoundError as fnf_error:
            logger.exception(f"Error loading data files: {fnf_error}")
            raise
        except KeyError as key_error:
            logger.exception(f"Error: Missing key in .mat file: {key_error}")
            raise
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise

    def calculate_earthquake_parameters(
        self, data: EarthquakeInput
    ) -> CalculationResponse:
        L = 10 ** (0.55 * data.Mw - 2.19)
        W = 10 ** (0.31 * data.Mw - 0.63)
        M0 = 10 ** (1.5 * data.Mw + 9.1)
        u = 4.5e10
        D = M0 / (u * (L * 1000) * (W * 1000))

        logger.debug("L: %s", L)
        logger.debug("W: %s", W)
        logger.debug("M0: %s", M0)
        logger.debug("D: %s", D)

        azimuth, dip = self._get_focal_mechanism(data.lon0, data.lat0)
        distance_to_coast = self._calculate_distance_to_coast(data.lon0, data.lat0)

        logger.debug("azimuth: %s", azimuth)
        logger.debug("dip: %s", dip)
        logger.debug("distance_to_coast: %s", distance_to_coast)

        h0 = self.bathy_interpolator((data.lat0, data.lon0))
        location = self._determine_epicenter_location(h0, distance_to_coast)
        warning = self._determine_tsunami_warning(
            data.Mw, data.h, h0, distance_to_coast
        )

        logger.debug("h0: %s", h0)
        logger.debug("location: %s", location)
        logger.debug("warning: %s", warning)

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

    def _get_focal_mechanism(self, lon0: float, lat0: float) -> Tuple[float, float]:
        mech_data = np.loadtxt(self.data_path / "mecfoc.dat")
        distances = np.sqrt(
            (mech_data[:, 0] - lon0) ** 2 + (mech_data[:, 1] - lat0) ** 2
        )
        closest_idx = np.argmin(distances)

        logger.debug("mech_data: %s", mech_data)
        logger.debug("distances: %s", distances)
        logger.debug("closest_idx: %s", closest_idx)

        return mech_data[closest_idx, 2], 18.0

    def _calculate_distance_to_coast(self, lon0: float, lat0: float) -> float:
        coast_points = self.maper1[:, :2]
        distances = np.sqrt(
            (coast_points[:, 0] - lon0) ** 2 + (coast_points[:, 1] - lat0) ** 2
        )
        min_distance = np.min(distances) * 111.12

        logger.debug("coast_points: %s", coast_points)
        logger.debug("distances: %s", distances)
        logger.debug("min_distance: %s", min_distance)

        return min_distance

    def calculate_tsunami_travel_times(
        self, data: EarthquakeInput
    ) -> TsunamiTravelResponse:
        arrival_times = {}
        distances = {}
        time0 = float(data.hhmm[:2]) + float(data.hhmm[2:]) / 60

        logger.debug("time0: %s", time0)

        with open(self.data_path / "puertos.txt", "r") as f:
            ports = f.readlines()

        logger.debug("ports: %s", ports)

        for port in ports:
            if len(port) < 15:
                continue

            parts = port.split()
            if len(parts) < 3:
                logger.error(f"Insufficient data in line: '{port.strip()}'")
                continue

            try:
                port_name = port[:15].strip()
                port_lon = float(parts[0])
                port_lat = float(parts[1])

                distance, travel_time = self._calculate_travel_time(
                    data.lon0, data.lat0, port_lon, port_lat, time0
                )

                arrival_times[port_name] = self._format_arrival_time(
                    travel_time, data.dia
                )
                distances[port_name] = distance

                logger.debug(
                    "port_name: %s, port_lat: %s, port_lon: %s",
                    port_name,
                    port_lat,
                    port_lon,
                )
                logger.debug("distance: %s, travel_time: %s", distance, travel_time)

            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing line '{port.strip()}': {e}")
                continue

        epicenter_info = {
            "date": data.dia,
            "time": data.hhmm,
            "latitude": f"{data.lat0:.2f}",
            "longitude": f"{data.lon0:.2f}",
            "depth": f"{data.h:.0f}",
            "magnitude": f"{data.Mw:.1f}",
        }

        logger.debug("epicenter_info: %s", epicenter_info)

        return TsunamiTravelResponse(
            arrival_times=arrival_times,
            distances=distances,
            epicenter_info=epicenter_info,
        )

    def _calculate_travel_time(
        self, lon0: float, lat0: float, port_lon: float, port_lat: float, time0: float
    ) -> Tuple[float, float]:
        t1 = np.pi / 2 - lat0 * np.pi / 180
        f1 = lon0 * np.pi / 180
        t2 = np.pi / 2 - port_lat * np.pi / 180
        f2 = port_lon * np.pi / 180

        logger.debug("t1: %s", t1)
        logger.debug("f1: %s", f1)
        logger.debug("t2: %s", t2)
        logger.debug("f2: %s", f2)

        cosen = np.sin(t1) * np.sin(t2) * np.cos(f1 - f2) + np.cos(t1) * np.cos(t2)
        alfa = np.arccos(cosen)
        distance = self.R * alfa

        logger.debug("cosen: %s", cosen)
        logger.debug("alfa: %s", alfa)
        logger.debug("distance: %s", distance)

        if distance >= 750:
            travel_time = distance / 790 + 0.2
        elif (lat0 > 0 or lat0 < -19) and distance < 750:
            travel_time = distance / 700
        else:
            travel_time = self._calculate_detailed_travel_time(
                lon0, lat0, port_lon, port_lat, distance, alfa
            )

        logger.debug("travel_time: %s", travel_time)

        return distance, travel_time + time0

    def _calculate_detailed_travel_time(
        self,
        lon0: float,
        lat0: float,
        port_lon: float,
        port_lat: float,
        distance: float,
        alfa: float,
    ) -> float:
        vu = np.array([port_lon - lon0, port_lat - lat0]) / distance * 110
        n = 100
        delta = alfa * 180 / np.pi / n

        P0 = np.array([lon0, lat0])
        h = [abs(self.bathy_interpolator((lat0, lon0)))]

        for i in range(n):
            P = P0 + (i + 1) * delta * vu
            h.append(abs(self.bathy_interpolator((P[1], P[0]))))

        h = np.array(h)
        v = np.sqrt(self.g * h) * 3.6

        delta = alfa / n * self.R
        y = 1 / v
        integral = (delta / 3) * (
            y[0] + y[-1] + 4 * np.sum(y[1:-1:2]) + 2 * np.sum(y[2:-1:2])
        )

        travel_time = 0.50 * integral

        if travel_time > 3.0:
            travel_time = distance / 733 + 0.25
        elif 1.4 < travel_time < 3.0:
            travel_time = distance / 690 + 0.2

        logger.debug("vu: %s", vu)
        logger.debug("n: %s", n)
        logger.debug("delta: %s", delta)
        logger.debug("P0: %s", P0)
        logger.debug("h: %s", h)
        logger.debug("v: %s", v)
        logger.debug("integral: %s", integral)
        logger.debug("travel_time: %s", travel_time)

        return travel_time

    def _determine_tsunami_warning(
        self, Mw: float, h: float, h0: float, dist_min: float
    ) -> str:
        if h0 > 0 and dist_min < 50:
            return "El epicentro esta en Tierra, pero podría generar Tsunami"
        elif h0 > 0 and dist_min > 50:
            return "El epicentro esta en Tierra. NO genera Tsunami"
        elif h0 <= 0:
            if h > 60 or Mw < 7.0:
                return "El epicentro esta en el Mar y NO genera Tsunami"
            elif Mw >= 8.8 and h <= 60:
                return "Genera un Tsunami grande y destructivo"
            elif Mw >= 8.3995 and h <= 60:
                return "Genera un Tsunami potencialmente destructivo"
            elif Mw >= 7.9 and h <= 60:
                return "Genera un Tsunami pequeno"
            elif Mw >= 7.0 and h <= 60:
                return "Probable Tsunami pequeno y local"
        return "NO genera Tsunami"

    def _determine_epicenter_location(self, h0: float, dist_min: float) -> str:
        if h0 > 0:
            return "tierra" if dist_min > 50 else "tierra cerca de costa"
        return "mar"

    def _format_arrival_time(self, time: float, day: str) -> str:
        hour = int(time)
        minute = int((time - hour) * 60)

        day_increment = hour >= 24
        if day_increment:
            hour -= 24

        day = str(int(day) + day_increment).zfill(2)
        return f"{hour:02d}:{minute:02d} {day}{datetime.now().strftime('%b')}"

    def _write_hypo_dat(self, data: EarthquakeInput):
        with open("hypo.dat", "w") as f:
            f.write(f"{data.hhmm}\n")
            f.write(f"{data.lon0:.2f}\n")
            f.write(f"{data.lat0:.2f}\n")
            f.write(f"{data.h:.0f}\n")
            f.write(f"{data.Mw:.1f}\n")


# Initialize calculator
calculator = TsunamiCalculator()


@app.post("/calculate", response_model=CalculationResponse)
async def calculate_endpoint(data: EarthquakeInput):
    """Endpoint for initial earthquake calculations"""
    try:
        return calculator.calculate_earthquake_parameters(data)
    except Exception as e:
        logger.exception("Error in calculate_endpoint: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/tsunami-travel-times", response_model=TsunamiTravelResponse)
async def tsunami_travel_times_endpoint(data: EarthquakeInput):
    """Endpoint for calculating tsunami travel times"""
    try:
        return calculator.calculate_tsunami_travel_times(data)
    except Exception as e:
        logger.exception("Error in tsunami_travel_times_endpoint: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/run-tsdhn")
async def run_tsdhn():
    """Endpoint to execute the job.run file"""
    try:
        os.chmod("model/job.run", 0o775)
        result = subprocess.run(
            ["model/job.run"], capture_output=True, text=True, check=True
        )
        logger.info("TSDHN executed successfully: %s", result.stdout)
        return {
            "status": "success",
            "message": "TSDHN execution completed successfully",
            "output": result.stdout,
        }
    except subprocess.CalledProcessError as e:
        logger.exception("TSDHN execution failed: %s", e.stderr)
        raise HTTPException(
            status_code=500, detail=f"TSDHN execution failed: {e.stderr}"
        ) from e
    except Exception as e:
        logger.exception("Error executing TSDHN: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Error executing TSDHN: {str(e)}"
        ) from e


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
