import { and, desc, eq } from "drizzle-orm";

import { db } from "$lib/server/db";
import { type ArtifactRef, computeJob } from "$lib/server/db/compute";
import { type NewSimulation, simulation } from "$lib/server/db/schema";

/** A web-owned simulation row joined with its live compute state. */
export type SimulationView = {
  id: string;
  userId: string;
  params: unknown;
  createdAt: Date;
  dispatchStatus: string;
  dispatchError: string | null;
  computeBackend: string | null;
  computeJobId: string | null;
  /** Live compute status, or the dispatch state before acceptance. */
  status: string;
  details: string | null;
  step: string | null;
  stepIndex: number | null;
  totalSteps: number | null;
  calculation: unknown;
  travelTimes: unknown;
  error: string | null;
  artifacts: string[];
  startedAt: Date | null;
  finishedAt: Date | null;
};

const SELECTION = {
  id: simulation.id,
  userId: simulation.userId,
  params: simulation.params,
  createdAt: simulation.createdAt,
  dispatchStatus: simulation.dispatchStatus,
  dispatchError: simulation.dispatchError,
  computeBackend: simulation.computeBackend,
  computeJobId: simulation.computeJobId,
  computeStatus: computeJob.status,
  details: computeJob.details,
  step: computeJob.step,
  stepIndex: computeJob.stepIndex,
  totalSteps: computeJob.totalSteps,
  calculation: computeJob.calculation,
  travelTimes: computeJob.travelTimes,
  computeError: computeJob.error,
  artifacts: computeJob.artifacts,
  startedAt: computeJob.startedAt,
  finishedAt: computeJob.finishedAt,
};

type Row = {
  [K in keyof typeof SELECTION]: unknown;
};

function toView(row: Row): SimulationView {
  const dispatchStatus = row.dispatchStatus as string;
  const computeStatus = row.computeStatus as string | null;
  const artifacts = (row.artifacts as ArtifactRef[] | null) ?? [];

  return {
    id: row.id as string,
    userId: row.userId as string,
    params: row.params,
    createdAt: row.createdAt as Date,
    dispatchStatus,
    dispatchError: row.dispatchError as string | null,
    computeBackend: row.computeBackend as string | null,
    computeJobId: row.computeJobId as string | null,
    // Before dispatch succeeds, there is no compute row to read.
    status: computeStatus ?? (dispatchStatus === "failed" ? "dispatch_failed" : "pending_dispatch"),
    details: row.details as string | null,
    step: row.step as string | null,
    stepIndex: row.stepIndex as number | null,
    totalSteps: row.totalSteps as number | null,
    calculation: row.calculation,
    travelTimes: row.travelTimes,
    error: (row.computeError as string | null) ?? (row.dispatchError as string | null),
    artifacts: artifacts.map((a) => a.name),
    startedAt: row.startedAt as Date | null,
    finishedAt: row.finishedAt as Date | null,
  };
}

export function createSimulation(data: NewSimulation): Promise<unknown> {
  return db.insert(simulation).values(data);
}

export function markDispatchAccepted(
  id: string,
  computeBackend: string,
  computeJobId: string,
): Promise<unknown> {
  return db
    .update(simulation)
    .set({
      dispatchStatus: "accepted",
      computeBackend,
      computeJobId,
      dispatchError: null,
      dispatchedAt: new Date(),
    })
    .where(eq(simulation.id, id));
}

export function markDispatchFailed(id: string, error: string): Promise<unknown> {
  return db
    .update(simulation)
    .set({ dispatchStatus: "failed", dispatchError: error })
    .where(eq(simulation.id, id));
}

export async function listSimulations(userId: string): Promise<SimulationView[]> {
  const rows = await db
    .select(SELECTION)
    .from(simulation)
    .leftJoin(computeJob, eq(computeJob.externalId, simulation.id))
    .where(eq(simulation.userId, userId))
    .orderBy(desc(simulation.createdAt));
  return rows.map(toView);
}

export async function getSimulation(
  userId: string,
  id: string,
): Promise<SimulationView | undefined> {
  const rows = await db
    .select(SELECTION)
    .from(simulation)
    .leftJoin(computeJob, eq(computeJob.externalId, simulation.id))
    .where(and(eq(simulation.id, id), eq(simulation.userId, userId)))
    .limit(1);
  return rows[0] ? toView(rows[0]) : undefined;
}
