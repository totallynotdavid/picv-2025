# tsdhn-api

`tsdhn-api` accepts requests from the web server, records job state in
PostgreSQL, queues work with Procrastinate, runs the shared `tsdhn` engine,
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

Create the compute and queue tables before starting the API or worker:

```sh
uv run tsdhn-compute-migrate
uv run tsdhn-procrastinate-migrate
```

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
- `api/core/tasks.py` runs queued simulations and records progress.
- `api/core/storage.py` uploads output files and creates download URLs.
- `api/core/procrastinate_app.py` defines the queue and scheduled cleanup work.
- `api/migrate.py`, `api/queue_migrate.py`, and `api/web_grants.py` apply the
  database changes described in `DEPLOY.md`.
- `api/worker.py` starts a worker for the configured queue.

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
