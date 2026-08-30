import { error } from "@sveltejs/kit";

import type { PageServerLoad } from "./$types";

export const load: PageServerLoad = async ({ locals }) => {
  const user = locals.user;
  if (!user) error(401);

  return { simulations: await locals.simulationRepository.listSimulations(user.id) };
};
