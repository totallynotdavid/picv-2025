import { fail, redirect } from "@sveltejs/kit";
import { message, superValidate } from "sveltekit-superforms";
import { zod4 } from "sveltekit-superforms/adapters";

import { defaultEarthquake, earthquakeSchema, toEarthquakeInput } from "$lib/schema/earthquake";
import { backend } from "$lib/server/api";
import { dispatchSimulation } from "$lib/server/dispatch";
import { createSimulation } from "$lib/server/simulations";

import type { Actions, PageServerLoad } from "./$types";

export const load: PageServerLoad = async () => {
  return { form: await superValidate(defaultEarthquake, zod4(earthquakeSchema)) };
};

export const actions: Actions = {
  default: async ({ request, locals, fetch }) => {
    const user = locals.user;
    if (!user) redirect(303, "/login");

    const form = await superValidate(request, zod4(earthquakeSchema));
    if (!form.valid) return fail(400, { form });

    const input = toEarthquakeInput(form.data);
    const appJobId = crypto.randomUUID();

    await createSimulation({
      id: appJobId,
      userId: user.id,
      params: input,
    });

    const client = backend(fetch);
    const dispatch = await dispatchSimulation({ id: appJobId, params: input }, client);
    if (!dispatch.ok) {
      return message(form, "No se pudo iniciar la simulación.", { status: 502 });
    }

    redirect(303, `/simulations/${appJobId}`);
  },
};
