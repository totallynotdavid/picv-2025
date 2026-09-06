"""Provision the least-privilege roles the API and worker connect as.

`tsdhn-compute-migrate` owns the compute schema and the web role;
`rqueue ... migrate` owns the queue schema. This runs after both, for the same
reason `tsdhn-web-grants` runs after the web migrations: a GRANT needs the
tables to exist. Everything here is idempotent, and re-running it narrows a
role that has been over-granted back to the table below.

| role                | queue schema                          | compute schema |
| ------------------- | ------------------------------------- | -------------- |
| COMPUTE_PRODUCER    | `Capability.PRODUCE`                  | SELECT, INSERT |
| COMPUTE_WORKER      | `Capability.CONSUME`                  | SELECT, UPDATE |
| COMPUTE_PURGER      | `Capability.INSPECT` + DELETE on jobs | none           |

`provision_role` grants no DDL to any of them, and row-level security scopes
`jobs` and `job_attempts` to the one queue this deployment runs;
`concurrency_slots` and `runtime_heartbeats` have no per-queue RLS in rqueue
today, which is fine for this single-queue deployment.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import asyncpg
from rqueue.models import TERMINAL_STATES
from rqueue.roles import Capability, provision_role

from api.core.settings import (
    APP_DB_ROLE,
    COMPUTE_DATABASE_URL,
    COMPUTE_PRODUCER_PASSWORD,
    COMPUTE_PRODUCER_ROLE,
    COMPUTE_PURGER_PASSWORD,
    COMPUTE_PURGER_ROLE,
    COMPUTE_QUEUE,
    COMPUTE_QUEUE_SCHEMA,
    COMPUTE_WORKER_PASSWORD,
    COMPUTE_WORKER_ROLE,
)

__all__ = ["QueueRole", "provision_queue_roles", "queue_roles"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueueRole:
    """One runtime role: what it may do to the queue, and to `compute.jobs`."""

    name: str
    password: str
    #: The environment variable the password comes from, for error messages.
    env_var: str
    capabilities: tuple[Capability, ...]
    #: Privileges on `compute.jobs`; empty means the role never reaches it.
    compute_privileges: str = ""
    #: Queue-table privileges no capability's grant set covers.
    extra_queue_privileges: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def queue_roles() -> tuple[QueueRole, ...]:
    """The roles this deployment runs, read from settings at call time."""
    return (
        QueueRole(
            name=COMPUTE_PRODUCER_ROLE,
            password=COMPUTE_PRODUCER_PASSWORD,
            env_var="COMPUTE_PRODUCER_PASSWORD",
            # The API only enqueues and reads back. It never touches schedules
            # or queue pauses, which is all INSPECT would add over PRODUCE.
            capabilities=(Capability.PRODUCE,),
            # `create_or_get_job` inserts and reads; no route updates a row.
            compute_privileges="SELECT, INSERT",
        ),
        QueueRole(
            name=COMPUTE_WORKER_ROLE,
            password=COMPUTE_WORKER_PASSWORD,
            env_var="COMPUTE_WORKER_PASSWORD",
            capabilities=(Capability.CONSUME,),
            # The worker only ever advances rows the API created.
            compute_privileges="SELECT, UPDATE",
        ),
        QueueRole(
            name=COMPUTE_PURGER_ROLE,
            password=COMPUTE_PURGER_PASSWORD,
            env_var="COMPUTE_PURGER_PASSWORD",
            # `Admin.purge` reads the terminal rows it is about to remove.
            capabilities=(Capability.INSPECT,),
            # Retention is a queue-only concern: compute.jobs keeps its own
            # history, and this task is not the one to start expiring it.
            compute_privileges="",
            # No capability carries DELETE, on purpose -- a consumer that can
            # delete a job can erase its own attempt history with it. Purge
            # needs exactly this one grant and nothing else.
            extra_queue_privileges=(("jobs", "DELETE"),),
        ),
    )


async def _ddl(connection: asyncpg.Connection, template: str, *args: str) -> None:
    """Run one DDL statement with PostgreSQL doing the identifier quoting.

    The same trick `rqueue.roles` uses: role, schema and table names have no
    bind-parameter form, so `format(..., %I)` is evaluated server-side and only
    its already-quoted result is executed.
    """
    placeholders = ", ".join(f"${index + 2}::text" for index in range(len(args)))
    statement = await connection.fetchval(
        f"SELECT format($1::text, {placeholders})", template, *args
    )
    await connection.execute(statement)


async def _grant_compute_access(
    connection: asyncpg.Connection, role: QueueRole
) -> None:
    """Give one role its `compute.jobs` privileges, and only those.

    The revoke comes first so re-running repairs a role that was widened by
    hand, matching what `migrate.provision_web_role` does for the web role.
    """
    await _ddl(connection, "REVOKE ALL PRIVILEGES ON compute.jobs FROM %I", role.name)
    await _ddl(connection, "REVOKE CREATE ON SCHEMA compute FROM %I", role.name)
    if not role.compute_privileges:
        await _ddl(connection, "REVOKE USAGE ON SCHEMA compute FROM %I", role.name)
        return
    await _ddl(connection, "GRANT USAGE ON SCHEMA compute TO %I", role.name)
    await _ddl(
        connection,
        f"GRANT {role.compute_privileges} ON compute.jobs TO %I",
        role.name,
    )


async def _grant_purger_delete_policy(
    connection: asyncpg.Connection, role: QueueRole
) -> None:
    """Restrict the purger's direct queue deletes to terminal rows."""
    policy_name = "compute_purger_terminal_delete"
    await _ddl(
        connection,
        "DROP POLICY IF EXISTS %I ON %I.%I",
        policy_name,
        COMPUTE_QUEUE_SCHEMA,
        "jobs",
    )
    state_placeholders = ", ".join("%L" for _ in TERMINAL_STATES)
    await _ddl(
        connection,
        "CREATE POLICY %I ON %I.%I AS RESTRICTIVE FOR DELETE TO %I "
        f"USING (state = ANY(ARRAY[{state_placeholders}]::text[]))",
        policy_name,
        COMPUTE_QUEUE_SCHEMA,
        "jobs",
        role.name,
        *TERMINAL_STATES,
    )


def _validate_role_names(roles: tuple[QueueRole, ...]) -> None:
    """Reject runtime roles that could overwrite another database role."""
    role_env_vars = (
        "COMPUTE_PRODUCER_ROLE",
        "COMPUTE_WORKER_ROLE",
        "COMPUTE_PURGER_ROLE",
    )
    names = [role.name for role in roles]
    if len(names) != len(set(names)):
        raise ValueError(
            "COMPUTE_PRODUCER_ROLE, COMPUTE_WORKER_ROLE, and "
            "COMPUTE_PURGER_ROLE must be pairwise distinct"
        )
    protected = (
        ("APP_DB_ROLE", APP_DB_ROLE),
        ("COMPUTE_DATABASE_URL username", urlsplit(COMPUTE_DATABASE_URL).username),
    )
    for env_var, role in zip(role_env_vars, roles, strict=True):
        for protected_name, protected_value in protected:
            if protected_value and role.name == protected_value:
                raise ValueError(
                    f"{env_var}={role.name!r} collides with "
                    f"{protected_name}={protected_value!r}"
                )


async def provision_queue_roles(connection: asyncpg.Connection) -> None:
    """Create or repair every runtime role, scoped to COMPUTE_QUEUE."""
    roles = queue_roles()
    _validate_role_names(roles)

    for role in roles:
        if not role.password:
            raise RuntimeError(
                f"{role.env_var} must be set: it is the password for "
                f"the database role {role.name}."
            )
        await provision_role(
            connection,
            role=role.name,
            capabilities=role.capabilities,
            schema=COMPUTE_QUEUE_SCHEMA,
            # One queue, so the row-level-security scope is that queue rather
            # than '*'. A second queue would need a row here, not a code change.
            queues=(COMPUTE_QUEUE,),
            password=role.password,
        )
        for table, privileges in role.extra_queue_privileges:
            await _ddl(
                connection,
                f"GRANT {privileges} ON %I.%I TO %I",
                COMPUTE_QUEUE_SCHEMA,
                table,
                role.name,
            )
        if role.name == COMPUTE_PURGER_ROLE:
            await _grant_purger_delete_policy(connection, role)
        await _grant_compute_access(connection, role)
        logger.info(
            "provisioned %s with %s on queue %s",
            role.name,
            ", ".join(capability.value for capability in role.capabilities),
            COMPUTE_QUEUE,
        )


async def _run() -> None:
    connection = await asyncpg.connect(COMPUTE_DATABASE_URL)
    try:
        async with connection.transaction():
            await provision_queue_roles(connection)
    finally:
        await connection.close()


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    main()
