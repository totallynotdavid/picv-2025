import math
from datetime import datetime
from typing import Any

import numpy as np

from tsdhn.constants import MEAN_EARTH_RADIUS_KM

DEG_TO_KM = (MEAN_EARTH_RADIUS_KM * math.pi) / 180.0


def calculate_distance_to_coast(
    coast_points: np.ndarray, lon0: float, lat0: float
) -> float:
    distances = np.hypot(coast_points[:, 0] - lon0, coast_points[:, 1] - lat0)
    min_deg: np.floating[Any] = distances.min()
    return float(min_deg) * DEG_TO_KM


def format_arrival_time(time: float, day: str) -> str:
    hour = int(time)
    minute = int((time - hour) * 60)
    day_increment = hour >= 24
    if day_increment:
        hour -= 24
    day = str(int(day) + day_increment).zfill(2)
    return f"{hour:02d}:{minute:02d} {day}{datetime.now().strftime('%b')}"


LAND_NEAR_COAST_WARNING = "El epicentro esta en Tierra, pero podría generar Tsunami"
LAND_NO_TSUNAMI_WARNING = "El epicentro esta en Tierra. NO genera Tsunami"
SEA_NO_TSUNAMI_WARNING = "El epicentro esta en el Mar y NO genera Tsunami"
NO_TSUNAMI_WARNING = "NO genera Tsunami"

SEA_TSUNAMI_TIERS: tuple[tuple[float, str], ...] = (
    (8.8, "Genera un Tsunami grande y destructivo"),
    (8.3995, "Genera un Tsunami potencialmente destructivo"),
    (7.9, "Genera un Tsunami pequeno"),
    (7.0, "Probable Tsunami pequeno y local"),
)


def determine_tsunami_warning(Mw: float, h: float, h0: float, dist_min: float) -> str:
    if h0 > 0:
        if dist_min < 50:
            return LAND_NEAR_COAST_WARNING
        return LAND_NO_TSUNAMI_WARNING
    if h > 60 or Mw < 7.0:
        return SEA_NO_TSUNAMI_WARNING
    for threshold, message in SEA_TSUNAMI_TIERS:
        if Mw >= threshold:
            return message
    return NO_TSUNAMI_WARNING


def determine_epicenter_location(h0: float, dist_min: float) -> str:
    if h0 > 0:
        return "tierra" if dist_min > 50 else "tierra cerca de costa"
    return "mar"
