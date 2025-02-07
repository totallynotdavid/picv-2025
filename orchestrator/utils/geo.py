from datetime import datetime

import numpy as np

# Constants
EARTH_RADIUS = 6371.0  # in kilometers
DEG_TO_KM = (EARTH_RADIUS * np.pi) / 180.0


def calculate_distance_to_coast(
    coast_points: np.ndarray, lon0: float, lat0: float
) -> float:
    """
    Compute the distance from the epicenter (lon0, lat0) to the closest point
    on the coast. The coast_points array is assumed to have the format:
    [ [lon, lat], [lon, lat], ... ].

    The minimal angular distance (in degrees) is converted to kilometers using the
    Earth's radius.
    """
    # Compute Euclidean distance in degree space using np.hypot
    distances = np.hypot(coast_points[:, 0] - lon0, coast_points[:, 1] - lat0)
    min_deg = distances.min()
    return min_deg * DEG_TO_KM


def format_arrival_time(time: float, day: str) -> str:
    hour = int(time)
    minute = int((time - hour) * 60)
    day_increment = hour >= 24
    if day_increment:
        hour -= 24
    day = str(int(day) + day_increment).zfill(2)
    return f"{hour:02d}:{minute:02d} {day}{datetime.now().strftime('%b')}"


def determine_tsunami_warning(Mw: float, h: float, h0: float, dist_min: float) -> str:
    if h0 > 0 and dist_min < 50:
        return "El epicentro esta en Tierra, pero podría generar Tsunami"
    elif h0 > 0 and dist_min > 50:
        return "El epicentro esta en Tierra. NO genera Tsunami"
    elif h0 <= 0:
        if h > 60 or Mw < 7.0:
            return "El epicentro esta en el Mar y NO genera Tsunami"
        elif Mw >= 8.8 and h <= 60:
            return "Genera un Tsunami grande y destructivo"
        elif Mw >= 8.3995 and h <= 60:
            return "Genera un Tsunami potencialmente destructivo"
        elif Mw >= 7.9 and h <= 60:
            return "Genera un Tsunami pequeno"
        elif Mw >= 7.0 and h <= 60:
            return "Probable Tsunami pequeno y local"
    return "NO genera Tsunami"


def determine_epicenter_location(h0: float, dist_min: float) -> str:
    if h0 > 0:
        return "tierra" if dist_min > 50 else "tierra cerca de costa"
    return "mar"
