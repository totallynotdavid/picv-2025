"""Shared fixtures for API database tests."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest

from api.core.schema import COMPUTE_SCHEMA_SQL
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
