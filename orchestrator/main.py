import logging
from datetime import datetime
from pathlib import Path
from typing import Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from orchestrator.core.calculator import TsunamiCalculator
from orchestrator.core.config import LOGGING_CONFIG, MODEL_DIR
from orchestrator.core.queue import JobStatus, TSDHNJob
from orchestrator.models.schemas import (
    CalculationResponse,
    EarthquakeInput,
    RunTSDHNRequest,
    TsunamiTravelResponse,
)

# Configure logging
logging.basicConfig(**LOGGING_CONFIG)
logger = logging.getLogger(__name__)

app = FastAPI(title="TSDHN API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Limit to specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
calculator = TsunamiCalculator()
tsdhn_queue = TSDHNJob()

skip_steps_default = Query(None)  # Used on /run-tsdhn endpoint to skip steps


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
            "Processing calculation request for earthquake at"
            f" ({data.lat0}, {data.lon0})"
        )
        return calculator.calculate_earthquake_parameters(data)
    except Exception as e:
        logger.exception("Error in calculate_endpoint")
        raise HTTPException(
            status_code=500, detail=f"Error calculating earthquake parameters: {str(e)}"
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
            "Calculating tsunami travel times for earthquake at"
            f" ({data.lat0}, {data.lon0})"
        )

        return calculator.calculate_tsunami_travel_times(data)
    except Exception as e:
        logger.exception("Error in tsunami_travel_times_endpoint")
        raise HTTPException(
            status_code=500, detail=f"Error calculating tsunami travel times: {str(e)}"
        ) from e


@app.post("/run-tsdhn")
async def run_tsdhn_endpoint(payload: RunTSDHNRequest):
    """
    Enqueue a TSDHN model execution job.

    The model takes approximately 12 minutes to run on a fast server.
    This endpoint returns immediately with a job ID that can be used
    to check the execution status.

    Returns:
        Dict containing:
            - status: "queued"
            - job_id: Unique identifier for the job
            - message: Status message
    """
    try:
        skip_steps = payload.skip_steps
        logger.info("Enqueueing new TSDHN job")
        if skip_steps:
            logger.info(f"Skipping steps: {skip_steps}")
            job_id = tsdhn_queue.enqueue_job(skip_steps=skip_steps)
        else:
            logger.info("No steps will be skipped.")
            job_id = tsdhn_queue.enqueue_job()
        return {
            "status": "queued",
            "job_id": job_id,
            "message": "TSDHN job has been queued successfully",
        }
    except Exception as e:
        logger.exception("Error queueing TSDHN job")
        raise HTTPException(
            status_code=500, detail=f"Error starting TSDHN job: {str(e)}"
        ) from e


@app.get("/job-status/{job_id}")
async def get_job_status_endpoint(job_id: str) -> Dict:
    """
    Get the status of a TSDHN job.

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
        logger.debug(f"Checking status for job {job_id}")
        return tsdhn_queue.get_job_status(job_id)
    except ValueError as e:
        logger.error(f"Job {job_id} not found")
        raise HTTPException(status_code=404, detail=f"Job not found: {str(e)}") from e
    except Exception as e:
        logger.exception(f"Error checking status for job {job_id}")
        raise HTTPException(
            status_code=500, detail=f"Error checking job status: {str(e)}"
        ) from e


@app.get("/job-result/{job_id}")
async def get_job_result_endpoint(job_id: str):
    """
    Get the result of a completed TSDHN job.

    Args:
        job_id (str): The job identifier returned by /run-tsdhn

    Returns:
        FileResponse: The generated PDF report
    """
    try:
        logger.info(f"Retrieving results for job {job_id}")

        # Check job status
        status = tsdhn_queue.get_job_status(job_id)
        if status["status"] != JobStatus.COMPLETED.value:
            raise HTTPException(
                status_code=400,
                detail=f"Job is not completed. Current status: {status['status']}",
            )

        # Check if report exists
        job_work_dir = Path(MODEL_DIR).parent / "jobs" / job_id
        report_path = job_work_dir / "reporte.pdf"
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="Report file not found")

        return FileResponse(
            path=str(report_path),
            filename=f"tsdhn_report_{job_id}.pdf",
            media_type="application/pdf",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving results for job {job_id}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving job results: {str(e)}"
        ) from e


@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        Dict containing service status and current timestamp
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "calculator": "initialized",
        "queue": "connected" if tsdhn_queue.redis.ping() else "disconnected",
    }


def start_app():
    """Start the FastAPI application using uvicorn."""
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    start_app()
