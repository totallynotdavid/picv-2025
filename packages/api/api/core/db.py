"""Database connections for API reads, workers, and job notifications."""

import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from api.core.errors import TransientInfraError
from api.core.settings import (
    COMPUTE_DATABASE_URL,
    DB_POOL_MAX_SIZE,
    DB_POOL_MIN_SIZE,
)

__all__ = [
    "CONNECT_TIMEOUT",
    "JobRow",
    "close_pool",
    "connect",
    "get_pool",
    "notify_channel",
    "pooled",
]

JobRow = dict[str, Any]
CONNECT_TIMEOUT = 2

_pool: ConnectionPool[psycopg.Connection[JobRow]] | None = None
_pool_lock = threading.Lock()


def _new_pool() -> ConnectionPool[psycopg.Connection[JobRow]]:
    return ConnectionPool(
        COMPUTE_DATABASE_URL,
        min_size=DB_POOL_MIN_SIZE,
        max_size=DB_POOL_MAX_SIZE,
        kwargs={"row_factory": dict_row, "connect_timeout": CONNECT_TIMEOUT},
        open=False,
    )


def get_pool() -> ConnectionPool[psycopg.Connection[JobRow]]:
    """Return the process-wide pool, creating it on first use."""
    global _pool
    with _pool_lock:
        if _pool is None or _pool.closed:
            _pool = _new_pool()
            _pool.open(wait=False)
        return _pool


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None and not _pool.closed:
            _pool.close()
        _pool = None


@contextmanager
def pooled() -> Iterator[psycopg.Connection[JobRow]]:
    """Provide a short-lived connection for API queries."""
    with get_pool().connection() as conn:
        yield conn


def connect() -> psycopg.Connection[JobRow]:
    """Open a dedicated worker connection."""
    try:
        return psycopg.connect(
            COMPUTE_DATABASE_URL,
            connect_timeout=CONNECT_TIMEOUT,
            row_factory=dict_row,
        )
    except psycopg.OperationalError as e:
        raise TransientInfraError("database connection failed") from e


def notify_channel(simulation_id: uuid.UUID) -> str:
    """Return the SQL-safe notification channel for one job."""
    return f"tsdhn_job_{simulation_id.hex}"
