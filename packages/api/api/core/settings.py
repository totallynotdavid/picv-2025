import os
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

__all__ = [
    "APP_DB_PASSWORD",
    "APP_DB_ROLE",
    "COMPUTE_DATABASE_URL",
    "COMPUTE_PRODUCER_PASSWORD",
    "COMPUTE_PRODUCER_ROLE",
    "COMPUTE_PURGER_PASSWORD",
    "COMPUTE_PURGER_ROLE",
    "COMPUTE_QUEUE",
    "COMPUTE_QUEUE_SCHEMA",
    "COMPUTE_WORKER_PASSWORD",
    "COMPUTE_WORKER_ROLE",
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
    "SSE_MAX_DURATION",
    "WORKER_CONCURRENCY",
    "WORKER_ID",
    "WORKER_LEASE_SECONDS",
    "api_pool_size",
    "worker_pool_size",
]

COMPUTE_DATABASE_URL = os.environ.get(
    "COMPUTE_DATABASE_URL",
    "postgresql://tsdhn:tsdhn@localhost:5432/tsdhn",
)

COMPUTE_QUEUE = os.environ.get("COMPUTE_QUEUE", "simulations")

# rqueue owns its own schema and never shares one with application tables, so
# this must not be `compute`: that schema is compute.jobs' own.
COMPUTE_QUEUE_SCHEMA = os.environ.get("COMPUTE_QUEUE_SCHEMA", "task_queue")

JOBS_DIR: Path = Path(os.environ.get("TSDHN_JOBS_DIR", "jobs")).resolve()

LOG_LEVEL = os.environ.get("TSDHN_LOG_LEVEL", "INFO").upper()

# Zero keeps the pool lazy, so a process starts before PostgreSQL is
# reachable and reports the outage through /health instead of refusing to
# boot -- the behaviour the psycopg pool had with open(wait=False).
DB_POOL_MIN_SIZE = int(os.environ.get("DB_POOL_MIN_SIZE", "0"))
DB_POOL_MAX_SIZE = int(os.environ.get("DB_POOL_MAX_SIZE", "10"))

# One simulation saturates the machine's cores, so the worker runs one job at a
# time unless a deployment says otherwise.
WORKER_CONCURRENCY = int(os.environ.get("TSDHN_WORKER_CONCURRENCY", "1"))

# A lease this long tolerates a slow database round trip; rqueue heartbeats at
# a third of it while the simulation runs off the event loop.
WORKER_LEASE_SECONDS = float(os.environ.get("TSDHN_WORKER_LEASE_SECONDS", "60"))

WORKER_ID = os.environ.get("TSDHN_WORKER_ID", "")


def api_pool_size() -> tuple[int, int]:
    """Return the API process's pool bounds."""
    return DB_POOL_MIN_SIZE, max(DB_POOL_MIN_SIZE, DB_POOL_MAX_SIZE)


def worker_pool_size() -> tuple[int, int]:
    """Return the worker process's pool bounds.

    This floor is load bearing, not cosmetic. `rqueue.Worker` holds one
    connection for the whole run to LISTEN on its wake channel, borrows one per
    poll to recover expired leases and claim, one per heartbeat, and one per
    progress write from a running simulation. When the pool cannot spare a
    connection for the listener, rqueue logs a warning and falls back to
    polling only, which is a latency regression that is easy to misdiagnose.
    """
    max_size = max(DB_POOL_MAX_SIZE, 2 * WORKER_CONCURRENCY + 4)
    return min(DB_POOL_MIN_SIZE, max_size), max_size


APP_DB_ROLE = os.environ.get("APP_DB_ROLE", "tsdhn_app")
APP_DB_PASSWORD = os.environ.get("APP_DB_PASSWORD", "")

# COMPUTE_DATABASE_URL names the schema owner: the role that runs migrations
# and owns both `compute` and the queue schema. Runtime processes use these
# roles instead, each provisioned with only the grants its process needs.
COMPUTE_PRODUCER_ROLE = os.environ.get("COMPUTE_PRODUCER_ROLE", "tsdhn_producer")
COMPUTE_PRODUCER_PASSWORD = os.environ.get("COMPUTE_PRODUCER_PASSWORD", "")

COMPUTE_WORKER_ROLE = os.environ.get("COMPUTE_WORKER_ROLE", "tsdhn_worker")
COMPUTE_WORKER_PASSWORD = os.environ.get("COMPUTE_WORKER_PASSWORD", "")

# Retention deletes queue history, which no consuming role may do. Keeping it
# on its own credential means a deployment can withhold it or move retention
# to a maintenance container without changing the worker role.
COMPUTE_PURGER_ROLE = os.environ.get("COMPUTE_PURGER_ROLE", "tsdhn_purger")
COMPUTE_PURGER_PASSWORD = os.environ.get("COMPUTE_PURGER_PASSWORD", "")


def role_database_url(role: str, password: str) -> str | None:
    """Return the compute URL rewritten to connect as `role`.

    A missing role or password means the role has not been provisioned. The
    runtime caller can then retain the owner URL while warning the operator.
    Credentials are percent-encoded because passwords commonly contain URL
    punctuation.
    """
    if not role or not password:
        return None
    parts = urlsplit(COMPUTE_DATABASE_URL)
    credentials = f"{quote(role, safe='')}:{quote(password, safe='')}"
    # Preserve the authority verbatim. asyncpg accepts socket URLs with no
    # hostname and multi-host authorities; accessing ``parts.hostname`` or
    # ``parts.port`` would reject those valid DSN forms before asyncpg sees
    # them. Existing userinfo is replaced by taking everything after the last
    # @, while the raw host list (if any) remains untouched.
    authority = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit(parts._replace(netloc=f"{credentials}@{authority}"))


MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
# Public endpoint differs from API endpoint for browser downloads.
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
