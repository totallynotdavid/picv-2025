"""Connection boundary behavior for the compute service."""

from typing import Any

import asyncpg
import pytest

from api.core import db, settings
from api.core.errors import TransientInfraError

db_module: Any = db


@pytest.mark.asyncio
async def test_acquire_borrows_and_returns_a_pooled_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = object()
    released: list[object] = []

    class _Pool:
        async def acquire(self) -> object:
            return connection

        async def release(self, borrowed: object) -> None:
            released.append(borrowed)

    monkeypatch.setattr(db_module, "get_pool", lambda: _Pool())

    async with db.acquire() as borrowed:
        assert borrowed is connection
    assert released == [connection]


@pytest.mark.asyncio
async def test_acquire_classifies_a_database_outage_as_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Pool:
        async def acquire(self) -> object:
            raise ConnectionRefusedError("database unavailable")

    monkeypatch.setattr(db_module, "get_pool", lambda: _Pool())

    with pytest.raises(TransientInfraError, match="database unavailable"):
        async with db.acquire():
            pytest.fail("acquire must not yield when the database is unreachable")


@pytest.mark.asyncio
async def test_connect_classifies_a_database_outage_as_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*args: Any, **kwargs: Any) -> object:
        raise OSError("database unavailable")

    monkeypatch.setattr(db_module.asyncpg, "connect", fail)

    with pytest.raises(TransientInfraError, match="database unavailable"):
        await db.connect()


@pytest.mark.asyncio
async def test_a_postgres_connection_error_is_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # asyncpg raises this, not OSError, when the server answers and refuses.
    async def fail(*args: Any, **kwargs: Any) -> object:
        raise asyncpg.PostgresConnectionError("server closed the connection")

    monkeypatch.setattr(db_module.asyncpg, "connect", fail)

    with pytest.raises(TransientInfraError):
        await db.connect()


def test_get_pool_says_which_call_was_missed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_module, "_pool", None)

    with pytest.raises(RuntimeError, match=r"db\.open_pool"):
        db.get_pool()


def test_the_worker_pool_leaves_room_for_the_listener_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # rqueue.Worker._listener() holds one connection for the whole run. A pool
    # sized to concurrency alone would starve it and silently drop back to
    # polling, so the floor has to exceed the worker's own concurrency.
    monkeypatch.setattr(settings, "WORKER_CONCURRENCY", 4)
    monkeypatch.setattr(settings, "DB_POOL_MAX_SIZE", 2)

    _, max_size = settings.worker_pool_size()

    assert max_size > settings.WORKER_CONCURRENCY + 1
    assert max_size == 2 * 4 + 4


def test_the_worker_pool_never_shrinks_below_the_configured_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "WORKER_CONCURRENCY", 1)
    monkeypatch.setattr(settings, "DB_POOL_MAX_SIZE", 20)

    assert settings.worker_pool_size()[1] == 20


def test_notify_channel_is_a_bare_identifier_per_job() -> None:
    import uuid

    simulation_id = uuid.UUID("4cfe522f-7e7d-46e0-96ca-7b98743fb9f5")
    channel = db.notify_channel(simulation_id)

    assert channel == "tsdhn_job_4cfe522f7e7d46e096ca7b98743fb9f5"
    # No hyphens or quoting needed: it goes straight into LISTEN/NOTIFY.
    assert channel.replace("_", "").isalnum()
    assert db.notify_channel(uuid.uuid4()) != channel


def test_role_database_url_swaps_only_the_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "COMPUTE_DATABASE_URL",
        "postgresql://owner:secret@db.internal:5432/tsdhn",
    )

    url = settings.role_database_url("tsdhn_producer", "p@ss word")

    assert url == "postgresql://tsdhn_producer:p%40ss%20word@db.internal:5432/tsdhn"


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        (
            "postgresql:///tsdhn?host=/var/run/postgresql",
            "postgresql://tsdhn_worker:secret@/tsdhn?host=/var/run/postgresql",
        ),
        (
            "postgresql://owner:old@db1:5432,db2:5432/tsdhn",
            "postgresql://tsdhn_worker:secret@db1:5432,db2:5432/tsdhn",
        ),
    ],
)
def test_role_database_url_preserves_asyncpg_dsn_authorities(
    monkeypatch: pytest.MonkeyPatch, database_url: str, expected: str
) -> None:
    monkeypatch.setattr(settings, "COMPUTE_DATABASE_URL", database_url)

    assert settings.role_database_url("tsdhn_worker", "secret") == expected


def test_an_unprovisioned_role_leaves_the_caller_on_the_owner_connection() -> None:
    assert settings.role_database_url("tsdhn_producer", "") is None
    assert settings.role_database_url("", "secret") is None


def test_runtime_dsn_warns_when_a_role_is_unprovisioned(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        assert db.runtime_dsn("tsdhn_producer", "") is None

    assert "tsdhn_producer" in caplog.text


@pytest.mark.asyncio
async def test_connect_reuses_the_dsn_the_pool_was_opened_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    async def create_pool(dsn: str, **_kwargs: Any) -> object:
        return object()

    async def connect(dsn: str, **_kwargs: Any) -> object:
        seen.append(dsn)
        return object()

    monkeypatch.setattr(db_module.asyncpg, "create_pool", create_pool)
    monkeypatch.setattr(db_module.asyncpg, "connect", connect)
    monkeypatch.setattr(db_module, "_pool", None)
    monkeypatch.setattr(db_module, "_dsn", None)

    await db.open_pool(min_size=0, max_size=1, dsn="postgresql://role:pw@host/db")
    await db.connect()

    assert seen == ["postgresql://role:pw@host/db"]


class _Connection:
    """A connection that reports whether it is closed, like asyncpg's."""

    def __init__(self, *, closed: bool) -> None:
        self._closed = closed

    def is_closed(self) -> bool:
        return self._closed


@pytest.mark.asyncio
async def test_a_backend_that_dies_mid_statement_is_transient() -> None:
    # What asyncpg raises when the backend goes away with a query in flight.
    with pytest.raises(TransientInfraError, match="database unavailable"):
        async with db.transient_connection_errors(_Connection(closed=False)):
            raise asyncpg.ConnectionDoesNotExistError("connection was closed")


@pytest.mark.asyncio
async def test_a_statement_issued_on_a_dead_connection_is_transient() -> None:
    # What asyncpg raises when the backend was already gone: a bare
    # InterfaceError, which is in no connection-error class at all.
    with pytest.raises(TransientInfraError, match="database unavailable"):
        async with db.transient_connection_errors(_Connection(closed=True)):
            raise asyncpg.InterfaceError("connection is closed")


@pytest.mark.asyncio
async def test_a_programming_error_is_not_disguised_as_an_outage() -> None:
    # asyncpg raises InterfaceError for a bad call too ("the server expects 2
    # arguments for this query, 1 was passed"), on a connection that is still
    # perfectly healthy. Retrying that spends the job's budget on a bug.
    with pytest.raises(asyncpg.InterfaceError, match="expects 2 arguments"):
        async with db.transient_connection_errors(_Connection(closed=False)):
            raise asyncpg.InterfaceError("the server expects 2 arguments")


@pytest.mark.asyncio
async def test_an_unrelated_error_passes_through_untouched() -> None:
    with pytest.raises(ValueError, match="not a connection problem"):
        async with db.transient_connection_errors(_Connection(closed=True)):
            raise ValueError("not a connection problem")


@pytest.mark.asyncio
async def test_a_pool_proxy_that_cannot_answer_is_treated_as_gone() -> None:
    # A pooled connection whose backend died is terminated and taken back by
    # the pool, and every method on the proxy then raises -- is_closed() too.
    class _ReleasedProxy:
        def is_closed(self) -> bool:
            raise asyncpg.InterfaceError(
                "cannot call Connection.is_closed(): "
                "connection has been released back to the pool"
            )

    with pytest.raises(TransientInfraError, match="database unavailable"):
        async with db.transient_connection_errors(_ReleasedProxy()):
            raise asyncpg.InterfaceError("cannot call Connection.execute()")


@pytest.mark.parametrize(
    ("exception", "transient"),
    [
        # 53300: the pool or the server ran out of connections. Not a
        # PostgresConnectionError -- the reason an exception-type allowlist
        # classified this as permanent and threw away retryable jobs.
        (asyncpg.TooManyConnectionsError("sorry, too many clients already"), True),
        (asyncpg.OutOfMemoryError("out of memory"), True),  # 53200
        (asyncpg.ConnectionDoesNotExistError("connection was closed"), True),  # 08003
        (asyncpg.CannotConnectNowError("the database is starting up"), True),  # 57P03
        (asyncpg.AdminShutdownError("terminating connection"), True),  # 57P01
        (asyncpg.DeadlockDetectedError("deadlock detected"), True),  # 40P01
        (asyncpg.SerializationError("could not serialize"), True),  # 40001
        (ConnectionResetError("peer reset"), True),
        (TimeoutError("timed out"), True),
        # Application bugs: a retry re-runs a whole simulation to fail the same
        # way, so these have to stay permanent.
        (asyncpg.UndefinedColumnError("column does not exist"), False),  # 42703
        (asyncpg.UniqueViolationError("duplicate key"), False),  # 23505
        (asyncpg.InvalidTextRepresentationError("invalid uuid"), False),  # 22P02
        (ValueError("not a database problem"), False),
    ],
)
def test_transient_classification_follows_the_sqlstate_class(
    exception: BaseException, transient: bool
) -> None:
    assert db.is_transient(exception) is transient


@pytest.mark.asyncio
async def test_pool_exhaustion_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Pool:
        async def acquire(self) -> object:
            raise asyncpg.TooManyConnectionsError("sorry, too many clients already")

    monkeypatch.setattr(db_module, "get_pool", lambda: _Pool())

    with pytest.raises(TransientInfraError, match="database unavailable"):
        async with db.acquire():
            pass
