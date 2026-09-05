# tsdhn-api

`tsdhn-api` accepts requests from the web server, records job state in
PostgreSQL, queues work with `rqueue`, runs the shared `tsdhn` engine,
and stores output files in MinIO.

The browser does not call this service. The web app calls it with
`COMPUTE_API_TOKEN`. See [`ARCHITECTURE.md`](../../ARCHITECTURE.md) for service
responsibilities and [`DEPLOY.md`](../../DEPLOY.md) for configuration,
migrations, storage, and worker resources.

## Commands

Run the service and worker from the repository root:

```sh
uv run tsdhn-api
uv run tsdhn-worker
```

Create the compute and queue tables before starting the API or worker.
`tsdhn-compute-migrate` also provisions the web application's database role, so
it needs a password for that role; there is no default, because a default
password is worse than an error:

```sh
export APP_DB_PASSWORD="$(openssl rand -hex 32)"   # or set it in .env

uv run tsdhn-compute-migrate
uv run rqueue \
  --database-url "${COMPUTE_DATABASE_URL:-postgresql://tsdhn:tsdhn@localhost:5432/tsdhn}" \
  --schema "${COMPUTE_QUEUE_SCHEMA:-task_queue}" \
  migrate
```

Everything else defaults to the values `api/core/settings.py` uses, so with
`APP_DB_PASSWORD` set the block works on a fresh clone with nothing else
exported. `rqueue`'s CLI reads `RQUEUE_DATABASE_URL`, not
`COMPUTE_DATABASE_URL`, which is why the URL is passed explicitly.

`rqueue` owns the queue tables and their migrations; `--schema` is a global
flag, before the subcommand. They live in `COMPUTE_QUEUE_SCHEMA` (default
`task_queue`), never in `compute`.

For a complete deployment, including web migrations and grants, follow
[`DEPLOY.md`](../../DEPLOY.md). For local PostgreSQL, `mise run db-migrate`
applies every database change. `mise run test-integration` creates disposable
databases and runs the database-backed tests.

## API definition

The OpenAPI UI at <http://127.0.0.1:8000/api-docs> is the current list of
routes, inputs, and responses. Health and version checks are public. Simulation
and calculation routes require `COMPUTE_API_TOKEN`.

The API accepts `simulation_id` as the web app's identifier. Repeating a
submission with the same ID and input returns the existing job. Output
responses expose output names and filenames, while storage keys remain private.
See [`ARCHITECTURE.md`](../../ARCHITECTURE.md) for the full submission and
download flows.

## Package map

- `api/routes.py` defines health, calculation, submission, progress, and output
  routes.
- `api/schemas.py` defines public request and response models.
- `api/security.py` checks `COMPUTE_API_TOKEN`.
- `api/core/repository.py` reads and updates compute jobs.
- `api/core/tasks.py` registers and runs the queued simulation task.
- `api/core/storage.py` uploads output files and creates download URLs.
- `api/core/queue.py` holds the `rqueue.Queue` the API and worker share.
- `api/core/db.py` owns the process-wide asyncpg pool.
- `api/migrate.py` and `api/web_grants.py` apply the database changes described
  in `DEPLOY.md`; `rqueue migrate` applies the queue's own.
- `api/worker.py` starts an `rqueue.Worker` for the configured queue and the
  periodic workspace sweep.

## Tests

Run the fast API tests with:

```sh
uv run --package tsdhn-api pytest packages/api/tests
uv run --package tsdhn-api pytest packages/api/tests/test_api.py::test_version
```

The integration tests use PostgreSQL and disposable databases:

```sh
mise run test-integration
```

## Generated client

After changing `api/routes.py` or `api/schemas.py`, regenerate the TypeScript
client:

```sh
mise run gen-client
```

The generation command exports OpenAPI from the running application code. Do
not edit the exported schema or generated TypeScript by hand.
