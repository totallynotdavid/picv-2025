<script lang="ts">
  import type { EarthquakeInput } from "$lib/schema/earthquake";
  import Button from "$lib/components/ui/Button.svelte";

  let { data } = $props();

  const STATUS: Record<string, { label: string; class: string }> = {
    submitting: { label: "Enviando", class: "bg-neutral-100 text-neutral-600" },
    submission_failed: { label: "No enviada", class: "bg-red-100 text-red-700" },
    queued: { label: "En cola", class: "bg-neutral-100 text-neutral-600" },
    running: { label: "Ejecutándose", class: "bg-brand-100 text-brand-700" },
    completed: { label: "Completada", class: "bg-green-100 text-green-700" },
    failed: { label: "Fallida", class: "bg-red-100 text-red-700" },
    cancelled: { label: "Cancelada", class: "bg-neutral-100 text-neutral-600" },
  };

  function badge(status: string) {
    return STATUS[status] ?? { label: status, class: "bg-neutral-100 text-neutral-600" };
  }

  function fmt(ms: Date) {
    return new Date(ms).toLocaleString("es-PE", { dateStyle: "medium", timeStyle: "short" });
  }
</script>

<svelte:head><title>Mis simulaciones · TSDHN</title></svelte:head>

<div class="mb-6 flex items-center justify-between">
  <h1 class="text-2xl font-bold text-neutral-900">Mis simulaciones</h1>
  <a href="/new"><Button>Nueva simulación</Button></a>
</div>

{#if data.simulations.length === 0}
  <div class="rounded-xl border border-dashed border-neutral-300 bg-white p-12 text-center">
    <p class="text-neutral-500">Aún no has iniciado ninguna simulación.</p>
    <a href="/new" class="mt-3 inline-block font-medium text-brand-600 hover:underline">
      Crear la primera →
    </a>
  </div>
{:else}
  <ul class="space-y-3">
    {#each data.simulations as sim (sim.id)}
      {@const p = sim.params as EarthquakeInput}
      {@const b = badge(sim.status)}
      <li>
        <a
          href="/simulations/{sim.id}"
          class="flex items-center justify-between rounded-xl border border-neutral-200 bg-white p-4 transition hover:border-brand-300 hover:shadow-sm"
        >
          <div class="space-y-1">
            <p class="font-medium text-neutral-900">
              Mw {p.Mw} · {p.lat0}, {p.lon0}
            </p>
            <p class="text-sm text-neutral-500">{fmt(sim.createdAt)}</p>
          </div>
          <span class="rounded-full px-3 py-1 text-xs font-medium {b.class}">{b.label}</span>
        </a>
      </li>
    {/each}
  </ul>
{/if}
