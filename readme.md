# TSDHN

TSDHN runs tsunami simulations from earthquake source parameters.

The repository contains the Python simulation engine and researcher CLI, the
FastAPI compute service and worker, the SvelteKit web app, the generated
TypeScript client, and tools that compare the Python results with the older
MATLAB and Fortran programs.

## Get started

Install the pinned tools and project dependencies:

```sh
mise install
mise run install
mise run web-install
```

Run the researcher CLI without starting the services:

```sh
uv run tsdhn assets install
uv run tsdhn doctor
uv run tsdhn calc --mw 8.0 --lat -20.5 --lon -70.5
```

Create `.env`, set `COMPUTE_API_TOKEN`, `BETTER_AUTH_SECRET`, and
`APP_DB_PASSWORD`, then run the self-hosted stack:

```sh
cp .env.example .env
mise run dev-up
mise run dev-web
```

The web app is at <http://localhost:3000>. The API is at
<http://localhost:8000/api-docs>.

## Commands

| Command | Purpose |
| --- | --- |
| `mise run install` | Install Python dependencies |
| `mise run web-install` | Install the Bun workspace |
| `mise run dev-up` | Start the API, worker, Postgres, and MinIO |
| `mise run dev-web` | Start the web profile and web app |
| `mise run db-migrate` | Apply local database migrations |
| `mise run test` | Run the fast Python test suite |
| `mise run test-integration` | Run disposable PostgreSQL tests |
| `mise run web-test` | Run the fast web test suite |
| `mise run lint-all` | Run Python and JavaScript checks |
| `mise run gen-client` | Regenerate the OpenAPI client |
| `mise run test-golden` | Run the real pipeline regression |
| `mise run test-parity` | Compare Python output with the older programs |

The fast test suites do not need services. `mise run test-integration` starts
the project-local PostgreSQL cluster, creates disposable databases, runs the
database-backed tests, and removes those databases when it exits.

## Documentation

| Document | Use it for |
| --- | --- |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Responsibilities, database ownership, identifiers, displayed state, and request flows |
| [`DEPLOY.md`](./DEPLOY.md) | Compose deployment, configuration, and operations |
| [`packages/tsdhn`](./packages/tsdhn/readme.md) | Engine, CLI, model files, and simulation outputs |
| [`packages/api`](./packages/api/readme.md) | Compute API and worker development |
| [`apps/web`](./apps/web/readme.md) | SvelteKit development and server modules |
| [`libs/api-client`](./libs/api-client/readme.md) | Generated client and regeneration |
| [`packages/tsdhn-parity`](./packages/tsdhn-parity/readme.md) | Comparing Python results with MATLAB and Fortran results |

Start with the architecture document when changing a boundary. Start with a
component README when changing code inside one component.

## Repository layout

```text
apps/web/                 SvelteKit web app
deploy/                   Container images
libs/api-client/          Generated TypeScript client
packages/tsdhn/           Simulation engine and researcher CLI
packages/api/             FastAPI service and worker
packages/tsdhn-parity/    Legacy-output comparison tools
scripts/                  Setup, generation, database, and end-to-end tasks
docker-compose.yml        Self-hosted service stack
mise.toml                 Pinned tools and project tasks
```
