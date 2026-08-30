"""Idempotent DDL for the compute schema and the web role's read grant."""

__all__ = ["COMPUTE_SCHEMA_SQL"]

COMPUTE_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS compute;

CREATE TABLE IF NOT EXISTS compute.jobs (
  id uuid PRIMARY KEY,
  external_id uuid UNIQUE NOT NULL,
  status text NOT NULL,
  input_params jsonb NOT NULL,
  details text,
  step text,
  step_index integer,
  total_steps integer,
  calculation jsonb,
  travel_times jsonb,
  artifacts jsonb NOT NULL DEFAULT '[]'::jsonb,
  result_bucket text,
  result_key text,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz
);

CREATE INDEX IF NOT EXISTS jobs_status_idx ON compute.jobs(status);
CREATE INDEX IF NOT EXISTS jobs_created_at_idx ON compute.jobs(created_at DESC);
"""
