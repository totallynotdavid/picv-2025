"""Apply the vendor queue schema once and make the operation repeatable."""

from __future__ import annotations

import logging

import procrastinate
import psycopg
from psycopg import sql

from api.core.settings import (
    COMPUTE_DATABASE_URL,
    PROCRASTINATE_SCHEMA,
    PROCRASTINATE_SEARCH_PATH,
)

logger = logging.getLogger(__name__)


def queue_schema_state(
    conn: psycopg.Connection[tuple[str, ...]], schema: str = PROCRASTINATE_SCHEMA
) -> tuple[bool, ...]:
    """Return whether the required Procrastinate types and tables exist."""
    result = conn.execute(
        """
        SELECT
            to_regtype(%s) IS NOT NULL,
            to_regtype(%s) IS NOT NULL,
            to_regtype(%s) IS NOT NULL,
            to_regclass(%s) IS NOT NULL,
            to_regclass(%s) IS NOT NULL,
            to_regclass(%s) IS NOT NULL,
            to_regclass(%s) IS NOT NULL
        """,
        [
            f"{schema}.procrastinate_job_status",
            f"{schema}.procrastinate_job_event_type",
            f"{schema}.procrastinate_job_to_defer_v1",
            f"{schema}.procrastinate_workers",
            f"{schema}.procrastinate_jobs",
            f"{schema}.procrastinate_periodic_defers",
            f"{schema}.procrastinate_events",
        ],
    ).fetchone()
    if result is None:
        raise RuntimeError("failed to inspect the Procrastinate schema")
    return tuple(bool(value) for value in result)


def move_legacy_schema(conn: psycopg.Connection[tuple[str, ...]]) -> None:
    """Move a pre-compute-schema Procrastinate install into `compute`."""
    for type_name in (
        "procrastinate_job_status",
        "procrastinate_job_event_type",
        "procrastinate_job_to_defer_v1",
    ):
        conn.execute(
            sql.SQL("ALTER TYPE public.{name} SET SCHEMA compute").format(
                name=sql.Identifier(type_name)
            )
        )

    objects = conn.execute(
        """
        SELECT c.relname, c.relkind
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname LIKE 'procrastinate_%'
          AND c.relkind IN ('r', 'p')
        """
    ).fetchall()
    for name, _kind in objects:
        conn.execute(
            sql.SQL("ALTER TABLE public.{name} SET SCHEMA compute").format(
                name=sql.Identifier(name)
            )
        )

    sequences = conn.execute(
        """
        SELECT sequence.relname, table_.relname, column_.attname
        FROM pg_class AS sequence
        JOIN pg_namespace AS sequence_schema
          ON sequence_schema.oid = sequence.relnamespace
        JOIN pg_depend AS dependency
          ON dependency.classid = 'pg_class'::regclass
         AND dependency.objid = sequence.oid
         AND dependency.deptype = 'a'
        JOIN pg_class AS table_ ON table_.oid = dependency.refobjid
        JOIN pg_namespace AS table_schema
          ON table_schema.oid = table_.relnamespace
        JOIN pg_attribute AS column_
          ON column_.attrelid = table_.oid
         AND column_.attnum = dependency.refobjsubid
        WHERE sequence_schema.nspname = 'public'
          AND sequence.relkind = 'S'
          AND table_schema.nspname = 'compute'
        """
    ).fetchall()
    for sequence_name, table_name, column_name in sequences:
        sequence_identifier = sql.Identifier(sequence_name)
        conn.execute(
            sql.SQL("ALTER SEQUENCE public.{name} OWNED BY NONE").format(
                name=sequence_identifier
            )
        )
        conn.execute(
            sql.SQL("ALTER SEQUENCE public.{name} SET SCHEMA compute").format(
                name=sequence_identifier
            )
        )
        conn.execute(
            sql.SQL(
                "ALTER SEQUENCE compute.{sequence_name} "
                "OWNED BY compute.{table_name}.{column_name}"
            ).format(
                sequence_name=sequence_identifier,
                table_name=sql.Identifier(table_name),
                column_name=sql.Identifier(column_name),
            )
        )

    conn.execute(
        """
        DO $$
        DECLARE function_record record;
        BEGIN
            FOR function_record IN
                SELECT p.proname, pg_get_function_identity_arguments(p.oid) AS arguments
                FROM pg_proc AS p
                JOIN pg_namespace AS n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public' AND p.proname LIKE 'procrastinate_%'
            LOOP
                EXECUTE format(
                    'ALTER FUNCTION public.%I(%s) SET SCHEMA compute',
                    function_record.proname,
                    function_record.arguments
                );
            END LOOP;
        END $$;
        """
    )


def apply_schema(conninfo: str) -> None:
    """Apply Procrastinate's schema in `compute`, rejecting partial installs."""
    with psycopg.connect(conninfo) as conn:
        state = queue_schema_state(conn)
        legacy_state = queue_schema_state(conn, "public")

    if all(state):
        logger.info("Procrastinate schema already applied")
        return
    if all(legacy_state):
        with psycopg.connect(conninfo) as conn:
            move_legacy_schema(conn)
            if not all(queue_schema_state(conn)):
                raise RuntimeError("failed to move the Procrastinate schema to compute")
            conn.commit()
        logger.info("Procrastinate schema moved from public to compute")
        return
    if any(state):
        raise RuntimeError(
            "partial Procrastinate schema in compute; repair it before retrying"
        )
    if any(legacy_state):
        raise RuntimeError(
            "partial Procrastinate schema in public; repair it before retrying"
        )

    connector = procrastinate.PsycopgConnector(
        conninfo=conninfo,
        kwargs={"options": f"-c search_path={PROCRASTINATE_SEARCH_PATH}"},
    )
    sync_connector = connector.get_sync_connector()
    sync_connector.open()
    try:
        schema_manager = procrastinate.App(connector=connector).schema_manager
        schema_manager.apply_schema()
    finally:
        sync_connector.close()
    logger.info("Procrastinate schema applied")


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    apply_schema(COMPUTE_DATABASE_URL)


if __name__ == "__main__":  # pragma: no cover
    main()
