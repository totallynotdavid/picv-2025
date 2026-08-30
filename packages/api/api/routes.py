import json
import logging
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from functools import lru_cache, partial
from pathlib import Path
from typing import Any

import anyio
import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, StreamingResponse

from api import __version__
from api.core import repository
from api.core.db import CONNECT_TIMEOUT, notify_channel
from api.core.settings import COMPUTE_DATABASE_URL, SSE_MAX_DURATION
from api.core.storage import output_store
from api.core.tasks import enqueue_simulation
from api.schemas import (
    CalculationPreview,
    HealthStatus,
    JobCreated,
    JobRequest,
    JobStatusResponse,
    OutputList,
    StoredOutput,
    VersionInfo,
)
from api.security import require_compute_api_token
from tsdhn.calculator import TsunamiCalculator
from tsdhn.domain import EarthquakeInput, JobStatus

logger = logging.getLogger(__name__)

_TERMINAL = {JobStatus.COMPLETED.value, JobStatus.FAILED.value}

# Proxies may close an idle SSE connection without a keepalive.
_KEEPALIVE_SECONDS = 20.0


@lru_cache(maxsize=1)
def get_calculator() -> TsunamiCalculator:
    """Process-wide calculator. Model data loads once."""
    return TsunamiCalculator()


ops_router = APIRouter(prefix="/api/v1", tags=["ops"])
router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_compute_api_token)],
    tags=["jobs"],
)


@ops_router.get("/health", response_model=HealthStatus)
async def health() -> HealthStatus:
    database_connected = await anyio.to_thread.run_sync(
        repository.is_database_connected
    )
    storage_connected = await anyio.to_thread.run_sync(output_store.is_connected)
    return HealthStatus(
        status="healthy" if database_connected and storage_connected else "degraded",
        timestamp=datetime.now(UTC).isoformat(),
        database_connected=database_connected,
        storage_connected=storage_connected,
    )


@ops_router.get("/version", response_model=VersionInfo)
async def version() -> VersionInfo:
    return VersionInfo(name="tsdhn-api", version=__version__)


@router.post("/calculations", response_model=CalculationPreview)
async def create_calculation(data: EarthquakeInput) -> CalculationPreview:
    calculator = get_calculator()

    def compute() -> CalculationPreview:
        # The preview writes hypo.dat, but previews must not mutate the workspace.
        with tempfile.TemporaryDirectory() as tmp:
            calculation = calculator.calculate_earthquake_parameters(data, Path(tmp))
        travel_times = calculator.calculate_tsunami_travel_times(data)
        return CalculationPreview(calculation=calculation, travel_times=travel_times)

    return await anyio.to_thread.run_sync(compute)


@router.post(
    "/jobs",
    response_model=JobCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(req: JobRequest) -> JobCreated:
    simulation_id = str(req.simulation_id)
    try:
        job_status = await anyio.to_thread.run_sync(
            partial(
                repository.create_or_get_job,
                data=req.input,
                simulation_id=simulation_id,
                defer=enqueue_simulation,
            )
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except Exception as e:
        logger.exception("Job queuing failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start simulation pipeline",
        ) from e

    return JobCreated(
        simulation_id=simulation_id,
        status=job_status["status"],
    )


@router.get("/jobs/{simulation_id}", response_model=JobStatusResponse)
async def get_job(simulation_id: str) -> JobStatusResponse:
    job_status = await _job_status(simulation_id)
    return JobStatusResponse(simulation_id=simulation_id, **job_status)


@router.get("/jobs/{simulation_id}/outputs", response_model=OutputList)
async def list_outputs(simulation_id: str) -> OutputList:
    try:
        outputs = await anyio.to_thread.run_sync(repository.get_outputs, simulation_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return OutputList(
        simulation_id=simulation_id,
        outputs=[
            StoredOutput(
                name=output["name"],
                filename=output["filename"],
                content_type=output["content_type"],
            )
            for output in outputs
        ],
    )


@router.get(
    "/jobs/{simulation_id}/outputs/{name}",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
)
async def get_output(simulation_id: str, name: str) -> RedirectResponse:
    try:
        outputs = await anyio.to_thread.run_sync(repository.get_outputs, simulation_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    match = next((output for output in outputs if output["name"] == name), None)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No output '{name}' for this job",
        )

    url = await anyio.to_thread.run_sync(
        partial(output_store.presigned_url, match["key"], filename=match["filename"])
    )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/jobs/{simulation_id}/events")
async def job_events(simulation_id: str) -> StreamingResponse:
    """Stream job state changes from the job's Postgres notification channel."""
    try:
        simulation_uuid = repository.as_uuid(simulation_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or unknown job ID",
        ) from e
    channel = notify_channel(simulation_uuid)

    async def stream() -> AsyncIterator[str]:
        try:
            job_status = await _job_status(simulation_id)
        except HTTPException:
            yield _sse_error("unknown job")
            return

        yield _sse_data(simulation_id, job_status)
        if job_status["status"] in _TERMINAL:
            return

        deadline = anyio.current_time() + SSE_MAX_DURATION
        aconn = await psycopg.AsyncConnection.connect(
            COMPUTE_DATABASE_URL, autocommit=True, connect_timeout=CONNECT_TIMEOUT
        )
        try:
            await aconn.execute(f"LISTEN {channel}")
            last = job_status
            while anyio.current_time() < deadline:
                notified = False
                async for _ in aconn.notifies(timeout=_KEEPALIVE_SECONDS, stop_after=1):
                    notified = True

                # Read on every tick to cover notifications that race the wait.
                job_status = await _job_status(simulation_id)
                if job_status != last:
                    last = job_status
                    yield _sse_data(simulation_id, job_status)
                    if job_status["status"] in _TERMINAL:
                        return
                elif not notified:
                    yield ": keepalive\n\n"
        finally:
            await aconn.close()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


async def _job_status(simulation_id: str) -> dict[str, Any]:
    try:
        return await anyio.to_thread.run_sync(repository.get_job_status, simulation_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


def _sse_data(simulation_id: str, job_status: dict[str, Any]) -> str:
    return f"data: {json.dumps({'simulation_id': simulation_id, **job_status})}\n\n"


def _sse_error(message: str) -> str:
    return f"event: error\ndata: {json.dumps({'error': message})}\n\n"
