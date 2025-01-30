from pathlib import Path

# Constants
GRAVITY = 9.81  # acceleration due to gravity (m/s²)
EARTH_RADIUS = 6370.8  # Earth radius (km)
MODEL_DIR = Path("model")

# Logging configuration
LOGGING_CONFIG = {
    "filename": "tsunami_api.log",
    "level": "DEBUG",
    "format": "%(asctime)s - %(levelname)s - %(message)s",
}
