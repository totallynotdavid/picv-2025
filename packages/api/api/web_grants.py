"""Grant the runtime web role access to web-owned public tables."""

from __future__ import annotations

import logging

import psycopg
from psycopg import sql

from api.core.settings import APP_DB_ROLE, COMPUTE_DATABASE_URL

logger = logging.getLogger(__name__)


def grant_web_tables(conn: psycopg.Connection[tuple[str, ...]]) -> None:
    role = sql.Identifier(APP_DB_ROLE)
    migration_role = sql.Identifier(conn.info.user)
    for statement in (
        sql.SQL(
            "GRANT SELECT, INSERT, UPDATE, DELETE "
            "ON ALL TABLES IN SCHEMA public TO {role}"
        ),
        sql.SQL(
            "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {role}"
        ),
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {migration_role} "
            "IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}"
        ),
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {migration_role} "
            "IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {role}"
        ),
    ):
        conn.execute(statement.format(role=role, migration_role=migration_role))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    with psycopg.connect(COMPUTE_DATABASE_URL) as conn:
        grant_web_tables(conn)
        conn.commit()
    logger.info("web table privileges granted to %s", APP_DB_ROLE)


if __name__ == "__main__":
    main()
