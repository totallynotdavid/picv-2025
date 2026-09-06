"""What the least-privilege queue roles can and cannot do, against PostgreSQL.

Every test here connects as a real provisioned role and asserts the boundary
from the grant table in `api.queue_grants`, in both directions: the statement
each process actually runs must succeed, and the neighbouring one it must
never run has to be refused by PostgreSQL, not by application code.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import asyncpg
import pytest
import pytest_asyncio
from rqueue import Admin, Queue, RetryPolicy, TaskContext, Worker
from rqueue.roles import revoke_role

from api import queue_grants
from api import worker as worker_module
from api.core import db
from api.core.settings import COMPUTE_QUEUE, COMPUTE_QUEUE_SCHEMA
from api.core.tasks import JOB_RETENTION, RUN_SIMULATION, purge_finished_jobs
from scripts.database import database_target

pytestmark = pytest.mark.integration

SCHEMA = COMPUTE_QUEUE_SCHEMA
# A disposable role in a disposable database; the cluster trusts localhost.
ROLE_PASSWORD = "queue-role-test-password"


class Roles:
    """The three provisioned role names, and how to connect as one."""

    def __init__(self, database_url: str, suffix: str) -> None:
        self.database_url = database_url
        self.producer = f"tsdhn_test_producer_{suffix}"
        self.worker = f"tsdhn_test_worker_{suffix}"
        self.purger = f"tsdhn_test_purger_{suffix}"

    @property
    def all(self) -> tuple[str, ...]:
        return (self.producer, self.worker, self.purger)

    def url(self, role: str) -> str:
        name = urlsplit(self.database_url).path.lstrip("/")
        return database_target(
            self.database_url, name, user=role, password=ROLE_PASSWORD
        ).database_url

    async def connect(self, role: str) -> asyncpg.Connection:
        return await asyncpg.connect(self.url(role))


@pytest_asyncio.fixture
async def roles(
    queue: Queue, isolated_database: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Roles]:
    """Provision the three roles the way `tsdhn-queue-grants` does."""
    provisioned = Roles(isolated_database, uuid.uuid4().hex[:12])
    monkeypatch.setattr(queue_grants, "COMPUTE_PRODUCER_ROLE", provisioned.producer)
    monkeypatch.setattr(queue_grants, "COMPUTE_WORKER_ROLE", provisioned.worker)
    monkeypatch.setattr(queue_grants, "COMPUTE_PURGER_ROLE", provisioned.purger)
    for setting in (
        "COMPUTE_PRODUCER_PASSWORD",
        "COMPUTE_WORKER_PASSWORD",
        "COMPUTE_PURGER_PASSWORD",
    ):
        monkeypatch.setattr(queue_grants, setting, ROLE_PASSWORD)

    async with db.acquire() as connection:
        await queue_grants.provision_queue_roles(connection)
    try:
        yield provisioned
    finally:
        async with db.acquire() as connection:
            for role in provisioned.all:
                await revoke_role(connection, role=role, schema=SCHEMA, drop=True)


@pytest.mark.asyncio
async def test_unprovisioned_purger_uses_a_separate_owner_pool(
    queue: Queue, roles: Roles, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The development fallback still has purge privileges without a role."""
    job_id = await _enqueue(queue)
    await _finish(job_id, age=JOB_RETENTION + timedelta(days=1))

    worker_pool = await asyncpg.create_pool(
        roles.url(roles.worker), min_size=1, max_size=1
    )
    assert worker_pool is not None
    monkeypatch.setattr(worker_module, "COMPUTE_PURGER_PASSWORD", "")
    try:
        async with worker_module.purge_pool() as fallback_pool:
            assert fallback_pool is not worker_pool
            async with fallback_pool.acquire() as connection:
                assert await connection.fetchval("SELECT current_user") == "tsdhn"
            assert (
                await purge_finished_jobs(
                    Admin(fallback_pool, schema=SCHEMA), compute_pool=worker_pool
                )
                == 1
            )
    finally:
        await worker_pool.close()


async def _enqueue(queue: Queue, **kwargs: Any) -> uuid.UUID:
    compute_job_id = uuid.uuid4()
    async with db.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO compute.jobs (id, simulation_id, status, input_params)
            VALUES ($1, gen_random_uuid(), 'queued', '{}'::jsonb)
            """,
            compute_job_id,
        )
        job = await queue.enqueue(
            connection,
            task=RUN_SIMULATION,
            payload={"compute_job_id": str(compute_job_id)},
            **kwargs,
        )
    job_id: uuid.UUID = job.id
    return job_id


async def _finish(
    job_id: uuid.UUID,
    *,
    age: timedelta,
    state: str = "succeeded",
    reconcile: bool = True,
) -> None:
    """Put one job in a terminal state, finished `age` ago."""
    async with db.acquire() as connection:
        await connection.execute(
            f"""
            UPDATE {SCHEMA}.jobs
            SET state = $2, attempt = 1, started_at = $3, finished_at = $3,
                lease_token = NULL, leased_until = NULL
            WHERE id = $1
            """,  # noqa: S608 - the schema is a validated identifier, not input
            job_id,
            state,
            datetime.now(UTC) - age,
        )
        if reconcile:
            compute_job_id = await connection.fetchval(
                f"SELECT payload->>'compute_job_id' FROM {SCHEMA}.jobs WHERE id = $1",  # noqa: S608
                job_id,
            )
            await connection.execute(
                "UPDATE compute.jobs SET status = $2, finished_at = $3 WHERE id = $1",
                uuid.UUID(compute_job_id),
                "completed" if state == "succeeded" else "failed",
                datetime.now(UTC) - age,
            )
        await connection.execute(
            f"""
            INSERT INTO {SCHEMA}.job_attempts
                (job_id, queue, task, attempt, worker_id, lease_token,
                 finished_at, outcome)
            VALUES ($1, $2, $3, 1, 'test-worker', gen_random_uuid(), now(), $4)
            """,  # noqa: S608 - the schema is a validated identifier, not input
            job_id,
            COMPUTE_QUEUE,
            RUN_SIMULATION,
            state,
        )


# --------------------------------------------------------------- the producer


@pytest.mark.asyncio
async def test_the_producer_can_enqueue_and_read_but_not_transition(
    queue: Queue, roles: Roles
) -> None:
    connection = await roles.connect(roles.producer)
    try:
        job_id = uuid.uuid4()
        await connection.execute(
            f"""
            INSERT INTO {SCHEMA}.jobs
                (id, queue, task, payload, state, max_attempts)
            VALUES ($1, $2, $3, '{{}}'::jsonb, 'pending', 3)
            """,  # noqa: S608 - the schema is a validated identifier, not input
            job_id,
            COMPUTE_QUEUE,
            RUN_SIMULATION,
        )
        assert (
            await connection.fetchval(
                f"SELECT count(*) FROM {SCHEMA}.jobs WHERE id = $1",  # noqa: S608
                job_id,
            )
            == 1
        )

        # The dedupe-conflict path is DO UPDATE SET updated_at, so this exact
        # column-scoped write is the one UPDATE a producer is allowed.
        await connection.execute(
            f"UPDATE {SCHEMA}.jobs SET updated_at = now() WHERE id = $1",  # noqa: S608
            job_id,
        )

        # Claiming is a whole-row UPDATE, which it must not be able to make.
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                f"UPDATE {SCHEMA}.jobs SET state = 'leased' WHERE id = $1",  # noqa: S608
                job_id,
            )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                f"DELETE FROM {SCHEMA}.jobs WHERE id = $1",  # noqa: S608
                job_id,
            )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_the_producer_reaches_compute_jobs_for_reads_and_inserts_only(
    queue: Queue, roles: Roles
) -> None:
    connection = await roles.connect(roles.producer)
    try:
        await connection.fetchval("SELECT count(*) FROM compute.jobs")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute("UPDATE compute.jobs SET status = 'running'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute("DELETE FROM compute.jobs")
    finally:
        await connection.close()


# ----------------------------------------------------------------- the worker


@pytest.mark.asyncio
async def test_the_worker_can_transition_a_job_but_never_delete_one(
    queue: Queue, roles: Roles
) -> None:
    job_id = await _enqueue(queue)
    connection = await roles.connect(roles.worker)
    try:
        await connection.execute(
            f"""
            UPDATE {SCHEMA}.jobs
            SET state = 'leased', lease_token = gen_random_uuid(),
                leased_until = now() + interval '1 minute', attempt = 1
            WHERE id = $1
            """,  # noqa: S608 - the schema is a validated identifier, not input
            job_id,
        )
        # Purge is not the worker's to run: deleting a job takes its attempt
        # history with it, which a consuming role must not be able to erase.
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(f"DELETE FROM {SCHEMA}.jobs")  # noqa: S608
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(f"DELETE FROM {SCHEMA}.job_attempts")  # noqa: S608
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_the_worker_updates_compute_jobs_but_cannot_create_one(
    queue: Queue, roles: Roles
) -> None:
    connection = await roles.connect(roles.worker)
    try:
        await connection.execute("UPDATE compute.jobs SET status = status")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                "INSERT INTO compute.jobs (id, simulation_id, status, input_params) "
                "VALUES (gen_random_uuid(), gen_random_uuid(), 'queued', '{}'::jsonb)"
            )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_reprovisioning_removes_compute_schema_create_drift(
    queue: Queue, roles: Roles
) -> None:
    """Role repair must remove schema-level CREATE as well as table grants."""
    async with db.acquire() as connection:
        for role in (roles.worker, roles.purger):
            await connection.execute(f'GRANT CREATE ON SCHEMA compute TO "{role}"')
            assert await connection.fetchval(
                "SELECT has_schema_privilege($1, 'compute', 'CREATE')", role
            )

        await queue_grants.provision_queue_roles(connection)

        for role in (roles.worker, roles.purger):
            assert not await connection.fetchval(
                "SELECT has_schema_privilege($1, 'compute', 'CREATE')", role
            )


# ----------------------------------------------------------------- the purger


@pytest.mark.asyncio
async def test_the_purger_may_only_read_and_delete_queue_rows(
    queue: Queue, roles: Roles
) -> None:
    job_id = await _enqueue(queue)
    connection = await roles.connect(roles.purger)
    try:
        assert (
            await connection.fetchval(
                f"SELECT count(*) FROM {SCHEMA}.jobs"  # noqa: S608
            )
            == 1
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                f"UPDATE {SCHEMA}.jobs SET state = 'cancelled'"  # noqa: S608
            )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                f"""
                INSERT INTO {SCHEMA}.jobs
                    (id, queue, task, payload, state, max_attempts)
                VALUES (gen_random_uuid(), $1, $2, '{{}}'::jsonb, 'pending', 1)
                """,  # noqa: S608 - the schema is a validated identifier
                COMPUTE_QUEUE,
                RUN_SIMULATION,
            )
        # The RLS defense in depth rejects direct deletion of active work.
        await connection.execute(
            f"DELETE FROM {SCHEMA}.jobs WHERE id = $1",  # noqa: S608
            job_id,
        )
        assert (
            await connection.fetchval(
                f"SELECT count(*) FROM {SCHEMA}.jobs WHERE id = $1",  # noqa: S608
                job_id,
            )
            == 1
        )
        await _finish(job_id, age=timedelta(days=1))
        # Retention itself, which is the one thing this role exists for.
        await connection.execute(
            f"DELETE FROM {SCHEMA}.jobs WHERE id = $1",  # noqa: S608
            job_id,
        )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_the_purger_cannot_see_the_compute_schema_at_all(
    queue: Queue, roles: Roles
) -> None:
    connection = await roles.connect(roles.purger)
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.fetchval("SELECT count(*) FROM compute.jobs")
    finally:
        await connection.close()


# ------------------------------------------------------------- shared floors


@pytest.mark.asyncio
@pytest.mark.parametrize("which", ["producer", "worker", "purger"])
async def test_no_runtime_role_can_run_ddl(
    queue: Queue, roles: Roles, which: str
) -> None:
    connection = await roles.connect(getattr(roles, which))
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(f"CREATE TABLE {SCHEMA}.forbidden (id integer)")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(f"ALTER TABLE {SCHEMA}.jobs ADD COLUMN x integer")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute("CREATE SCHEMA forbidden")
    finally:
        await connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("which", ["producer", "worker", "purger"])
async def test_a_role_is_scoped_to_this_deployments_queue(
    queue: Queue, roles: Roles, which: str
) -> None:
    # Row-level security, not a grant: the roles are granted COMPUTE_QUEUE
    # rather than '*', so a job on another queue is invisible to all of them.
    await _enqueue(queue)
    async with db.acquire() as connection:
        await connection.execute(
            f"""
            INSERT INTO {SCHEMA}.jobs (id, queue, task, payload, state, max_attempts)
            VALUES (gen_random_uuid(), 'other', $1, '{{}}'::jsonb, 'pending', 3)
            """,  # noqa: S608 - the schema is a validated identifier, not input
            RUN_SIMULATION,
        )

    connection = await roles.connect(getattr(roles, which))
    try:
        visible = await connection.fetch(
            f"SELECT queue FROM {SCHEMA}.jobs"  # noqa: S608
        )
    finally:
        await connection.close()

    assert [row["queue"] for row in visible] == [COMPUTE_QUEUE]


# ------------------------------------------------- the real end-to-end paths


@pytest.mark.asyncio
async def test_the_provisioned_roles_run_the_real_enqueue_and_claim_paths(
    queue: Queue, roles: Roles
) -> None:
    """A grant table that passes SQL probes but not rqueue's own SQL is no use.

    So this drives the code the two processes actually run: `Queue.enqueue`
    with the dedupe conflict path the producer needs `UPDATE (updated_at)`
    for, then a real `Worker` claiming, heartbeating and finalizing the job.
    """
    probe = "tests.role_probe"
    ran: list[str] = []

    async def handler(_payload: Any, _context: TaskContext) -> None:
        ran.append("yes")

    producer_pool = await asyncpg.create_pool(
        roles.url(roles.producer), min_size=1, max_size=2
    )
    assert producer_pool is not None
    try:
        producer = Queue(producer_pool, name=COMPUTE_QUEUE, schema=SCHEMA)
        producer.register(
            name=probe, handler=handler, retry=RetryPolicy(max_attempts=1)
        )
        async with producer_pool.acquire() as connection:
            first = await producer.enqueue(
                connection,
                task=probe,
                payload={},
                dedupe_key="role-probe",
                on_conflict="return_existing",
            )
            # The second enqueue takes ON CONFLICT ... DO UPDATE SET
            # updated_at, which is why PRODUCE is granted that one column.
            second = await producer.enqueue(
                connection,
                task=probe,
                payload={},
                dedupe_key="role-probe",
                on_conflict="return_existing",
            )
    finally:
        await producer_pool.close()

    worker_pool = await asyncpg.create_pool(
        roles.url(roles.worker), min_size=1, max_size=6
    )
    assert worker_pool is not None
    try:
        consumer = Queue(worker_pool, name=COMPUTE_QUEUE, schema=SCHEMA)
        consumer.register(
            name=probe, handler=handler, retry=RetryPolicy(max_attempts=1)
        )
        await Worker(
            consumer, worker_id="role-probe-worker", concurrency=1, lease_duration=30.0
        ).drain(timeout=30)
    finally:
        await worker_pool.close()

    async with db.acquire() as connection:
        row = await connection.fetchrow(
            f"SELECT state, attempt FROM {SCHEMA}.jobs WHERE id = $1",  # noqa: S608
            first.id,
        )
        attempts = await connection.fetchval(
            f"SELECT count(*) FROM {SCHEMA}.job_attempts WHERE job_id = $1",  # noqa: S608
            first.id,
        )

    assert first.id == second.id
    assert ran == ["yes"]
    assert (row["state"], row["attempt"]) == ("succeeded", 1)
    assert attempts == 1


# ------------------------------------------------------------------ retention


@pytest.mark.asyncio
async def test_purge_is_refused_on_the_worker_role(queue: Queue, roles: Roles) -> None:
    """Why retention has a third role rather than riding on the worker's pool."""
    job_id = await _enqueue(queue)
    await _finish(job_id, age=JOB_RETENTION + timedelta(days=1))

    pool = await asyncpg.create_pool(roles.url(roles.worker), min_size=1, max_size=1)
    assert pool is not None
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await purge_finished_jobs(Admin(pool, schema=SCHEMA))
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_purge_removes_only_jobs_past_the_retention_window(
    queue: Queue, roles: Roles
) -> None:
    old = await _enqueue(queue)
    recent = await _enqueue(queue)
    pending = await _enqueue(queue)
    unreconciled = await _enqueue(queue)
    await _finish(old, age=JOB_RETENTION + timedelta(days=1))
    await _finish(recent, age=JOB_RETENTION - timedelta(days=1), state="failed")
    await _finish(
        unreconciled,
        age=JOB_RETENTION + timedelta(days=1),
        reconcile=False,
    )

    pool = await asyncpg.create_pool(roles.url(roles.purger), min_size=1, max_size=1)
    assert pool is not None
    try:
        removed = await purge_finished_jobs(Admin(pool, schema=SCHEMA))
    finally:
        await pool.close()

    async with db.acquire() as connection:
        remaining = {
            row["id"]
            for row in await connection.fetch(f"SELECT id FROM {SCHEMA}.jobs")  # noqa: S608
        }
        orphaned = await connection.fetchval(
            f"SELECT count(*) FROM {SCHEMA}.job_attempts WHERE job_id = $1",  # noqa: S608
            old,
        )
        kept_attempts = await connection.fetchval(
            f"SELECT count(*) FROM {SCHEMA}.job_attempts WHERE job_id = $1",  # noqa: S608
            recent,
        )

    assert removed == 1
    # The unfinished job is untouched however old it is; only terminal rows go.
    assert remaining == {recent, pending, unreconciled}
    assert orphaned == 0
    assert kept_attempts == 1
