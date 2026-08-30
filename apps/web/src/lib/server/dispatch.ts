import type { TsdhnClient } from "@tsdhn/api-client";

import type { EarthquakeInput } from "$lib/schema/earthquake";
import { markDispatchAccepted, markDispatchFailed } from "$lib/server/simulations";

const DEFAULT_COMPUTE_BACKEND = "default";

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "No se pudo iniciar la simulación en el backend.";
}

export async function dispatchSimulation(
  sim: { id: string; params: unknown },
  client: TsdhnClient,
  computeBackend = DEFAULT_COMPUTE_BACKEND,
): Promise<{ ok: true; computeJobId: string } | { ok: false; error: string }> {
  try {
    const { data, error } = await client.POST("/api/v1/jobs", {
      body: {
        app_job_id: sim.id,
        input: sim.params as EarthquakeInput,
      },
    });

    if (error || !data) {
      const message =
        typeof error === "object" && error && "detail" in error
          ? String(error.detail)
          : "No se pudo iniciar la simulación en el backend.";
      await markDispatchFailed(sim.id, message);
      return { ok: false, error: message };
    }

    await markDispatchAccepted(sim.id, computeBackend, data.compute_job_id);
    return { ok: true, computeJobId: data.compute_job_id };
  } catch (error) {
    const message = errorMessage(error);
    await markDispatchFailed(sim.id, message);
    return { ok: false, error: message };
  }
}
