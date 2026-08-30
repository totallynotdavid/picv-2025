# TSDHN web

`apps/web` is the SvelteKit control plane. It provides authentication,
simulation history, the input form, progress pages, and artifact downloads.

The browser calls SvelteKit only. Server code calls the FastAPI compute service
with `BACKEND_SERVICE_TOKEN`.

## Commands

From the repository root:

```sh
bun install
bun --filter web dev
bun --filter web check
bun --filter web build
```

Database commands:

```sh
bun --filter web db:generate
bun --filter web db:migrate
bun --filter web db:push
bun --filter web db:studio
```

The web database must be PostgreSQL. In the self-hosted stack, use the
`APP_DB_ROLE` connection created by `tsdhn-compute-migrate`.

## Environment

| Variable                | Purpose                                             |
| ----------------------- | --------------------------------------------------- |
| `DATABASE_URL`          | PostgreSQL URL for the web database role            |
| `ORIGIN`                | Public web origin used by SvelteKit and Better Auth |
| `BETTER_AUTH_SECRET`    | Better Auth session secret                          |
| `BACKEND_URL`           | FastAPI base URL                                    |
| `BACKEND_SERVICE_TOKEN` | Server-only bearer token for FastAPI                |

The service token must stay in server code. Do not create the API client in a
browser component.

For local Compose, `DATABASE_URL` uses the `tsdhn_app` role and the Postgres
database created by the stack:

```text
postgresql://tsdhn_app:<APP_DB_PASSWORD>@localhost:5432/tsdhn
```

## Data ownership

`src/lib/server/db/schema.ts` defines tables owned by the web app. Better Auth
tables are generated into `src/lib/server/db/auth.schema.ts`; regenerate them
with:

```sh
bun --filter web auth:schema
```

`src/lib/server/db/compute.ts` defines the read-only Drizzle view of
`compute.jobs`. The compute service owns that table and its migrations. The web
database role can read it but cannot change it.

The `simulation` row stores the user, input, dispatch state, and compute job
identifiers. `src/lib/server/simulations.ts` joins it with live compute state.
It does not copy status or artifact metadata into the web table.

## Server modules

- `src/lib/server/api.ts` creates the typed FastAPI client and keeps the token
  server-side.
- `src/lib/server/dispatch.ts` submits a simulation with its `app_job_id`.
- `src/lib/server/simulations.ts` checks ownership and reads the joined view.
- `src/routes/(app)/simulations/[id]/events/+server.ts` checks ownership before
  proxying the compute SSE stream.
- `src/routes/(app)/simulations/[id]/artifacts/[name]/+server.ts` checks
  ownership before passing through the compute redirect to MinIO.

## User flow

1. The web server validates the form and creates `app_job_id`.
2. It stores the simulation row before calling FastAPI.
3. FastAPI returns `compute_job_id` and queues the work.
4. The web server records the accepted dispatch.
5. The detail page reads live state from Postgres and opens the compute SSE
   stream.
6. Completed artifact links redirect to short-lived MinIO URLs.

The user can retry a dispatch that failed before the compute service accepted
the job. The same `app_job_id` makes that retry safe.
