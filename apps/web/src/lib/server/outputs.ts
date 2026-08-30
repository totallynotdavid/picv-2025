import { error } from "@sveltejs/kit";

import type { SimulationDetails } from "$lib/server/simulation-details";

export function assertOutputAccessible(
  sim: SimulationDetails | undefined,
  name: string,
): asserts sim is SimulationDetails {
  if (!sim) error(404);
  if (!sim.outputs.includes(name)) {
    error(404, "Este resultado no está disponible.");
  }
}
