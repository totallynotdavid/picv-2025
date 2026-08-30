import { error, redirect } from "@sveltejs/kit";

import { computeRequestConfig } from "$lib/server/compute-api";
import { assertOutputAccessible } from "$lib/server/outputs";

import type { RequestHandler } from "./$types";

export const GET: RequestHandler = async ({ params, locals, fetch }) => {
  if (!locals.user) error(401);

  const sim = await locals.simulationRepository.getSimulation(locals.user.id, params.id);
  assertOutputAccessible(sim, params.name);

  const { url, headers } = computeRequestConfig();
  const upstream = await fetch(
    `${url}/api/v1/jobs/${encodeURIComponent(sim.id)}/outputs/${encodeURIComponent(params.name)}`,
    { headers, redirect: "manual" },
  );

  const location = upstream.headers.get("location");
  if (upstream.status !== 307 || !location) {
    error(502, "No se pudo preparar la descarga.");
  }

  redirect(302, location);
};
