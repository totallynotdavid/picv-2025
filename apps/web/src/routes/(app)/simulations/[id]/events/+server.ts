import { error } from "@sveltejs/kit";

import { backendRaw } from "$lib/server/api";
import { getSimulation } from "$lib/server/simulations";

import type { RequestHandler } from "./$types";

/** Check ownership before proxying the compute progress stream. */
export const GET: RequestHandler = async ({ params, locals, fetch }) => {
  if (!locals.user) error(401);
  const sim = await getSimulation(locals.user.id, params.id);
  if (!sim) error(404);
  if (!sim.computeJobId) error(409, "La simulación aún no fue aceptada por el backend.");

  const { url, headers } = backendRaw();
  const upstream = await fetch(`${url}/api/v1/jobs/${encodeURIComponent(sim.id)}/events`, {
    headers,
  });
  if (!upstream.ok || !upstream.body) error(502, "No hay flujo de progreso disponible.");

  return new Response(upstream.body, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    },
  });
};
