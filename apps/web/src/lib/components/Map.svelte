<script lang="ts">
  import { onMount } from "svelte";
  import maplibregl from "maplibre-gl";
  import "maplibre-gl/dist/maplibre-gl.css";
  import type { FeatureCollection } from "geojson";

  export interface Corner {
    lat: number;
    lon: number;
  }

  let {
    lat = $bindable(-20.5),
    lon = $bindable(-70.5),
    faultCorners = null,
    interactive = true,
  }: {
    lat?: number;
    lon?: number;
    faultCorners?: Corner[] | null;
    interactive?: boolean;
  } = $props();

  let container: HTMLDivElement;
  let map: maplibregl.Map | undefined;
  let marker: maplibregl.Marker | undefined;
  let ready = $state(false);

  const empty: FeatureCollection = { type: "FeatureCollection", features: [] };

  function faultData(): FeatureCollection {
    if (!faultCorners || faultCorners.length < 3) return empty;
    const ring = faultCorners.map((c) => [c.lon, c.lat]);
    return {
      type: "FeatureCollection",
      features: [
        { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } },
      ],
    };
  }

  onMount(() => {
    map = new maplibregl.Map({
      container,
      style: "https://demotiles.maplibre.org/style.json",
      center: [lon, lat],
      zoom: 4,
    });
    map.addControl(new maplibregl.NavigationControl({}), "top-right");
    marker = new maplibregl.Marker({ color: "#1d4ed8" }).setLngLat([lon, lat]).addTo(map);

    if (interactive) {
      map.on("click", (e) => {
        lon = Number(e.lngLat.lng.toFixed(4));
        lat = Number(e.lngLat.lat.toFixed(4));
      });
    }

    map.on("load", () => {
      map!.addSource("fault", { type: "geojson", data: faultData() });
      map!.addLayer({
        id: "fault-fill",
        type: "fill",
        source: "fault",
        paint: { "fill-color": "#1d4ed8", "fill-opacity": 0.2 },
      });
      map!.addLayer({
        id: "fault-line",
        type: "line",
        source: "fault",
        paint: { "line-color": "#1d4ed8", "line-width": 2 },
      });
      ready = true;
    });

    return () => map?.remove();
  });

  // Keep the marker in sync with form edits.
  $effect(() => {
    marker?.setLngLat([lon, lat]);
  });

  // Add the fault polygon after preview data arrives.
  $effect(() => {
    const data = faultData();
    if (ready) {
      const src = map?.getSource("fault") as maplibregl.GeoJSONSource | undefined;
      src?.setData(data);
    }
  });
</script>

<div bind:this={container} class="h-120 w-full overflow-hidden rounded-xl border border-neutral-200"></div>
