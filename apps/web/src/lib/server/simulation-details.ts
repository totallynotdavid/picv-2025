import type { StoredOutput } from "$lib/server/db/compute";

export type SimulationDetails = {
  id: string;
  userId: string;
  params: unknown;
  createdAt: Date;
  submissionError: string | null;
  status: string;
  details: string | null;
  step: string | null;
  stepIndex: number | null;
  totalSteps: number | null;
  calculation: unknown;
  travelTimes: unknown;
  error: string | null;
  outputs: string[];
  startedAt: Date | null;
  finishedAt: Date | null;
};

type SimulationDetailsRow = {
  id: unknown;
  userId: unknown;
  params: unknown;
  createdAt: unknown;
  submissionError: unknown;
  computeStatus: unknown;
  details: unknown;
  step: unknown;
  stepIndex: unknown;
  totalSteps: unknown;
  calculation: unknown;
  travelTimes: unknown;
  computeError: unknown;
  outputs: unknown;
  startedAt: unknown;
  finishedAt: unknown;
};

export function toSimulationDetails(row: SimulationDetailsRow): SimulationDetails {
  const computeStatus = row.computeStatus as string | null;
  const submissionError = row.submissionError as string | null;
  const outputs = (row.outputs as StoredOutput[] | null) ?? [];

  return {
    id: row.id as string,
    userId: row.userId as string,
    params: row.params,
    createdAt: row.createdAt as Date,
    submissionError,
    status: computeStatus ?? (submissionError ? "submission_failed" : "submitting"),
    details: row.details as string | null,
    step: row.step as string | null,
    stepIndex: row.stepIndex as number | null,
    totalSteps: row.totalSteps as number | null,
    calculation: row.calculation,
    travelTimes: row.travelTimes,
    error: (row.computeError as string | null) ?? submissionError,
    outputs: outputs.map((output) => output.name),
    startedAt: row.startedAt as Date | null,
    finishedAt: row.finishedAt as Date | null,
  };
}
