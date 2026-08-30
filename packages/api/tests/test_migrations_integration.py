"""Database-role behavior for the compute migration."""

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql

from api import migrate, queue_migrate, web_grants
from api.core.schema import COMPUTE_SCHEMA_SQL

pytestmark = pytest.mark.integration


@pytest.fixture
def temporary_web_role(
    isolated_database: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    role = f"tsdhn_test_{uuid.uuid4().hex[:16]}"
    monkeypatch.setattr(migrate, "APP_DB_ROLE", role)
    monkeypatch.setattr(migrate, "APP_DB_PASSWORD", "test-password")
    monkeypatch.setattr(web_grants, "APP_DB_ROLE", role)

    with psycopg.connect(isolated_database) as conn:
        conn.execute(COMPUTE_SCHEMA_SQL)
        migrate.provision_web_role(conn)
        conn.commit()

    yield role

    with psycopg.connect(isolated_database) as conn:
        role_identifier = sql.Identifier(role)
        conn.execute(sql.SQL("DROP OWNED BY {}").format(role_identifier))
        conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(role_identifier))
        conn.commit()


def test_provision_web_role_grants_only_the_runtime_boundary(
    isolated_database: str, temporary_web_role: str
) -> None:
    with psycopg.connect(isolated_database) as conn:
        privileges = conn.execute(
            """
            SELECT
                has_database_privilege(%s, current_database(), 'CONNECT'),
                has_database_privilege(%s, current_database(), 'CREATE'),
                has_schema_privilege(%s, 'public', 'CREATE'),
                has_schema_privilege(%s, 'compute', 'USAGE'),
                has_table_privilege(%s, 'compute.jobs', 'SELECT'),
                has_table_privilege(%s, 'compute.jobs', 'INSERT')
            """,
            [temporary_web_role] * 6,
        ).fetchone()

    assert privileges == (True, False, False, True, True, False)


def test_provision_web_role_repairs_compute_write_privileges(
    isolated_database: str, temporary_web_role: str
) -> None:
    with psycopg.connect(isolated_database) as conn:
        role = sql.Identifier(temporary_web_role)
        conn.execute(
            sql.SQL("GRANT INSERT, UPDATE, DELETE ON compute.jobs TO {} ").format(role)
        )
        conn.commit()

        migrate.provision_web_role(conn)
        conn.commit()

        privileges = conn.execute(
            """
            SELECT
                has_table_privilege(%s, 'compute.jobs', 'INSERT'),
                has_table_privilege(%s, 'compute.jobs', 'UPDATE'),
                has_table_privilege(%s, 'compute.jobs', 'DELETE')
            """,
            [temporary_web_role] * 3,
        ).fetchone()

    assert privileges == (False, False, False)


def test_provision_web_role_is_idempotent(
    isolated_database: str, temporary_web_role: str
) -> None:
    with psycopg.connect(isolated_database) as conn:
        migrate.provision_web_role(conn)
        conn.commit()
        exists = conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", [temporary_web_role]
        ).fetchone()

    assert exists is not None


def test_compute_migration_renames_old_job_columns(isolated_database: str) -> None:
    with psycopg.connect(isolated_database) as conn:
        conn.execute(
            "ALTER TABLE compute.jobs RENAME COLUMN simulation_id TO external_id"
        )
        conn.execute("ALTER TABLE compute.jobs RENAME COLUMN outputs TO artifacts")
        migrate.install_compute_schema(conn)
        columns = {
            row[0]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'compute' AND table_name = 'jobs'
                """
            ).fetchall()
        }

    assert "simulation_id" in columns
    assert "outputs" in columns
    assert "external_id" not in columns
    assert "artifacts" not in columns


def test_web_role_can_use_future_tables_but_cannot_run_ddl(
    isolated_database: str, temporary_web_role: str
) -> None:
    with psycopg.connect(isolated_database) as conn:
        conn.execute(
            "CREATE TABLE public.permission_probe "
            "(id integer PRIMARY KEY, value text NOT NULL)"
        )
        web_grants.grant_web_tables(conn)
        conn.commit()

    with psycopg.connect(
        isolated_database, user=temporary_web_role, password="test-password"
    ) as conn:
        conn.execute("INSERT INTO public.permission_probe VALUES (1, 'before')")
        conn.execute("UPDATE public.permission_probe SET value = 'after' WHERE id = 1")
        value = conn.execute(
            "SELECT value FROM public.permission_probe WHERE id = 1"
        ).fetchone()
        conn.execute("DELETE FROM public.permission_probe WHERE id = 1")
        conn.commit()

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("CREATE TABLE public.forbidden (id integer)")

    assert value == ("after",)


def test_provision_web_role_transfers_legacy_table_ownership(
    isolated_database: str, temporary_web_role: str
) -> None:
    with psycopg.connect(isolated_database) as conn:
        migration_user = conn.info.user
        role = sql.Identifier(temporary_web_role)
        conn.execute("CREATE TABLE public.legacy_probe (id integer PRIMARY KEY)")
        conn.execute(
            sql.SQL("ALTER TABLE public.legacy_probe OWNER TO {} ").format(role)
        )
        conn.commit()

        migrate.provision_web_role(conn)
        conn.commit()

        owner = conn.execute(
            "SELECT pg_get_userbyid(c.relowner) FROM pg_class AS c "
            "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'legacy_probe'"
        ).fetchone()

    with (
        psycopg.connect(
            isolated_database, user=temporary_web_role, password="test-password"
        ) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute("ALTER TABLE public.legacy_probe ADD COLUMN forbidden text")

    assert owner == (migration_user,)


def test_procrastinate_schema_migration_is_repeatable(isolated_database: str) -> None:
    queue_migrate.apply_schema(isolated_database)
    queue_migrate.apply_schema(isolated_database)

    with psycopg.connect(isolated_database) as conn:
        assert all(queue_migrate.queue_schema_state(conn))


def test_web_role_cannot_read_compute_queue_tables(
    isolated_database: str, temporary_web_role: str
) -> None:
    with psycopg.connect(isolated_database) as conn:
        web_grants.grant_web_tables(conn)
        conn.commit()
    queue_migrate.apply_schema(isolated_database)

    with (
        psycopg.connect(
            isolated_database, user=temporary_web_role, password="test-password"
        ) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute("SELECT 1 FROM compute.procrastinate_jobs")
