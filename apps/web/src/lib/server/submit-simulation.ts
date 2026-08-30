import type { TsdhnClient } from "@tsdhn/api-client";

import type { EarthquakeInput } from "$lib/schema/earthquake";
import type { SimulationRepository } from "$lib/server/simulation-repository";

type SubmissionRepository = Pick<
  SimulationRepository,
  "clearSubmissionFailure" | "recordSubmissionFailure"
>;

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "No se pudo enviar la simulación al servicio de cálculo.";
}

export async function submitSimulation(
  sim: { id: string; params: unknown; submissionError?: string | null },
  client: TsdhnClient,
  repository: SubmissionRepository,
): Promise<{ ok: true } | { ok: false; error: string }> {
  let response: Awaited<ReturnType<TsdhnClient["POST"]>>;

  try {
    response = await client.POST("/api/v1/jobs", {
      body: {
        simulation_id: sim.id,
        input: sim.params as EarthquakeInput,
      },
    });
  } catch (error) {
    const message = errorMessage(error);
    await repository.recordSubmissionFailure(sim.id, message);
    return { ok: false, error: message };
  }

  const { data, error } = response;
  if (error || !data) {
    const message =
      typeof error === "object" && error && "detail" in error
        ? String(error.detail)
        : "No se pudo enviar la simulación al servicio de cálculo.";
    await repository.recordSubmissionFailure(sim.id, message);
    return { ok: false, error: message };
  }

  if (sim.submissionError) await repository.clearSubmissionFailure(sim.id);
  return { ok: true };
}
