"""Connection boundary behavior for the compute service."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest

from api.core import db
from api.core.errors import TransientInfraError

db_module: Any = db


class _Pool:
    def __init__(self) -> None:
        self.connection_value = object()

    @contextmanager
    def connection(self) -> Iterator[object]:
        yield self.connection_value


def test_pooled_yields_a_connection_from_the_process_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _Pool()
    monkeypatch.setattr(db_module, "get_pool", lambda: pool)

    with db.pooled() as connection:
        assert connection is pool.connection_value


def test_connect_classifies_a_database_outage_as_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: Any, **kwargs: Any) -> object:
        raise psycopg.OperationalError("database unavailable")

    monkeypatch.setattr(db_module.psycopg, "connect", fail)

    with pytest.raises(TransientInfraError, match="database connection failed"):
        db.connect()
