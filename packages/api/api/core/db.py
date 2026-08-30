"""Database access for the compute plane: a pooled read/write path for the
API, and the LISTEN/NOTIFY channel that carries job progress to SSE clients.
"""

import logging
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

logger = logging.getLogger(__name__)

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
    """The process-wide read-path pool, built on first use.

    Built lazily rather than at import so nothing blocks on the database
    just by importing this module -- the worker imports it too, and
    `tsdhn-api` must still boot and serve /health when Postgres is down.
    Rebuilt if it was closed: a psycopg_pool instance is single-use, so
    holding one in a module global would make a second app lifespan in the
    same process (a test client, an in-process restart) unusable.
    """
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
    """A pooled connection for short API-side queries.

    Not for the worker's simulation task: that holds its connection across
    a multi-minute run, which would pin a pool slot the API needs. It uses
    `connect()` instead.
    """
    with get_pool().connection() as conn:
        yield conn


def connect() -> psycopg.Connection[JobRow]:
    """A dedicated connection for long-running worker work.

    A connection failure is classified as transient so the caller's
    RetryStrategy retries the whole task rather than failing the job.
    """
    try:
        return psycopg.connect(
            COMPUTE_DATABASE_URL,
            connect_timeout=CONNECT_TIMEOUT,
            row_factory=dict_row,
        )
    except psycopg.OperationalError as e:
        raise TransientInfraError("database connection failed") from e


def notify_channel(external_id: uuid.UUID) -> str:
    """Per-job NOTIFY channel name.

    One channel per job rather than one shared channel with a payload
    filter: a listener then wakes only for its own job, and the hex form
    keeps the channel a bare SQL identifier needing no quoting.
    """
    return f"tsdhn_job_{external_id.hex}"
