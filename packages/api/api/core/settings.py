import os
from pathlib import Path

__all__ = [
    "APP_DB_PASSWORD",
    "APP_DB_ROLE",
    "COMPUTE_DATABASE_URL",
    "DB_POOL_MAX_SIZE",
    "DB_POOL_MIN_SIZE",
    "JOBS_DIR",
    "LOG_LEVEL",
    "MINIO_ACCESS_KEY",
    "MINIO_BUCKET",
    "MINIO_ENDPOINT",
    "MINIO_PUBLIC_ENDPOINT",
    "MINIO_SECRET_KEY",
    "MINIO_SECURE",
    "NUMBA_THREADS",
    "OUTPUT_URL_TTL",
    "PROCRASTINATE_QUEUE",
    "PROCRASTINATE_SCHEMA",
    "PROCRASTINATE_SEARCH_PATH",
    "SSE_MAX_DURATION",
]

COMPUTE_DATABASE_URL = os.environ.get(
    "COMPUTE_DATABASE_URL",
    "postgresql://tsdhn:tsdhn@localhost:5432/tsdhn",
)

PROCRASTINATE_QUEUE = os.environ.get("PROCRASTINATE_QUEUE", "simulations")
PROCRASTINATE_SCHEMA = "compute"
PROCRASTINATE_SEARCH_PATH = f"{PROCRASTINATE_SCHEMA},public"

JOBS_DIR: Path = Path(os.environ.get("TSDHN_JOBS_DIR", "jobs")).resolve()

LOG_LEVEL = os.environ.get("TSDHN_LOG_LEVEL", "INFO").upper()

# API reads use a pool; worker runs use dedicated connections.
DB_POOL_MIN_SIZE = int(os.environ.get("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.environ.get("DB_POOL_MAX_SIZE", "10"))

APP_DB_ROLE = os.environ.get("APP_DB_ROLE", "tsdhn_app")
APP_DB_PASSWORD = os.environ.get("APP_DB_PASSWORD", "")

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
# Browser URLs may use a different endpoint from API requests.
MINIO_PUBLIC_ENDPOINT = os.environ.get("MINIO_PUBLIC_ENDPOINT", MINIO_ENDPOINT)
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "tsdhn-results")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() in {
    "1",
    "true",
    "yes",
}

OUTPUT_URL_TTL = int(os.environ.get("OUTPUT_URL_TTL_SECONDS", str(15 * 60)))

SSE_MAX_DURATION = int(os.environ.get("SSE_MAX_DURATION_SECONDS", str(30 * 60)))

# Unset means Numba uses the CPUs visible to the process.
NUMBA_THREADS: int | None = (
    int(os.environ["TSDHN_NUMBA_THREADS"])
    if os.environ.get("TSDHN_NUMBA_THREADS")
    else None
)
