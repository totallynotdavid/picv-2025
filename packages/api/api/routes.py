"""
Two routers: `ops_router` is unauthenticated (health/version, for liveness
probes); `router` carries the service-token dependency on every data route.
"""

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
from api.core.storage import artifact_store
from api.core.tasks import enqueue_simulation
from api.schemas import (
    ArtifactList,
    ArtifactRef,
    CalculationPreview,
    HealthStatus,
    JobCreated,
    JobRequest,
    JobStatusResponse,
    VersionInfo,
)
from api.security import require_service_token
from tsdhn.calculator import TsunamiCalculator
from tsdhn.domain import EarthquakeInput, JobStatus

logger = logging.getLogger(__name__)

_TERMINAL = {JobStatus.COMPLETED.value, JobStatus.FAILED.value}

# Sent when nothing has happened for a while, so idle proxies do not drop
# an otherwise-healthy stream. A comment frame; EventSource ignores it.
_KEEPALIVE_SECONDS = 20.0


@lru_cache(maxsize=1)
def get_calculator() -> TsunamiCalculator:
    """Process-wide calculator. Model data loads once."""
    return TsunamiCalculator()


ops_router = APIRouter(prefix="/api/v1", tags=["ops"])
router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_service_token)],
    tags=["jobs"],
)


@ops_router.get("/health", response_model=HealthStatus)
async def health() -> HealthStatus:
    database_connected = await anyio.to_thread.run_sync(
        repository.is_database_connected
    )
    storage_connected = await anyio.to_thread.run_sync(artifact_store.is_connected)
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
    app_job_id = str(req.app_job_id)
    try:
        job_status = await anyio.to_thread.run_sync(
            partial(
                repository.create_or_get_job,
                data=req.input,
                external_id=app_job_id,
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
        app_job_id=app_job_id,
        compute_job_id=job_status["compute_job_id"],
        status=job_status["status"],
        result_bucket=job_status["result_bucket"],
        result_key=job_status["result_key"],
    )


@router.get("/jobs/{app_job_id}", response_model=JobStatusResponse)
async def get_job(app_job_id: str) -> JobStatusResponse:
    job_status = await _job_status(app_job_id)
    return JobStatusResponse(app_job_id=app_job_id, **job_status)


@router.get("/jobs/{app_job_id}/artifacts", response_model=ArtifactList)
async def list_artifacts(app_job_id: str) -> ArtifactList:
    try:
        artifacts = await anyio.to_thread.run_sync(repository.get_artifacts, app_job_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return ArtifactList(
        app_job_id=app_job_id,
        artifacts=[
            ArtifactRef(
                name=a["name"],
                filename=a["filename"],
                content_type=a["content_type"],
            )
            for a in artifacts
        ],
    )


@router.get(
    "/jobs/{app_job_id}/artifacts/{name}",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
)
async def get_artifact(app_job_id: str, name: str) -> RedirectResponse:
    """Redirect to a short-lived presigned URL for one artifact.

    Bytes go straight from MinIO to the browser. Neither this service nor
    the control plane proxies a report PDF, so a large download costs one
    redirect instead of an open connection on two hops.
    """
    try:
        artifacts = await anyio.to_thread.run_sync(repository.get_artifacts, app_job_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    match = next((a for a in artifacts if a["name"] == name), None)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No artifact '{name}' for this job",
        )

    url = await anyio.to_thread.run_sync(
        partial(artifact_store.presigned_url, match["key"], filename=match["filename"])
    )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/jobs/{app_job_id}/events")
async def job_events(app_job_id: str) -> StreamingResponse:
    """Server-sent progress, pushed via LISTEN/NOTIFY.

    Every write to compute.jobs issues a NOTIFY on the job's own channel
    (see repository._notify), so this holds one connection and sleeps until
    something actually changes -- rather than reconnecting to Postgres
    every couple of seconds to ask whether it has.
    """
    external_id = repository.as_uuid(app_job_id)
    channel = notify_channel(external_id)

    async def stream() -> AsyncIterator[str]:
        try:
            job_status = await _job_status(app_job_id)
        except HTTPException:
            yield _sse_error("unknown job")
            return

        yield _sse_data(app_job_id, job_status)
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

                # Re-read on the keepalive tick too, not only on a
                # notification. A notification that lands between two
                # `notifies()` windows would otherwise strand the stream on
                # stale state; this way the worst case degrades to a slow
                # poll instead of a hang, and the tick doubles as the
                # comment frame that keeps idle proxies from dropping us.
                job_status = await _job_status(app_job_id)
                if job_status != last:
                    last = job_status
                    yield _sse_data(app_job_id, job_status)
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


async def _job_status(app_job_id: str) -> dict[str, Any]:
    try:
        return await anyio.to_thread.run_sync(repository.get_job_status, app_job_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


def _sse_data(app_job_id: str, job_status: dict[str, Any]) -> str:
    return f"data: {json.dumps({'app_job_id': app_job_id, **job_status})}\n\n"


def _sse_error(message: str) -> str:
    return f"event: error\ndata: {json.dumps({'error': message})}\n\n"
