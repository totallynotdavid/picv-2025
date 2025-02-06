from typing import Dict, List, Optional

from pydantic import BaseModel, field_validator


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
