from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Tuple, List

@dataclass
class Config:
    """Application configuration."""

    EARTH_RADIUS: float = 6371.0
    SHEAR_MODULUS: float = 4.5e10
    MOMENT_CONSTANT: float = 1e21
    KM2DEG: float = 1 / 110
    DIP_ANGLE: float = 18.0

    MODEL_PATH: Path = Path("/home/fenlab/web/picv-2025/model")
    INPUT_FILE: Path = Path("/home/fenlab/web/picv-2025/model/falla.inp")
    STATIC_DIR: Path = field(default_factory=lambda: Path(__file__).parent / "static")

    PARAM_RANGES: Dict[str, Tuple[float, float]] = field(
        default_factory=lambda: {
            "Mw": (5.0, 9.5),
            "h": (0, 700),
            "lat0": (-90, 90),
            "lon0": (-180, 180),
        }
    )

    LOCATIONS: List[Tuple[float, float, str]] = field(
        default_factory=lambda: [
            (-79.48, 8.99, "Panama"),
            (-80.5876, -3.6337, "La Cruz"),
            (-81.30, -5.082, "Paita"),
            (-79.9423, -6.8396, "Pimentel"),
            (-78.6100, -9.0733, "Chimbote"),
            (-77.615, -11.123, "Huacho"),
            (-77.031, -12.046, "Lima"),
            (-76.22, -13.71, "Pisco"),
            (-75.1567, -15.3433, "San Juan"),
            (-73.61, -16.23, "Atico"),
            (-72.6838, -16.6604, "Camana"),
            (-72.1067, -16.9983, "Matarani"),
            (-70.3232, -18.4758, "Arica"),
        ]
    )
