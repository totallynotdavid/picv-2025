"""Database-independent checks for queue-role configuration."""

from typing import Any, cast

import pytest

from api import queue_grants


@pytest.mark.asyncio
async def test_queue_role_names_must_be_pairwise_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(queue_grants, "COMPUTE_PRODUCER_ROLE", "same-role")
    monkeypatch.setattr(queue_grants, "COMPUTE_WORKER_ROLE", "same-role")
    monkeypatch.setattr(queue_grants, "COMPUTE_PURGER_ROLE", "purger-role")

    with pytest.raises(ValueError, match="pairwise distinct"):
        await queue_grants.provision_queue_roles(cast(Any, object()))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "conflict"),
    [
        ("COMPUTE_PRODUCER_ROLE", "web-role", "APP_DB_ROLE"),
        ("COMPUTE_WORKER_ROLE", "db-owner", "COMPUTE_DATABASE_URL username"),
    ],
)
async def test_queue_role_names_cannot_overwrite_protected_roles(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
    conflict: str,
) -> None:
    monkeypatch.setattr(queue_grants, "COMPUTE_PRODUCER_ROLE", "producer-role")
    monkeypatch.setattr(queue_grants, "COMPUTE_WORKER_ROLE", "worker-role")
    monkeypatch.setattr(queue_grants, "COMPUTE_PURGER_ROLE", "purger-role")
    monkeypatch.setattr(queue_grants, field, value)
    if conflict == "APP_DB_ROLE":
        monkeypatch.setattr(queue_grants, "APP_DB_ROLE", value)
    else:
        monkeypatch.setattr(
            queue_grants,
            "COMPUTE_DATABASE_URL",
            "postgresql://db-owner:secret@localhost:5432/tsdhn",
        )

    with pytest.raises(ValueError, match=conflict):
        await queue_grants.provision_queue_roles(cast(Any, object()))
