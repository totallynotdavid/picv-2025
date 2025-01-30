import logging
import os
import subprocess
from datetime import datetime

from core.calculator import TsunamiCalculator
from core.config import LOGGING_CONFIG, MODEL_DIR
from models.schemas import (
    CalculationResponse,
    EarthquakeInput,
    TsunamiTravelResponse,
)
from fastapi import FastAPI, HTTPException

# Configure logging
logging.basicConfig(**LOGGING_CONFIG)
logger = logging.getLogger(__name__)

app = FastAPI(title="TSDHN API", version="0.1.0")

# Initialize calculator
calculator = TsunamiCalculator()


@app.post("/calculate", response_model=CalculationResponse)
async def calculate_endpoint(data: EarthquakeInput):
    """
    Calculate earthquake parameters and assess tsunami risk.

    Required: Mw (magnitude), h (depth), lat0 (latitude), lon0 (longitude)
    Optional: dia (day), hhmm (time)

    Returns earthquake parameters including rupture dimensions, tsunami warning,
    and location classification.
    """
    try:
        return calculator.calculate_earthquake_parameters(data)
    except Exception as e:
        logger.exception("Error in calculate_endpoint: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/tsunami-travel-times", response_model=TsunamiTravelResponse)
async def tsunami_travel_times_endpoint(data: EarthquakeInput):
    """
    Calculate tsunami travel times to coastal locations.

    Uses same input parameters as /calculate.
    Returns estimated arrival times and distances for monitored ports,
    along with epicenter information.
    """
    try:
        return calculator.calculate_tsunami_travel_times(data)
    except Exception as e:
        logger.exception("Error in tsunami_travel_times_endpoint: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/run-tsdhn")
async def run_tsdhn():
    """
    Execute TSDHN model with parameters from hypo.dat.

    Requires prior execution of /calculate endpoint to generate hypo.dat.
    Returns execution status and model output.
    """
    try:
        job_run_path = MODEL_DIR / "job.run"
        os.chmod(job_run_path, 0o775)
        result = subprocess.run(
            ["./job.run"],
            cwd=MODEL_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("TSDHN executed successfully: %s", result.stdout)
        return {
            "status": "success",
            "message": "TSDHN execution completed successfully",
            "output": result.stdout,
        }
    except Exception as e:
        logger.exception("Error executing TSDHN: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/health")
async def health_check():
    """
    Returns service status and current timestamp.
    """
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
