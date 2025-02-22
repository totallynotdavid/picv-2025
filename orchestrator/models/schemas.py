from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, field_validator


class JobStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EarthquakeInput(BaseModel):
    Mw: float
    h: float
    lat0: float
    lon0: float
    dia: Optional[str] = "00"
    hhmm: Optional[str] = "0000"

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
    rectangle_parameters: Dict[str, float]
    rectangle_corners: List[Dict[str, float]]


class TsunamiTravelResponse(BaseModel):
    arrival_times: Dict[str, str]
    distances: Dict[str, float]
    epicenter_info: Dict[str, str]


class RunTSDHNRequest(BaseModel):
    skip_steps: Optional[List[str]] = None


@dataclass(frozen=True)
class CompilerConfig:
    source: str
    output: str
    compiler: str = "gfortran"
    flags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProcessingStep:
    name: str
    command: Optional[List[str]] = None
    python_callable: Optional[Callable[[Path], None]] = None
    file_checks: List[Tuple[str, str]] = field(default_factory=list)
    compiler_config: Optional[CompilerConfig] = None
    pre_execute_checks: List[Tuple[str, str]] = field(default_factory=list)
    extra_executables: List[str] = field(default_factory=list)
    working_dir: Optional[str] = None

    def __post_init__(self):
        if not (self.command is None) ^ (self.python_callable is None):
            raise ValueError(
                "ProcessingStep must have either command or python_callable"
            )
