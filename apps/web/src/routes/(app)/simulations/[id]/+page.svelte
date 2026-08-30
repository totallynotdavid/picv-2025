<script lang="ts">
  import { invalidateAll } from "$app/navigation";
  import type { components } from "@tsdhn/api-client";

  import type { EarthquakeInput } from "$lib/schema/earthquake";
  import SourceParams from "$lib/components/SourceParams.svelte";
  import Map from "$lib/components/Map.svelte";
  import Alert from "$lib/components/ui/Alert.svelte";
  import Button from "$lib/components/ui/Button.svelte";

  let { data, form } = $props();
  type Calculation = components["schemas"]["CalculationResponse"];
  type JobStatusResponse = {
    simulation_id: string;
    status: string;
    details: string | null;
    step: string | null;
    step_index: number | null;
    total_steps: number | null;
    calculation: Calculation | null;
    travel_times: unknown;
    error: string | null;
    finished_at: string | null;
    outputs: string[];
  };

  const params = $derived(data.sim.params as EarthquakeInput);
  const simulationId = $derived(data.sim.id);

  function statusFromSnapshot(): JobStatusResponse {
    return {
      simulation_id: data.sim.id,
      status: data.sim.status,
      details: data.sim.details,
      step: data.sim.step,
      step_index: data.sim.stepIndex,
      total_steps: data.sim.totalSteps,
      calculation: data.sim.calculation as Calculation | null,
      travel_times: data.sim.travelTimes,
      error: data.sim.error,
      finished_at: data.sim.finishedAt?.toISOString() ?? null,
      outputs: data.sim.outputs,
    };
  }

  const OUTPUT_LABEL: Record<string, string> = {
    max_height_map: "Mapa de altura máxima (PDF)",
    arrival_time_map: "Mapa de tiempos de arribo (PDF)",
    mareogram: "Mareograma (SVG)",
    calculation: "Parámetros de la fuente (JSON)",
    travel_times_json: "Tiempos de arribo (JSON)",
    travel_times_csv: "Tiempos de arribo (CSV)",
    input: "Parámetros de entrada (JSON)",
    runtime: "Entorno de ejecución (JSON)",
  };

  function isTerminal(status: string): boolean {
    return (
      status === "completed" ||
      status === "failed" ||
      status === "submission_failed" ||
      status === "cancelled"
    );
  }

  let live = $state<JobStatusResponse>(statusFromSnapshot());

  const terminal = $derived(isTerminal(live.status));
  const retryable = $derived(live.status === "submitting" || live.status === "submission_failed");
  const percent = $derived(
    live.step_index !== null && live.step_index !== undefined && live.total_steps
      ? Math.round((live.step_index / live.total_steps) * 100)
      : null,
  );

  const faultCorners = $derived(
    live.calculation?.rectangle_corners?.map((c) => ({ lat: c.lat, lon: c.lon })) ?? null,
  );

  const STATUS_LABEL: Record<string, string> = {
    submitting: "Enviando",
    submission_failed: "No enviada",
    queued: "En cola",
    running: "Ejecutándose",
    completed: "Completada",
    failed: "Fallida",
    cancelled: "Cancelada",
  };

  $effect(() => {
    const id = simulationId;
    const initial = statusFromSnapshot();
    live = initial;

    if (isTerminal(initial.status) || retryable) return;

    const es = new EventSource(`/simulations/${id}/events`);
    es.onmessage = (event) => {
      try {
        const next = JSON.parse(event.data) as JobStatusResponse;
        live = next;
        if (isTerminal(next.status)) {
          es.close();
          void invalidateAll();
        }
      } catch {
        // Keepalive frames are not JSON status updates.
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  });
</script>

<svelte:head><title>Simulación · TSDHN</title></svelte:head>

<div class="mb-6 flex items-center justify-between">
  <div>
    <a href="/dashboard" class="text-sm text-brand-600 hover:underline">← Mis simulaciones</a>
    <h1 class="mt-1 text-2xl font-bold text-neutral-900">
      Mw {params.Mw} · {params.lat0}, {params.lon0}
    </h1>
  </div>
  <span class="rounded-full bg-neutral-100 px-3 py-1 text-sm font-medium text-neutral-700">
    {STATUS_LABEL[live.status] ?? live.status}
  </span>
</div>

<div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
  <div class="space-y-6">
    {#if !terminal}
      <div class="rounded-xl border border-neutral-200 bg-white p-6">
        <div class="mb-3 flex items-center gap-3">
          <span class="size-3 animate-pulse rounded-full bg-brand-500"></span>
          <p class="font-medium text-neutral-900">{live.details ?? "Procesando…"}</p>
        </div>
        {#if percent !== null}
          <div class="h-2 w-full overflow-hidden rounded-full bg-neutral-100">
            <div class="h-full rounded-full bg-brand-500 transition-all" style="width: {percent}%"></div>
          </div>
          <p class="mt-2 text-sm text-neutral-500">
            Paso {live.step_index} de {live.total_steps}{live.step ? ` · ${live.step}` : ""}
          </p>
        {/if}
        <p class="mt-3 text-xs text-neutral-400">
          Esta simulación puede tardar alrededor de una hora. Puede cerrar esta página y volver
          más tarde.
        </p>
      </div>
    {/if}

    {#if live.status === "failed" || live.status === "submission_failed"}
      <Alert tone="error" title="La simulación falló">
        {live.error ?? "Error desconocido."}
      </Alert>
    {/if}

    {#if form?.retryError}
      <Alert tone="error" title="No se pudo reenviar">
        {form.retryError}
      </Alert>
    {/if}

    {#if retryable}
      <form method="POST" action="?/retry">
        <Button type="submit" variant="outline">Reenviar simulación</Button>
      </form>
    {/if}

    {#if live.calculation}
      <div class="rounded-xl border border-neutral-200 bg-white p-6">
        <h2 class="mb-3 text-lg font-semibold text-neutral-900">Parámetros de la fuente</h2>
        <SourceParams calculation={live.calculation} />
      </div>
    {/if}

    {#if live.status === "completed" && live.outputs.length > 0}
      <div class="rounded-xl border border-neutral-200 bg-white p-6">
        <h2 class="mb-3 text-lg font-semibold text-neutral-900">Resultados</h2>
        <ul class="space-y-2">
          {#each live.outputs as name (name)}
            <li>
              <a
                class="text-brand-600 hover:underline"
                href="/simulations/{simulationId}/outputs/{name}"
              >
                {OUTPUT_LABEL[name] ?? name}
              </a>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  </div>

  <div class="lg:sticky lg:top-6 lg:self-start">
    <Map lat={params.lat0} lon={params.lon0} {faultCorners} interactive={false} />
  </div>
</div>
