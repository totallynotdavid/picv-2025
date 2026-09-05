"""The process-wide asyncpg pool, shared by the API and the worker.

Both processes open one pool in `open_pool(...)` and take a connection from it
per statement (or per transaction). Nothing holds a connection across a
simulation run: the only long-lived borrow in the system is the one
`rqueue.Worker` makes to LISTEN on its wake channel, which is why
`settings.worker_pool_size()` sizes the worker's pool the way it does.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

from api.core.errors import TransientInfraError
from api.core.settings import COMPUTE_DATABASE_URL

__all__ = [
    "CONNECT_TIMEOUT",
    "JobRow",
    "acquire",
    "close_pool",
    "connect",
    "get_pool",
    "is_transient",
    "notify_channel",
    "open_pool",
    "transient_connection_errors",
]

JobRow = dict[str, Any]
CONNECT_TIMEOUT = 2

_pool: asyncpg.Pool | None = None

# Client-side failures: the server was never reached, or the socket died.
_CLIENT_ERRORS = (ConnectionError, OSError, TimeoutError)

# Server-side failures are classified by SQLSTATE *class* rather than by
# exception type. An enumerated tuple of asyncpg classes is the wrong basis:
# it looked complete and was not (`TooManyConnectionsError` is an
# `InsufficientResourcesError`, not a `PostgresConnectionError`, so pool
# exhaustion read as permanent), and it grows by one entry per incident.
#
#   08  connection_exception     the connection broke or was refused
#   53  insufficient_resources   too many connections, out of memory, disk full
#   57  operator_intervention    admin shutdown, crash shutdown, cannot connect now
#   40  transaction_rollback     serialization failure, deadlock detected
#
# The asymmetry justifies the width. Classifying a transient failure as
# permanent throws away a simulation that would have succeeded -- tens of
# minutes of compute, and an operator retry to get it back. Classifying a
# permanent failure as transient costs two extra attempts and roughly 45s of
# backoff before it fails anyway with the same error. So the few permanent
# members inside these classes (57P04 database_dropped, say) are worth carrying
# to catch every transient one.
#
# Deliberately *not* included: 22 (data exception), 23 (integrity constraint),
# 42 (syntax and access rules). Those are application bugs, and a retry there
# re-runs a whole simulation to reach the identical failure.
_TRANSIENT_SQLSTATE_CLASSES = frozenset({"08", "40", "53", "57"})


def is_transient(exc: BaseException) -> bool:
    """Whether this failure could plausibly succeed on a later attempt."""
    if isinstance(exc, _CLIENT_ERRORS):
        return True
    sqlstate = getattr(exc, "sqlstate", None)
    return isinstance(sqlstate, str) and sqlstate[:2] in _TRANSIENT_SQLSTATE_CLASSES


async def open_pool(*, min_size: int, max_size: int) -> asyncpg.Pool:
    """Create the process-wide pool. Idempotent within one process."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            COMPUTE_DATABASE_URL,
            min_size=min_size,
            max_size=max_size,
            timeout=CONNECT_TIMEOUT,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the open pool, or explain that startup did not open one."""
    if _pool is None:
        raise RuntimeError("database pool is not open; call db.open_pool() first")
    return _pool


@asynccontextmanager
async def transient_connection_errors(
    connection: asyncpg.Connection,
) -> AsyncIterator[None]:
    """Translate a connection lost mid-statement into `TransientInfraError`.

    `acquire()` covers only the borrow, which is not where a database restart
    under a running simulation actually lands. asyncpg reports a connection
    that dies around a statement two different ways, and only one of them was
    already covered:

    - the backend dies with the statement in flight -> `ConnectionDoesNotExist`,
      SQLSTATE 08003, which `is_transient` recognises;
    - the backend is already gone when the statement is issued -> a bare
      `InterfaceError("connection is closed")`, which is not a connection
      error class at all.

    `InterfaceError` is also what asyncpg raises for a genuine programming
    error ("the server expects 2 arguments for this query, 1 was passed"), so
    it is translated only when the connection really is gone. That distinction
    is load bearing: `TRANSIENT_RETRY` retries `TransientInfraError`, so
    mistranslating a bug would spend a job's whole retry budget re-running
    something that cannot succeed. A programming error leaves the connection
    open and propagates unchanged.
    """
    try:
        yield
    except asyncpg.InterfaceError as e:
        if not _connection_is_gone(connection):
            raise
        raise TransientInfraError("database unavailable") from e
    except Exception as e:
        if not is_transient(e):
            raise
        raise TransientInfraError("database unavailable") from e


def _connection_is_gone(connection: asyncpg.Connection) -> bool:
    """Whether this connection can still be used for anything at all.

    Not simply `is_closed()`. When a pooled connection's backend dies, the
    pool terminates the connection and takes the proxy back, after which
    *every* method on that proxy raises `InterfaceError("cannot call
    Connection.is_closed(): connection has been released back to the pool")` --
    the question included. A proxy that cannot answer is certainly gone,
    whereas a connection that merely rejected a malformed call answers
    `False` and keeps working.
    """
    try:
        return bool(connection.is_closed())
    except asyncpg.InterfaceError:
        return True


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    """Borrow a pooled connection for one statement or one transaction."""
    pool = get_pool()
    try:
        connection = await pool.acquire()
    except Exception as e:
        # Pool exhaustion arrives here as TooManyConnectionsError (53300), which
        # is every bit as retryable as a refused socket.
        if not is_transient(e):
            raise
        raise TransientInfraError("database unavailable") from e
    try:
        yield connection
    finally:
        await pool.release(connection)


async def connect() -> asyncpg.Connection:
    """Open a connection outside the pool.

    The SSE endpoint holds one of these for the lifetime of a stream, which can
    be half an hour. Taking that from the request pool would let a handful of
    watching browsers starve every other route.
    """
    try:
        return await asyncpg.connect(COMPUTE_DATABASE_URL, timeout=CONNECT_TIMEOUT)
    except Exception as e:
        if not is_transient(e):
            raise
        raise TransientInfraError("database unavailable") from e


def notify_channel(simulation_id: uuid.UUID) -> str:
    """Return the SQL-safe notification channel for one job."""
    return f"tsdhn_job_{simulation_id.hex}"
