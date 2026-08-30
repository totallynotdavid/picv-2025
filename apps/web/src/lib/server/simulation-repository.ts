import { and, desc, eq } from "drizzle-orm";
import type { PostgresJsDatabase } from "drizzle-orm/postgres-js";

import { computeJob } from "$lib/server/db/compute";
import * as schema from "$lib/server/db/schema";
import { type NewSimulation, simulation } from "$lib/server/db/schema";
import { type SimulationDetails, toSimulationDetails } from "$lib/server/simulation-details";

export type SimulationDatabase = PostgresJsDatabase<typeof schema>;

export type SimulationRepository = ReturnType<typeof createSimulationRepository>;

const simulationDetailsSelection = {
  id: simulation.id,
  userId: simulation.userId,
  params: simulation.params,
  createdAt: simulation.createdAt,
  submissionError: simulation.submissionError,
  computeStatus: computeJob.status,
  details: computeJob.details,
  step: computeJob.step,
  stepIndex: computeJob.stepIndex,
  totalSteps: computeJob.totalSteps,
  calculation: computeJob.calculation,
  travelTimes: computeJob.travelTimes,
  computeError: computeJob.error,
  outputs: computeJob.outputs,
  startedAt: computeJob.startedAt,
  finishedAt: computeJob.finishedAt,
};

export function createSimulationRepository(database: SimulationDatabase) {
  return {
    async createSimulation(data: NewSimulation): Promise<void> {
      await database.insert(simulation).values(data);
    },

    async clearSubmissionFailure(id: string): Promise<void> {
      await database.update(simulation).set({ submissionError: null }).where(eq(simulation.id, id));
    },

    async recordSubmissionFailure(id: string, error: string): Promise<void> {
      await database
        .update(simulation)
        .set({ submissionError: error })
        .where(eq(simulation.id, id));
    },

    async listSimulations(userId: string): Promise<SimulationDetails[]> {
      const rows = await database
        .select(simulationDetailsSelection)
        .from(simulation)
        .leftJoin(computeJob, eq(computeJob.simulationId, simulation.id))
        .where(eq(simulation.userId, userId))
        .orderBy(desc(simulation.createdAt));
      return rows.map(toSimulationDetails);
    },

    async getSimulation(userId: string, id: string): Promise<SimulationDetails | undefined> {
      const rows = await database
        .select(simulationDetailsSelection)
        .from(simulation)
        .leftJoin(computeJob, eq(computeJob.simulationId, simulation.id))
        .where(and(eq(simulation.id, id), eq(simulation.userId, userId)))
        .limit(1);
      return rows[0] ? toSimulationDetails(rows[0]) : undefined;
    },
  };
}
