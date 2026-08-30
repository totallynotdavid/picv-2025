# Architecture

This document explains what each component owns and how a simulation moves
through the system. Component READMEs explain how to work on each component.
[`DEPLOY.md`](./DEPLOY.md) explains how to run the services.

## System

```text
Browser
  |
  v
SvelteKit web app
  |-- users, sessions, and simulations in public
  |-- reads current jobs from compute.jobs
  |
  v
FastAPI compute service
  |-- compute.jobs and the Procrastinate queue
  |-- worker -> tsdhn engine -> MinIO
```

The browser talks to the web app. The web app checks the session and handles
the researcher-facing flow. Its server code calls the compute API at
`COMPUTE_API_URL` with `COMPUTE_API_TOKEN`. The browser never receives the
token and never calls the compute API directly.

The web app and compute service may use the same PostgreSQL server. Separate
schemas and database roles keep their writes independent.

## Responsibilities

### Web app

The web app owns:

- users, sessions, accounts, and verification records;
- `simulation_id`, user ID, submitted parameters, and creation time;
- failures that happen while submitting a simulation to the compute service;
- authentication, ownership checks, and user-facing responses;
- joining the simulation with current compute state for display.

The web app does not store compute progress, queue state, an internal compute
job ID, a compute-service selector, or output storage keys.

### Compute service

The compute service owns:

- the API used by the web server;
- `compute.jobs` and the Procrastinate queue tables;
- the internal compute job ID;
- job progress, retry state, and worker heartbeats;
- simulation work directories and checkpoints;
- output metadata and uploads to MinIO.

The compute service receives a `simulation_id` from the web app. It does not
know about web sessions, users, or passwords.

### Simulation engine

The `tsdhn` package owns the scientific calculation, pipeline order, run
directory, checkpoints, and output files. It has no dependency on web users,
PostgreSQL jobs, queues, or MinIO.

The engine preserves several numerical and file-format rules from the original
MATLAB and Fortran programs. Those rules are documented with the engine and
beside the code that implements them. Legacy behavior is compatibility
evidence; it is not treated as scientific validation without a source.

### Output storage

The worker may use local disk while a simulation is running. That work
directory contains intermediate files and checkpoints needed for recovery.

MinIO stores completed output files. The compute database stores their names,
media types, filenames, and private object keys. Public API responses omit the
object keys.

## Database ownership

The database owner runs migrations and owns all schemas and tables. Runtime
services use restricted roles.

The web app creates and writes only its tables in `public`. Its simulation
table contains:

```text
id
user_id
params
submission_error
created_at
```

The compute service creates and writes `compute.jobs` and the Procrastinate
queue tables. `compute.jobs.simulation_id` links a compute job to the web
simulation. The value is unique because repeating a submission must return the
same compute job.

The web runtime role can read and write the web tables and read
`compute.jobs`. It cannot change compute jobs, read queue tables, or run schema
changes. The table definition in `apps/web/src/lib/server/db/compute.ts` is
used only for reads and is excluded from web migrations.

## Identifiers

| Name | Owner | Purpose |
| --- | --- | --- |
| `simulation_id` | web app | Public simulation ID, used again when a submission is retried |
| internal job ID | compute service | Database and queue ID; never returned to the web app |
| output object key | compute service | Private MinIO location |

The public page is `/simulations/{simulation_id}`. The web app creates
`simulation_id` before calling the compute API and uses the same value for
every retry.

Repeating a request with the same `simulation_id` and input returns the
existing compute job. Reusing the ID with different input is rejected. A
researcher can therefore retry after a lost response without starting the
same simulation twice.

## Displayed state

The compute row is the current record once it exists. Before then, the web app
derives a short submission state from its own row:

```text
compute row exists                  use the compute job status
no compute row, submission error    submission_failed
no compute row, no error            submitting
```

A stale submission error never overrides an existing compute row. A successful
retry clears the saved submission error.

Compute jobs use these states:

```text
queued     waiting for a worker
running    executing the simulation
completed  output metadata and files were stored
failed     the simulation cannot continue
```

## Submit a simulation

1. The web app authenticates the user and validates the form.
2. It creates the simulation ID and saves the user input.
3. It sends the ID and input to the compute API.
4. The compute service creates the job and queue task in one database
   transaction, or returns the existing job for the same ID and input.
5. The browser opens the simulation page.

If the request fails before a compute row can be read, the web app saves a
submission error. The researcher can retry with the same `simulation_id`.

## Run a simulation

1. A worker claims the queue task.
2. It marks the compute job as running.
3. It runs the engine in `TSDHN_JOBS_DIR/{simulation_id}`.
4. Progress callbacks update the compute job and notify listeners.
5. The worker uploads completed output files and their metadata to MinIO.
6. It marks the job as completed only after storage succeeds.

## Show progress

The web app checks ownership, then reads the simulation and its compute row.
For live progress, it relays the compute API event stream to the browser. The
compute service sends the current state, listens for PostgreSQL notifications,
and closes the stream when the job finishes or the configured stream lifetime
ends.

## Download an output file

1. The browser asks the web app for an output name.
2. The web app checks the session, simulation ownership, and available names.
3. The compute API creates a short-lived MinIO URL.
4. The browser downloads the file directly from MinIO.

The web app and compute API do not relay output bytes.

## Failure and recovery

The compute service retries temporary failures in PostgreSQL, MinIO, or other
services. Invalid input, missing model files, and failed scientific steps do
not become more likely to succeed when repeated, so they fail the job.

The engine records enough state to continue valid completed work after a
retry. The compute service keeps the job in `compute.jobs` and reports the
final failure when retries are exhausted. Deployment settings determine retry
limits, worker recovery, storage, and cleanup.
