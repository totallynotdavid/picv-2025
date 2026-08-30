import { error, redirect } from "@sveltejs/kit";

import { backendRaw } from "$lib/server/api";
import { getSimulation } from "$lib/server/simulations";

import type { RequestHandler } from "./$types";

/** Check ownership before passing the compute redirect to object storage. */
export const GET: RequestHandler = async ({ params, locals, fetch }) => {
  if (!locals.user) error(401);

  const sim = await getSimulation(locals.user.id, params.id);
  if (!sim) error(404);
  if (!sim.artifacts.includes(params.name)) {
    error(404, "Este resultado no está disponible.");
  }

  const { url, headers } = backendRaw();
  const upstream = await fetch(
    `${url}/api/v1/jobs/${encodeURIComponent(sim.id)}/artifacts/${encodeURIComponent(params.name)}`,
    { headers, redirect: "manual" },
  );

  const location = upstream.headers.get("location");
  if (upstream.status !== 307 || !location) {
    error(502, "No se pudo preparar la descarga.");
  }

  redirect(302, location);
};
