"""Shared fixtures for API database tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
import pytest_asyncio
from rqueue import Queue, migrations

from api.core import db
from api.core.queue import build_queue, set_queue
from api.core.schema import COMPUTE_SCHEMA_SQL
from api.core.settings import COMPUTE_QUEUE_SCHEMA
from api.core.tasks import register_tasks
from scripts.database import create_database, drop_database

LOCAL_DATABASE_URL = "postgresql://tsdhn:tsdhn@127.0.0.1:5432/tsdhn"


@pytest.fixture
def isolated_database() -> Iterator[str]:
    """Yield a fresh compute database and remove it after the test."""
    database_name = f"tsdhn_test_{uuid.uuid4().hex}"
    try:
        target = create_database(LOCAL_DATABASE_URL, database_name)
    except psycopg.OperationalError as error:
        pytest.exit(
            f"PostgreSQL is not reachable at {LOCAL_DATABASE_URL} ({error}). "
            "Run `mise run db:start` or `mise run test-integration` first.",
            returncode=1,
        )

    try:
        with psycopg.connect(target.database_url) as connection:
            connection.execute(COMPUTE_SCHEMA_SQL)
        yield target.database_url
    finally:
        drop_database(LOCAL_DATABASE_URL, database_name)


@pytest_asyncio.fixture
async def queue(
    isolated_database: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Queue]:
    """Point the process-wide pool and queue at a disposable database.

    Both schemas are applied the way a deployment applies them: the compute
    schema by `isolated_database`, the queue schema by rqueue's own migration
    runner. Neither is ever created implicitly at import or worker startup.
    """
    monkeypatch.setattr(db, "COMPUTE_DATABASE_URL", isolated_database)
    pool = await db.open_pool(min_size=1, max_size=6)
    async with pool.acquire() as connection:
        await migrations.migrate(connection, schema=COMPUTE_QUEUE_SCHEMA)
    try:
        yield register_tasks(build_queue(pool))
    finally:
        set_queue(None)
        await db.close_pool()
