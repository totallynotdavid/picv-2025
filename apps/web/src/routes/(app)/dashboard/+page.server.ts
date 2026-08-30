import { error } from "@sveltejs/kit";

import { listSimulations } from "$lib/server/simulations";

import type { PageServerLoad } from "./$types";

export const load: PageServerLoad = async ({ locals }) => {
  const user = locals.user;
  if (!user) error(401);

  return { simulations: await listSimulations(user.id) };
};
