"""DDL for compute state."""

__all__ = ["COMPUTE_SCHEMA_SQL"]

COMPUTE_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS compute;

CREATE TABLE IF NOT EXISTS compute.jobs (
  id uuid PRIMARY KEY,
  simulation_id uuid UNIQUE NOT NULL,
  status text NOT NULL,
  input_params jsonb NOT NULL,
  details text,
  step text,
  step_index integer,
  total_steps integer,
  calculation jsonb,
  travel_times jsonb,
  outputs jsonb NOT NULL DEFAULT '[]'::jsonb,
  result_bucket text,
  result_key text,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz,
  -- Which task-queue attempt currently owns this row. Every write an attempt
  -- makes during its run carries its own number and matches on this column in
  -- the same statement, so a write from an attempt that has been superseded
  -- matches zero rows instead of racing the attempt that replaced it. NULL
  -- until the first attempt claims the row.
  owner_attempt integer
);

ALTER TABLE compute.jobs ADD COLUMN IF NOT EXISTS owner_attempt integer;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'compute' AND table_name = 'jobs'
      AND column_name = 'external_id'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'compute' AND table_name = 'jobs'
      AND column_name = 'simulation_id'
  ) THEN
    ALTER TABLE compute.jobs RENAME COLUMN external_id TO simulation_id;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'compute' AND table_name = 'jobs'
      AND column_name = 'artifacts'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'compute' AND table_name = 'jobs'
      AND column_name = 'outputs'
  ) THEN
    ALTER TABLE compute.jobs RENAME COLUMN artifacts TO outputs;
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'compute.jobs'::regclass
      AND conname = 'jobs_external_id_key'
  ) AND NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'compute.jobs'::regclass
      AND conname = 'jobs_simulation_id_key'
  ) THEN
    ALTER TABLE compute.jobs
      RENAME CONSTRAINT jobs_external_id_key TO jobs_simulation_id_key;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS jobs_status_idx ON compute.jobs(status);
CREATE INDEX IF NOT EXISTS jobs_created_at_idx ON compute.jobs(created_at DESC);
"""
