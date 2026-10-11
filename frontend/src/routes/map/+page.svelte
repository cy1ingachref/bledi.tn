<script lang="ts">
  import { onMount } from "svelte";
  import L from "leaflet";
  import { api, type RoutePlan, type Station } from "$lib/router";

  // ── Transport modes ───────────────────────────────────────────────────────
  const MODES = [
    { id: "bus", label: "Bus", icon: "🚌", color: "#3b82f6" },
    { id: "metro", label: "Métro", icon: "🚇", color: "#ef4444" },
    { id: "tram", label: "Tram", icon: "🚊", color: "#f59e0b" },
    { id: "train", label: "Train", icon: "🚆", color: "#8b5cf6" },
    { id: "rfr", label: "RFR", icon: "🚈", color: "#06b6d4" },
    { id: "louaj", label: "Louaj", icon: "🚕", color: "#f97316" },
    { id: "walk", label: "Marche", icon: "🚶", color: "#22c55e" },
  ] as const;

  type ModeId = (typeof MODES)[number]["id"];

  const OBJECTIVES = [
    { id: "fastest", label: "Le plus rapide", icon: "⚡" },
    { id: "cheapest", label: "Le moins cher", icon: "💰" },
    { id: "fewest_transfers", label: "Moins de changements", icon: "🔁" },
  ] as const;

  // ── State ─────────────────────────────────────────────────────────────────
  let mapEl: HTMLDivElement | null = $state(null);
  let map: L.Map | null = null;
  let stationLayer: L.LayerGroup | null = null;
  let routeLayer: L.LayerGroup | null = null;
  let startMarker: L.Marker | null = null;
  let endMarker: L.Marker | null = null;

  let stations: Station[] = $state([]);
  let loadingStations = $state(true);
  let error = $state("");

  let startLat = $state("36.8065");
  let startLon = $state("10.1815");
  let endLat = $state("36.7528");
  let endLon = $state("10.2108");

  let busSelected = $state(true);
  let metroSelected = $state(true);
  let tramSelected = $state(true);
  let trainSelected = $state(true);
  let rfrSelected = $state(true);
  let louajSelected = $state(false);
  let walkSelected = $state(false);

  let objective = $state<string>("fastest");
  let routePlan: RoutePlan | null = $state(null);
  let computing = $state(false);
  let selectedItinerary = $state(0);

  const modeGetters: Record<string, () => boolean> = {
    bus: () => busSelected,
    metro: () => metroSelected,
    tram: () => tramSelected,
    train: () => trainSelected,
    rfr: () => rfrSelected,
    louaj: () => louajSelected,
    walk: () => walkSelected,
  };

  function isModeSelected(id: string): boolean {
    const getter = modeGetters[id];
    return typeof getter === "function" ? getter() : false;
  }

  function toggleMode(id: ModeId) {
    switch (id) {
      case "bus": busSelected = !busSelected; break;
      case "metro": metroSelected = !metroSelected; break;
      case "tram": tramSelected = !tramSelected; break;
      case "train": trainSelected = !trainSelected; break;
      case "rfr": rfrSelected = !rfrSelected; break;
      case "louaj": louajSelected = !louajSelected; break;
      case "walk": walkSelected = !walkSelected; break;
    }
    refreshStations();
  }

  function getModeColor(mode: string): string {
    return MODES.find((m) => m.id === mode)?.color ?? "#94a3b8";
  }

  function getModeLabel(mode: string): string {
    return MODES.find((m) => m.id === mode)?.label ?? mode;
  }

  function getModeIcon(mode: string): string {
    return MODES.find((m) => m.id === mode)?.icon ?? "📍";
  }

  // ── Map ───────────────────────────────────────────────────────────────────
  function initMap() {
    if (!mapEl) return;
    map = L.map(mapEl, {
      center: [36.8065, 10.1815],
      zoom: 12,
      zoomControl: true,
      attributionControl: true,
    });

    // Free OSM tiles, darkened via CSS filter (CARTO now requires an API key)
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
      className: "map-tiles-dark",
    }).addTo(map);

    stationLayer = L.layerGroup().addTo(map);
    routeLayer = L.layerGroup().addTo(map);
  }

  function markerIcon(mode: string) {
    const color = getModeColor(mode);
    return L.divIcon({
      className: "",
      html: `<div style="
        width:14px;height:14px;border-radius:50%;
        background:${color};border:2px solid #0b1220;
        box-shadow:0 0 0 2px ${color}55;"></div>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    });
  }

  function endpointIcon(label: string, color: string) {
    return L.divIcon({
      className: "",
      html: `<div style="
        width:26px;height:26px;border-radius:50%;
        background:${color};color:#04121c;font-weight:800;font-size:12px;
        display:flex;align-items:center;justify-content:center;
        border:3px solid #e2e8f0;box-shadow:0 2px 10px #000a;">${label}</div>`,
      iconSize: [26, 26],
      iconAnchor: [13, 13],
    });
  }

  function refreshStations() {
    if (!map || !stationLayer) return;
    stationLayer.clearLayers();
    const visible = stations.filter((s) => isModeSelected(s.mode as ModeId));
    // Cap markers for performance; keep a representative sample
    const MAX = 1200;
    const step = Math.max(1, Math.ceil(visible.length / MAX));
    for (let i = 0; i < visible.length; i += step) {
      const s = visible[i];
      L.marker([s.lat, s.lon], { icon: markerIcon(s.mode), title: s.name })
        .bindTooltip(
          `<b>${s.name}</b><br/><span style="opacity:.7">${getModeLabel(s.mode)}</span>`,
          { direction: "top", offset: [0, -8] }
        )
        .addTo(stationLayer);
    }
  }

  function placeEndpoints() {
    if (!map) return;
    const sLat = parseFloat(startLat), sLon = parseFloat(startLon);
    const eLat = parseFloat(endLat), eLon = parseFloat(endLon);
    if (startMarker) map.removeLayer(startMarker);
    if (endMarker) map.removeLayer(endMarker);
    if (!isNaN(sLat) && !isNaN(sLon)) {
      startMarker = L.marker([sLat, sLon], { icon: endpointIcon("A", "#22d3ee") })
        .bindTooltip("Départ", { direction: "top" })
        .addTo(map);
    }
    if (!isNaN(eLat) && !isNaN(eLon)) {
      endMarker = L.marker([eLat, eLon], { icon: endpointIcon("B", "#f472b6") })
        .bindTooltip("Arrivée", { direction: "top" })
        .addTo(map);
    }
  }

  function drawItinerary(itin: RoutePlan["itineraries"][number]) {
    if (!map || !routeLayer) return;
    routeLayer.clearLayers();

    type Leg = { geometry?: [number, number][]; mode?: string; from?: string; to?: string };
    const legs = (itin.legs ?? []) as Leg[];

    for (const leg of legs) {
      const geom = leg.geometry;
      if (geom && geom.length >= 2) {
        L.polyline(
          geom.map(([lat, lon]) => [lat, lon] as [number, number]),
          {
            color: getModeColor(leg.mode ?? "bus"),
            weight: 5,
            opacity: 0.9,
            lineCap: "round",
          }
        ).addTo(routeLayer);
      }
    }

    // Fallback straight line if API returned no geometry
    const hasGeom = legs.some((l) => l.geometry && l.geometry.length >= 2);
    if (!hasGeom) {
      const sLat = parseFloat(startLat), sLon = parseFloat(startLon);
      const eLat = parseFloat(endLat), eLon = parseFloat(endLon);
      if (![sLat, sLon, eLat, eLon].some(isNaN)) {
        L.polyline([[sLat, sLon], [eLat, eLon]], {
          color: "#22d3ee",
          weight: 4,
          dashArray: "8 8",
          opacity: 0.85,
        }).addTo(routeLayer);
      }
    }

    const pts: [number, number][] = [];
    for (const leg of legs) if (leg.geometry) pts.push(...leg.geometry);
    if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.2));
    else {
      const sLat = parseFloat(startLat), sLon = parseFloat(startLon);
      const eLat = parseFloat(endLat), eLon = parseFloat(endLon);
      if (![sLat, sLon, eLat, eLon].some(isNaN))
        map.fitBounds(L.latLngBounds([[sLat, sLon], [eLat, eLon]]).pad(0.3));
    }
  }

  async function computeRoute() {
    computing = true;
    routePlan = null;
    error = "";
    try {
      const sLat = parseFloat(startLat), sLon = parseFloat(startLon);
      const eLat = parseFloat(endLat), eLon = parseFloat(endLon);
      if ([sLat, sLon, eLat, eLon].some(isNaN)) throw new Error("Coordonnées invalides.");

      const modesInclude = MODES.filter((m) => isModeSelected(m.id)).map((m) => m.id).join(",");
      if (!modesInclude) throw new Error("Sélectionnez au moins un moyen de transport.");

      placeEndpoints();
      const plan = await api.routePlan({
        startLat: sLat, startLon: sLon, endLat: eLat, endLon: eLon,
        modesInclude, objective,
      });
      routePlan = plan;
      selectedItinerary = 0;
      if (plan.itineraries?.length) drawItinerary(plan.itineraries[0]);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      computing = false;
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      error = "Géolocalisation non supportée par ce navigateur.";
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        startLat = pos.coords.latitude.toFixed(5);
        startLon = pos.coords.longitude.toFixed(5);
        placeEndpoints();
        map?.setView([pos.coords.latitude, pos.coords.longitude], 14);
      },
      () => { error = "Impossible d'obtenir votre position."; }
    );
  }

  onMount(() => {
    initMap();
    placeEndpoints();
    (async () => {
      try {
        const gj = await api.getStations();
        const features = (gj as unknown as { features?: unknown[] }).features ?? [];
        stations = (features as Array<{
          properties?: Record<string, unknown>;
          geometry?: { coordinates?: [number, number] };
        }>).map((f) => {
          const p = f.properties ?? {};
          return {
            id: String(p.id ?? ""),
            name: String(p.name ?? "Sans nom"),
            lat: f.geometry?.coordinates?.[1] ?? 0,
            lon: f.geometry?.coordinates?.[0] ?? 0,
            mode: String(p.mode ?? "walk"),
          };
        }).filter((s) => s.lat !== 0 && s.lon !== 0);
        refreshStations();
      } catch (e) {
        error = "Impossible de charger les stations: " + (e instanceof Error ? e.message : String(e));
      } finally {
        loadingStations = false;
      }
    })();

    return () => { map?.remove(); map = null; };
  });
</script>

<div class="flex h-screen flex-col bg-[#070d18] text-slate-200">
  <!-- ── Header ─────────────────────────────────────────────────────────── -->
  <header class="z-20 flex items-center justify-between border-b border-slate-800/80 bg-[#0b1220]/90 px-5 py-3 backdrop-blur">
    <div class="flex items-center gap-3">
      <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-400 to-cyan-600 text-lg shadow-lg shadow-cyan-500/20">
        🚌
      </div>
      <div>
        <h1 class="text-[15px] font-bold leading-tight tracking-tight text-white">Bledi.tn</h1>
        <p class="text-[11px] leading-tight text-slate-500">Planificateur de transport · Tunisie</p>
      </div>
    </div>
    <div class="flex items-center gap-2 text-[11px]">
      <span class="rounded-full border border-slate-700/60 bg-slate-800/60 px-2.5 py-1 text-slate-400">
        {stations.length.toLocaleString("fr-FR")} arrêts
      </span>
      {#if routePlan?.itineraries?.length}
        <span class="rounded-full border border-cyan-700/50 bg-cyan-950/60 px-2.5 py-1 font-medium text-cyan-300">
          {routePlan.itineraries.length} itinéraire{routePlan.itineraries.length > 1 ? "s" : ""}
        </span>
      {/if}
    </div>
  </header>

  <div class="flex min-h-0 flex-1">
    <!-- ── Sidebar ──────────────────────────────────────────────────────── -->
    <aside class="z-10 flex w-[340px] flex-shrink-0 flex-col overflow-y-auto border-r border-slate-800/80 bg-[#0b1220]">
      <div class="space-y-5 p-4">
        <!-- Trip endpoints -->
        <section class="space-y-2.5">
          <div class="flex items-center justify-between">
            <h2 class="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Votre trajet</h2>
            <button
              onclick={useMyLocation}
              class="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-cyan-400 transition-colors hover:bg-cyan-950/50"
            >
              📍 Ma position
            </button>
          </div>

          <div class="space-y-2">
            <div class="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2">
              <span class="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-cyan-500 text-[10px] font-bold text-cyan-950">A</span>
              <input
                bind:value={startLat}
                onchange={placeEndpoints}
                placeholder="Lat"
                class="w-[72px] rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-200 outline-none focus:border-cyan-600"
              />
              <input
                bind:value={startLon}
                onchange={placeEndpoints}
                placeholder="Lon"
                class="w-[72px] rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-200 outline-none focus:border-cyan-600"
              />
            </div>

            <div class="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2">
              <span class="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-pink-400 text-[10px] font-bold text-pink-950">B</span>
              <input
                bind:value={endLat}
                onchange={placeEndpoints}
                placeholder="Lat"
                class="w-[72px] rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-200 outline-none focus:border-cyan-600"
              />
              <input
                bind:value={endLon}
                onchange={placeEndpoints}
                placeholder="Lon"
                class="w-[72px] rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-200 outline-none focus:border-cyan-600"
              />
            </div>
          </div>
        </section>

        <!-- Objective -->
        <section class="space-y-2">
          <h2 class="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Priorité</h2>
          <div class="grid grid-cols-3 gap-1.5">
            {#each OBJECTIVES as obj}
              <button
                onclick={() => (objective = obj.id)}
                class="flex flex-col items-center gap-1 rounded-lg border px-1 py-2 text-[10px] font-medium transition-all {objective === obj.id
                  ? 'border-cyan-500/70 bg-cyan-950/60 text-cyan-300'
                  : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700 hover:text-slate-300'}"
              >
                <span class="text-sm">{obj.icon}</span>
                <span class="text-center leading-tight">{obj.label}</span>
              </button>
            {/each}
          </div>
        </section>

        <!-- Modes -->
        <section class="space-y-2">
          <h2 class="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Moyens de transport
          </h2>
          <div class="grid grid-cols-2 gap-1.5">
            {#each MODES as mode}
              <button
                onclick={() => toggleMode(mode.id)}
                aria-pressed={isModeSelected(mode.id)}
                class="group flex items-center gap-2 rounded-lg border px-2 py-2 text-xs font-medium transition-all {isModeSelected(mode.id)
                  ? 'border-slate-700 bg-slate-800 text-white'
                  : 'border-slate-800/70 bg-slate-900/40 text-slate-500 hover:border-slate-700'}"
              >
                <span
                  class="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-[5px] border text-[9px] font-bold transition-all {isModeSelected(mode.id)
                    ? 'border-transparent text-slate-950'
                    : 'border-slate-700 text-transparent'}"
                  style={isModeSelected(mode.id) ? `background:${mode.color}` : ""}
                >
                  ✓
                </span>
                <span class="text-sm leading-none">{mode.icon}</span>
                <span class="truncate">{mode.label}</span>
              </button>
            {/each}
          </div>
        </section>

        <!-- Compute -->
        <button
          onclick={computeRoute}
          disabled={computing}
          class="w-full rounded-xl bg-gradient-to-r from-cyan-500 to-cyan-600 px-4 py-3 text-sm font-bold text-cyan-950 shadow-lg shadow-cyan-500/20 transition-all hover:from-cyan-400 hover:to-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {computing ? "Calcul en cours…" : "Calculer l'itinéraire"}
        </button>

        {#if error}
          <div class="rounded-lg border border-red-800/60 bg-red-950/40 p-2.5 text-[11px] leading-snug text-red-300">
            {error}
          </div>
        {/if}

        <!-- Results -->
        {#if routePlan?.itineraries?.length}
          <section class="space-y-2">
            <h2 class="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Options · du plus rapide au plus économique
            </h2>
            <div class="space-y-2">
              {#each routePlan.itineraries as itin, i}
                <button
                  onclick={() => {
                    selectedItinerary = i;
                    drawItinerary(itin);
                  }}
                  class="w-full rounded-xl border p-3 text-left transition-all {selectedItinerary === i
                    ? 'border-cyan-500/70 bg-slate-800/90 shadow-lg shadow-cyan-500/10'
                    : 'border-slate-800 bg-slate-900/50 hover:border-slate-700'}"
                >
                  <div class="mb-2 flex items-center justify-between">
                    <span class="text-xs font-bold text-white">Option {i + 1}</span>
                    <span class="text-[11px] font-medium text-cyan-300">
                      {itin.duration_min.toFixed(0)} min
                    </span>
                  </div>
                  <div class="mb-2 flex flex-wrap items-center gap-1">
                    {#each itin.modes_used as m}
                      <span
                        class="rounded px-1.5 py-0.5 text-[10px] font-semibold text-slate-950"
                        style="background:{getModeColor(m)}"
                      >
                        {getModeIcon(m)} {getModeLabel(m)}
                      </span>
                    {/each}
                  </div>
                  <div class="flex items-center gap-3 text-[11px] text-slate-400">
                    <span>🔁 {itin.transfers} changement{itin.transfers > 1 ? "s" : ""}</span>
                    {#if itin.fare_dinars > 0}
                      <span>💵 {itin.fare_dinars.toFixed(2)} DT</span>
                    {/if}
                  </div>
                  {#if itin.rank_reason}
                    <p class="mt-1.5 text-[10px] italic leading-snug text-slate-500">{itin.rank_reason}</p>
                  {/if}
                </button>
              {/each}
            </div>
          </section>
        {:else if routePlan}
          <div class="rounded-lg border border-amber-800/60 bg-amber-950/30 p-2.5 text-[11px] text-amber-300">
            Aucun itinéraire trouvé avec ces critères. Essayez d'activer plus de moyens de transport.
          </div>
        {/if}
      </div>
    </aside>

    <!-- ── Map ──────────────────────────────────────────────────────────── -->
    <main class="relative min-w-0 flex-1">
      <div bind:this={mapEl} class="absolute inset-0"></div>

      {#if loadingStations}
        <div class="pointer-events-none absolute left-1/2 top-4 z-[500] -translate-x-1/2">
          <div class="flex items-center gap-2 rounded-full border border-slate-700/60 bg-[#0b1220]/90 px-3 py-1.5 text-[11px] text-slate-300 shadow-xl backdrop-blur">
            <span class="h-3 w-3 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent"></span>
            Chargement des arrêts…
          </div>
        </div>
      {/if}

      <!-- Legend -->
      <div class="absolute bottom-6 right-3 z-[500] rounded-xl border border-slate-800/80 bg-[#0b1220]/90 p-2.5 shadow-2xl backdrop-blur">
        <p class="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Légende</p>
        <div class="grid grid-cols-2 gap-x-3 gap-y-1">
          {#each MODES as mode}
            <div class="flex items-center gap-1.5 text-[10px] {isModeSelected(mode.id) ? 'text-slate-300' : 'text-slate-600 line-through'}">
              <span class="h-2.5 w-2.5 rounded-full" style="background:{mode.color}"></span>
              {mode.label}
            </div>
          {/each}
        </div>
      </div>
    </main>
  </div>
</div>
