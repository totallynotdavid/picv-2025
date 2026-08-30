# TSDHN web

`apps/web` is the SvelteKit web app. It provides authentication, simulation
history, the input form, progress pages, and output downloads.

The browser talks to SvelteKit. Server code calls the FastAPI compute service
at `COMPUTE_API_URL` with `COMPUTE_API_TOKEN`. See
[`ARCHITECTURE.md`](../../ARCHITECTURE.md) for how the parts share data and
derive the state shown to researchers.

## Development

From the repository root:

```sh
bun install
bun --filter web dev
bun --filter web check
bun --filter web build
bun --filter web test
```

`bun --filter web test` is the fast Vitest suite. It does not need PostgreSQL,
the compute service, or MinIO. It tests route decisions and server behavior
without a database. PostgreSQL queries are tested by:

```sh
mise run test-integration
```

That task starts PostgreSQL, creates a temporary database, and runs the web
integration tests. It does not use the normal development database.

## Database

Web tables are declared in `src/lib/server/db/schema.ts`. Better Auth tables
are generated into `src/lib/server/db/auth.schema.ts`:

```sh
bun --filter web auth:schema
```

`src/lib/server/db/compute.ts` describes the columns read from `compute.jobs`.
It exists so Drizzle can join current compute state to a simulation. It is not
part of the web migration schema.

Run web migrations with a database administrator connection:

```sh
bun --filter web db:generate
bun --filter web db:migrate
```

The running app uses the restricted role created by the compute migration. See
[`DEPLOY.md`](../../DEPLOY.md) for the complete startup order and environment.

## Server modules

- `src/lib/server/compute-api.ts` builds the typed compute API client from
  `COMPUTE_API_URL` and `COMPUTE_API_TOKEN`. Both values stay on the server.
- `src/lib/server/submit-simulation.ts` submits a simulation. It records an
  error if the compute service rejects the request and clears that error after
  a successful retry.
- `src/lib/server/simulation-repository.ts` contains simulation queries and
  accepts the database connection to use.
- `src/hooks.server.ts` creates the production repository and puts it in
  `event.locals`.
- `src/lib/server/simulation-details.ts` joins the simulation record with its
  current compute status for pages.
- `src/lib/server/outputs.ts` checks requested output names against the files
  available for the simulation.
- The progress and output route handlers check the session and simulation
  ownership before calling the compute API.

For local schema work, `db:push` and `db:studio` are available. Use migrations
for a deployed database.
