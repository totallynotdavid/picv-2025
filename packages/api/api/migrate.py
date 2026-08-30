"""Applies the compute plane's schema and provisions the control plane's
database role.

Run once, as the database owner, after Procrastinate's own schema:

    procrastinate --app=api.core.procrastinate_app.app schema --apply
    tsdhn-compute-migrate
"""

import logging

import psycopg
from psycopg import sql

from api.core.schema import COMPUTE_SCHEMA_SQL
from api.core.settings import (
    APP_DB_PASSWORD,
    APP_DB_ROLE,
    COMPUTE_DATABASE_URL,
)

logger = logging.getLogger(__name__)


def install_compute_schema(conn: psycopg.Connection[tuple[str, ...]]) -> None:
    conn.execute(COMPUTE_SCHEMA_SQL)


def provision_app_role(conn: psycopg.Connection[tuple[str, ...]]) -> None:
    """Create (or re-password) the control plane's role and scope it.

    The role owns the `app` schema, so Drizzle can migrate the web app's
    own tables, and holds SELECT -- not INSERT, not UPDATE -- on
    compute.jobs. That grant *is* the plane boundary: the control plane
    reads live job state from the source of truth and cannot write it, and
    has no reach into Procrastinate's tables at all.

    The compute plane issues the grant because it owns the table being
    granted.
    """
    if not APP_DB_PASSWORD:
        raise RuntimeError(
            "APP_DB_PASSWORD must be set: it is the password for the "
            f"control plane's database role ({APP_DB_ROLE})."
        )

    role = sql.Identifier(APP_DB_ROLE)
    database = sql.Identifier(conn.info.dbname)
    exists = conn.execute(
        "SELECT 1 FROM pg_roles WHERE rolname = %s", [APP_DB_ROLE]
    ).fetchone()

    action = sql.SQL("ALTER ROLE") if exists else sql.SQL("CREATE ROLE")
    conn.execute(
        sql.SQL("{action} {role} LOGIN PASSWORD {password}").format(
            action=action, role=role, password=sql.Literal(APP_DB_PASSWORD)
        )
    )

    for statement in (
        sql.SQL("CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION {role}"),
        sql.SQL("GRANT CONNECT ON DATABASE {database} TO {role}"),
        sql.SQL("GRANT USAGE ON SCHEMA compute TO {role}"),
        sql.SQL("GRANT SELECT ON compute.jobs TO {role}"),
        sql.SQL("REVOKE ALL ON SCHEMA public FROM {role}"),
    ):
        conn.execute(statement.format(role=role, database=database))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    with psycopg.connect(COMPUTE_DATABASE_URL, connect_timeout=5) as conn:
        install_compute_schema(conn)
        provision_app_role(conn)
        conn.commit()
    logger.info("compute schema applied; role %s provisioned", APP_DB_ROLE)


if __name__ == "__main__":
    main()
