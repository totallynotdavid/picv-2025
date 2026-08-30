from uuid import UUID

from pydantic import BaseModel

from tsdhn.domain import CalculationResponse, EarthquakeInput, TsunamiTravelResponse

__all__ = [
    "CalculationPreview",
    "HealthStatus",
    "JobCreated",
    "JobRequest",
    "JobStatusResponse",
    "OutputList",
    "StoredOutput",
    "VersionInfo",
]


class CalculationPreview(BaseModel):
    """Preview data returned before committing to a queued simulation."""

    calculation: CalculationResponse
    travel_times: TsunamiTravelResponse


class JobRequest(BaseModel):
    simulation_id: UUID
    input: EarthquakeInput


class JobCreated(BaseModel):
    simulation_id: str
    status: str


class JobStatusResponse(BaseModel):
    simulation_id: str
    status: str
    details: str | None = None
    step: str | None = None
    step_index: int | None = None
    total_steps: int | None = None
    calculation: CalculationResponse | None = None
    travel_times: TsunamiTravelResponse | None = None
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    # Output names are public. Storage keys remain inside the compute service.
    outputs: list[str] = []


class StoredOutput(BaseModel):
    name: str
    filename: str
    content_type: str


class OutputList(BaseModel):
    simulation_id: str
    outputs: list[StoredOutput]


class HealthStatus(BaseModel):
    status: str
    timestamp: str
    database_connected: bool
    storage_connected: bool


class VersionInfo(BaseModel):
    name: str
    version: str
