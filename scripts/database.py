"""Create and remove disposable PostgreSQL databases for test tasks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from urllib.parse import SplitResult, quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql


@dataclass(frozen=True)
class DatabaseTarget:
    """An administrative connection and a connection to one database."""

    name: str
    maintenance_url: str
    database_url: str


def _netloc(parts: SplitResult, user: str | None, password: str | None) -> str:
    hostname = parts.hostname
    if hostname is None:
        raise ValueError("database URL must include a hostname")
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"

    port = parts.port
    host = f"{hostname}:{port}" if port is not None else hostname
    if user is None and password is None:
        return parts.netloc

    credentials = quote(user or "", safe="")
    if password is not None:
        credentials += f":{quote(password, safe='')}"
    return f"{credentials}@{host}"


def database_target(
    base_url: str,
    name: str,
    *,
    user: str | None = None,
    password: str | None = None,
) -> DatabaseTarget:
    """Build maintenance and target URLs without interpolating SQL values."""
    parts = urlsplit(base_url)
    maintenance_url = urlunsplit(parts._replace(path="/postgres"))
    database_url = urlunsplit(
        parts._replace(
            netloc=_netloc(parts, user, password),
            path=f"/{name}",
        )
    )
    return DatabaseTarget(name, maintenance_url, database_url)


def create_database(base_url: str, name: str) -> DatabaseTarget:
    """Create a database from a privileged maintenance connection."""
    target = database_target(base_url, name)
    with psycopg.connect(target.maintenance_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target.name))
        )
    return target


def drop_database(base_url: str, name: str) -> None:
    """Drop a disposable database, terminating any test connections first."""
    target = database_target(base_url, name)
    with psycopg.connect(target.maintenance_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(target.name)
            )
        )


def drop_role(base_url: str, role: str) -> None:
    """Remove a role created for an isolated integration run.

    Cleanup also runs when provisioning failed before the role was created;
    ``DROP OWNED BY`` has no ``IF EXISTS`` form.
    """
    target = database_target(base_url, role)
    with psycopg.connect(target.maintenance_url, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", [role]
        ).fetchone()
        if exists is None:
            return
        identifier = sql.Identifier(role)
        connection.execute(sql.SQL("DROP OWNED BY {}").format(identifier))
        connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(identifier))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--base-url", required=True)
    create.add_argument("--name", required=True)

    url = subparsers.add_parser("url")
    url.add_argument("--base-url", required=True)
    url.add_argument("--name", required=True)
    url.add_argument("--user", required=True)
    url.add_argument("--password", required=True)

    drop = subparsers.add_parser("drop")
    drop.add_argument("--base-url", required=True)
    drop.add_argument("--name", required=True)
    drop.add_argument("--role", action="append", default=[])

    args = parser.parse_args()
    if args.command == "create":
        print(create_database(args.base_url, args.name).database_url)
    elif args.command == "url":
        print(
            database_target(
                args.base_url,
                args.name,
                user=args.user,
                password=args.password,
            ).database_url
        )
    else:
        drop_database(args.base_url, args.name)
        for role in args.role:
            drop_role(args.base_url, role)


if __name__ == "__main__":
    main()
