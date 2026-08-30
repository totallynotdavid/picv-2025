import { error, fail, redirect } from "@sveltejs/kit";

import { backend } from "$lib/server/api";
import { dispatchSimulation } from "$lib/server/dispatch";
import { getSimulation } from "$lib/server/simulations";

import type { Actions, PageServerLoad } from "./$types";

const RETRYABLE = new Set(["pending_dispatch", "dispatch_failed"]);

export const load: PageServerLoad = async ({ params, locals }) => {
  const user = locals.user;
  if (!user) error(401);

  const sim = await getSimulation(user.id, params.id);
  if (!sim) error(404, "Simulación no encontrada");

  return { sim };
};

export const actions: Actions = {
  retry: async ({ params, locals, fetch }) => {
    const user = locals.user;
    if (!user) error(401);

    const sim = await getSimulation(user.id, params.id);
    if (!sim) error(404, "Simulación no encontrada");

    if (!RETRYABLE.has(sim.status)) {
      return fail(400, { retryError: "Esta simulación ya no se puede reenviar." });
    }

    const client = backend(fetch);
    const dispatch = await dispatchSimulation(sim, client, sim.computeBackend ?? undefined);
    if (!dispatch.ok) return fail(502, { retryError: dispatch.error });

    redirect(303, `/simulations/${sim.id}`);
  },
};
