from uuid import UUID

from pydantic import BaseModel

from tsdhn.domain import CalculationResponse, EarthquakeInput, TsunamiTravelResponse

__all__ = [
    "ArtifactList",
    "ArtifactRef",
    "CalculationPreview",
    "HealthStatus",
    "JobCreated",
    "JobRequest",
    "JobStatusResponse",
    "VersionInfo",
]


class CalculationPreview(BaseModel):
    """Preview data returned before committing to a queued simulation."""

    calculation: CalculationResponse
    travel_times: TsunamiTravelResponse


class JobRequest(BaseModel):
    app_job_id: UUID
    input: EarthquakeInput


class JobCreated(BaseModel):
    app_job_id: str
    compute_job_id: str
    status: str
    result_bucket: str | None = None
    result_key: str | None = None


class JobStatusResponse(BaseModel):
    app_job_id: str
    compute_job_id: str
    status: str
    details: str | None = None
    step: str | None = None
    step_index: int | None = None
    total_steps: int | None = None
    calculation: CalculationResponse | None = None
    travel_times: TsunamiTravelResponse | None = None
    result_bucket: str | None = None
    result_key: str | None = None
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    # Names of the artifacts this job produced, empty until it completes.
    # Fetch one with GET /api/v1/jobs/{app_job_id}/artifacts/{name}.
    artifacts: list[str] = []


class ArtifactRef(BaseModel):
    name: str
    filename: str
    content_type: str


class ArtifactList(BaseModel):
    app_job_id: str
    artifacts: list[ArtifactRef]


class HealthStatus(BaseModel):
    status: str
    timestamp: str
    database_connected: bool
    storage_connected: bool


class VersionInfo(BaseModel):
    name: str
    version: str
