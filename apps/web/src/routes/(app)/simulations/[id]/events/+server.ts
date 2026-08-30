import { error } from "@sveltejs/kit";

import { computeRequestConfig } from "$lib/server/compute-api";

import type { RequestHandler } from "./$types";

export const GET: RequestHandler = async ({ params, locals, fetch }) => {
  if (!locals.user) error(401);
  const sim = await locals.simulationRepository.getSimulation(locals.user.id, params.id);
  if (!sim) error(404);
  if (sim.status === "submitting" || sim.status === "submission_failed") {
    error(409, "La simulación aún no fue aceptada por el servicio de cálculo.");
  }

  const { url, headers } = computeRequestConfig();
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
