import { error, fail, redirect } from "@sveltejs/kit";

import { computeClient } from "$lib/server/compute-api";
import { submitSimulation } from "$lib/server/submit-simulation";

import type { Actions, PageServerLoad } from "./$types";

const RETRYABLE = new Set(["submitting", "submission_failed"]);

export const load: PageServerLoad = async ({ params, locals }) => {
  const user = locals.user;
  if (!user) error(401);

  const sim = await locals.simulationRepository.getSimulation(user.id, params.id);
  if (!sim) error(404, "Simulación no encontrada");

  return { sim };
};

export const actions: Actions = {
  retry: async ({ params, locals, fetch }) => {
    const user = locals.user;
    if (!user) error(401);

    const sim = await locals.simulationRepository.getSimulation(user.id, params.id);
    if (!sim) error(404, "Simulación no encontrada");

    if (!RETRYABLE.has(sim.status)) {
      return fail(400, { retryError: "Esta simulación ya no se puede reenviar." });
    }

    const client = computeClient(fetch);
    const submission = await submitSimulation(sim, client, locals.simulationRepository);
    if (!submission.ok) return fail(502, { retryError: submission.error });

    redirect(303, `/simulations/${sim.id}`);
  },
};
