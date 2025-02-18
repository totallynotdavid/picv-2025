import logging
from datetime import datetime
from typing import Dict

import anyio
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from orchestrator.core.calculator import TsunamiCalculator
from orchestrator.core.config import LOGGING_CONFIG
from orchestrator.core.queue import JobStatus, tsdhn_queue
from orchestrator.models.schemas import (
    CalculationResponse,
    EarthquakeInput,
    RunTSDHNRequest,
    TsunamiTravelResponse,
)
from orchestrator.utils.job_validators import secure_path_construction, validate_job_id

# Configure logging
logging.basicConfig(**LOGGING_CONFIG)
logger = logging.getLogger(__name__)

app = FastAPI(title="TSDHN API", version="0.1.0", docs_url="/api-docs", redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Limit to specific domains
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Initialize services
calculator = TsunamiCalculator()


@app.post("/calculate", response_model=CalculationResponse)
async def calculate_endpoint(data: EarthquakeInput):
    """
    Calculate earthquake parameters and assess tsunami risk.

    Args:
        data (EarthquakeInput): Input data containing:
            - Mw (float): Earthquake magnitude
            - h (float): Depth
            - lat0 (float): Latitude
            - lon0 (float): Longitude
            - dia (str, optional): Day
            - hhmm (str, optional): Time

    Returns:
        CalculationResponse: Calculated parameters including:
            - Rupture dimensions
            - Tsunami warning
            - Location classification
            - Rectangle parameters and corners
    """
    try:
        logger.info(
            "Processing calculation request for earthquake",
            extra={"lat": data.lat0, "lon": data.lon0},
        )
        return await anyio.to_thread.run_sync(
            calculator.calculate_earthquake_parameters, data
        )
    except Exception as e:
        logger.exception("Error in calculate_endpoint")
        raise HTTPException(
            status_code=500, detail="Error processing calculation"
        ) from e


@app.post("/tsunami-travel-times", response_model=TsunamiTravelResponse)
async def tsunami_travel_times_endpoint(data: EarthquakeInput):
    """
    Calculate tsunami travel times to coastal locations.

    Args:
        data (EarthquakeInput): Same input parameters as /calculate endpoint

    Returns:
        TsunamiTravelResponse: Estimated arrival times and distances for monitored ports
    """
    try:
        logger.info(
            "Calculating tsunami travel times",
            extra={"lat": data.lat0, "lon": data.lon0},
        )
        return await anyio.to_thread.run_sync(
            calculator.calculate_tsunami_travel_times, data
        )
    except Exception as e:
        logger.exception("Error in tsunami_travel_times_endpoint")
        raise HTTPException(
            status_code=500, detail="Error calculating travel times"
        ) from e


@app.post("/run-tsdhn")
async def run_tsdhn_endpoint(payload: RunTSDHNRequest):
    """
    Enqueue a TSDHN model execution job.

    The TSDHN model takes approximately 25 minutes to run on a fast server.
    Returns a job ID that can be used to check the execution
    status later on or retrieve the results.

    Returns:
        Dict containing:
            - status: "queued"
            - job_id: Unique identifier for the job
            - message: Status message
    """
    try:
        logger.info("Enqueueing new TSDHN job")
        job_id = tsdhn_queue.enqueue_job(skip_steps=payload.skip_steps)
        return {
            "status": "queued",
            "job_id": job_id,
            "message": "Job queued successfully",
        }
    except Exception as e:
        logger.exception("Job queuing failed")
        raise HTTPException(
            status_code=500, detail="Error starting processing job"
        ) from e


@app.get("/job-status/{job_id}")
async def get_job_status_endpoint(job_id: str) -> Dict:
    """
    Args:
        job_id (str): The job identifier returned by /run-tsdhn

    Returns:
        Dict containing:
            - status: Current job status (queued/running/completed/failed)
            - error: Error message if failed
            - created_at: Job creation timestamp
            - ended_at: Job completion timestamp (if completed)
    """
    try:
        logger.debug("Retrieving job status", extra={"job_id": job_id})
        return tsdhn_queue.get_job_status(job_id)
    except Exception as e:
        logger.exception(f"Error checking status for job {job_id}")
        raise HTTPException(
            status_code=500, detail="Error retrieving job status"
        ) from e


@app.get("/job-result/{job_id}")
async def get_job_result_endpoint(job_id: str):
    """
    Args:
        job_id (str): The job identifier returned by /run-tsdhn

    Returns:
        FileResponse: The generated PDF report
    """
    validate_job_id(job_id)

    try:
        status = tsdhn_queue.get_job_status(job_id)
        if status["status"] != JobStatus.COMPLETED.value:
            raise HTTPException(status_code=400, detail="Job processing not complete")

        job_dir = secure_path_construction(job_id)
        report_path = job_dir / "reporte.pdf"

        if not await anyio.to_thread.run_sync(report_path.exists):
            raise HTTPException(status_code=404, detail="Report not available")

        return FileResponse(
            path=report_path,
            filename=f"tsdhn_report_{job_id}.pdf",
            media_type="application/pdf",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Result retrieval error")
        raise HTTPException(
            status_code=500, detail="Error retrieving job results"
        ) from e


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "calculator": "initialized",
        "queue_status": "connected" if tsdhn_queue.redis.ping() else "disconnected",
    }


def start_app():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    start_app()
