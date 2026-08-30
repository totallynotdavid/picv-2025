# tsdhn-api

`tsdhn-api` is the compute service. It accepts trusted requests from the web
server, records job state in Postgres, queues work with Procrastinate, runs the
shared `tsdhn` engine, and stores completed artifacts in MinIO.

The browser must not call this service directly. The SvelteKit server adds the
service token to each request.

## Commands

Run the API, worker, and migrations from the repository root:

```sh
uv run tsdhn-api
uv run tsdhn-worker
uv run tsdhn-compute-migrate
```

The API listens on `127.0.0.1:8000` by default. The OpenAPI UI is at
`/api-docs`.

Before starting the worker, apply the compute schema and Procrastinate schema:

```sh
uv run tsdhn-compute-migrate
uv run procrastinate --app=api.core.procrastinate_app.app schema --apply
```

`tsdhn-compute-migrate` needs a database-owner connection and
`APP_DB_PASSWORD`. It creates or updates the web role, grants it `SELECT` on
`compute.jobs`, and does not grant it access to the queue tables.

## Configuration

| Variable | Used by | Default | Purpose |
| --- | --- | --- | --- |
| `APP_HOST` | API | `127.0.0.1` | Bind host |
| `APP_PORT` | API | `8000` | Bind port |
| `TSDHN_LOG_LEVEL` | API, worker | `INFO` | Log level |
| `BACKEND_SERVICE_TOKEN` | API | none | Bearer token for data routes |
| `ALLOWED_ORIGINS` | API | empty | Optional direct browser origins |
| `COMPUTE_DATABASE_URL` | API, worker, migration | `postgresql://tsdhn:tsdhn@localhost:5432/tsdhn` | Compute Postgres URL |
| `APP_DB_ROLE` | migration | `tsdhn_app` | Web database role |
| `APP_DB_PASSWORD` | migration | none | Web database role password |
| `DB_POOL_MIN_SIZE` | API | `1` | Minimum API read-pool size |
| `DB_POOL_MAX_SIZE` | API | `10` | Maximum API read-pool size |
| `PROCRASTINATE_QUEUE` | API, worker | `simulations` | Queue name |
| `MINIO_ENDPOINT` | API, worker | `localhost:9000` | Internal MinIO endpoint |
| `MINIO_PUBLIC_ENDPOINT` | API | `MINIO_ENDPOINT` | Browser-reachable MinIO endpoint |
| `MINIO_ACCESS_KEY` | API, worker | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | API, worker | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | API, worker | `tsdhn-results` | Artifact bucket |
| `MINIO_SECURE` | API, worker | `false` | Use HTTPS for MinIO |
| `ARTIFACT_URL_TTL_SECONDS` | API | `900` | Presigned URL lifetime |
| `SSE_MAX_DURATION_SECONDS` | API | `1800` | Maximum progress-stream lifetime |
| `TSDHN_MODEL_DIR` | API, worker | none | Model dataset directory |
| `TSDHN_JOBS_DIR` | worker | `jobs` | Temporary workspace root |
| `TSDHN_NUMBA_THREADS` | worker | unset | Per-worker thread limit |

The worker also needs `gmt` and `ttt_client` on `PATH`. The API image includes
the model data and these tools.

## Routes

Health and version are public. All other routes require the service token.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Report Postgres and MinIO readiness |
| `GET` | `/api/v1/version` | Report the API version |
| `POST` | `/api/v1/calculations` | Calculate source parameters and arrival times |
| `POST` | `/api/v1/jobs` | Create or return an idempotent simulation job |
| `GET` | `/api/v1/jobs/{app_job_id}` | Read current job state and artifact names |
| `GET` | `/api/v1/jobs/{app_job_id}/artifacts` | List completed artifacts |
| `GET` | `/api/v1/jobs/{app_job_id}/artifacts/{name}` | Redirect to a presigned artifact URL |
| `GET` | `/api/v1/jobs/{app_job_id}/events` | Stream job progress as SSE |

`POST /api/v1/jobs` accepts the web app's `app_job_id`. The compute plane
stores it as the unique `external_id`, creates `compute_job_id`, and inserts
the database row and queue task in one transaction. Repeating the request with
the same input returns the existing job. Reusing the id with different input
returns `400`.

The worker publishes progress in `compute.jobs`. The events route reads the
initial state, listens on the job's Postgres notification channel, and sends a
keepalive while the job is quiet. It ends when the job reaches a terminal state
or the stream lifetime expires.

Artifacts are stored under `simulations/{app_job_id}/`. The API returns a
short-lived redirect to MinIO. Report bytes do not pass through FastAPI or the
web server.

## Tests and client generation

```sh
uv run --package tsdhn-api pytest packages/api/tests
uv run --package tsdhn-api pytest packages/api/tests/test_api.py::test_version
```

Apply the full local stack with:

```sh
mise run db-migrate
```

After changing API schemas or routes, regenerate the TypeScript client:

```sh
bun run gen:client
```
