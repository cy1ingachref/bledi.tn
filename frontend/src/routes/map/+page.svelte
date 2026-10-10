<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Station, type RoutePlan } from "$lib/router";

  const W = 900;
  const H = 520;

  // ── Transport modes ──────────────────────────────────────────────────────
  const MODES = [
    { id: "bus", label: "Bus", icon: "🚌", color: "#3b82f6" },
    { id: "metro", label: "Metro", icon: "🚇", color: "#ef4444" },
    { id: "tram", label: "Tram", icon: "🚊", color: "#f59e0b" },
    { id: "train", label: "Train", icon: "🚆", color: "#8b5cf6" },
    { id: "rfr", label: "RFR", icon: "🚌", color: "#06b6d4" },
    { id: "louaj", label: "Louaj", icon: "🚕", color: "#f97316" },
    { id: "walk", label: "Walk", icon: "🚶", color: "#22c55e" },
  ] as const;

  type ModeId = (typeof MODES)[number]["id"];

  const OBJECTIVES = [
    { id: "fastest", label: "Fastest" },
    { id: "cheapest", label: "Cheapest" },
    { id: "fewest_transfers", label: "Fewest transfers" },
  ] as const;

  // ── State ────────────────────────────────────────────────────────────────
  let canvas: HTMLCanvasElement | null = null;
  let ctx: CanvasRenderingContext2D | null = null;
  let stations: Station[] = [];
  let state = "loading";
  let error = "";

  // Route inputs
  let startLat = "36.8065";
  let startLon = "10.1815";
  let endLat = "36.7528";
  let endLon = "10.2108";

  // Mode selection
  let selectedModes = new Set<ModeId>(["bus", "metro", "train", "tram", "rfr"]);

  // Objective
  let objective = "fastest";

  // Results
  let routePlan: RoutePlan | null = null;
  let computingRoute = false;
  let selectedItinerary = 0;

  // Map view
  let cx = 0;
  let cy = 0;
  let scale = 1;
  let configuredRoute: unknown = null;

  function mmerc(lat: number, lon: number): [number, number] {
    return [lon, Math.log(Math.tan((lat * Math.PI) / 360 + Math.PI / 4))];
  }

  function toggleMode(id: ModeId) {
    if (selectedModes.has(id)) {
      selectedModes.delete(id);
    } else {
      selectedModes.add(id);
    }
    selectedModes = new Set(selectedModes); // trigger reactivity
  }

  function isModeSelected(id: ModeId): boolean {
    return selectedModes.has(id);
  }

  function setObjective(obj: string) {
    objective = obj;
  }

  function getModeColor(mode: string): string {
    return MODES.find((m) => m.id === mode)?.color ?? "#94a3b8";
  }

  function getModeLabel(mode: string): string {
    return MODES.find((m) => m.id === mode)?.label ?? mode;
  }

  // ── Routing ──────────────────────────────────────────────────────────────
  async function computeRoute() {
    computingRoute = true;
    routePlan = null;
    selectedItinerary = 0;
    try {
      const sLat = parseFloat(startLat);
      const sLon = parseFloat(startLon);
      const eLat = parseFloat(endLat);
      const eLon = parseFloat(endLon);

      if (isNaN(sLat) || isNaN(sLon) || isNaN(eLat) || isNaN(eLon)) {
        throw new Error("Please enter valid coordinates");
      }

      const modesInclude = [...selectedModes].join(",");
      const plan = await api.routePlan({
        startLat: sLat,
        startLon: sLon,
        endLat: eLat,
        endLon: eLon,
        modesInclude,
        objective,
      });
      routePlan = plan;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      computingRoute = false;
    }
  }

  // ── Drawing ──────────────────────────────────────────────────────────────
  function fit(points: [number, number][]) {
    if (!points.length) return;
    let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
    for (const [x, y] of points) {
      minx = Math.min(minx, x);
      miny = Math.min(miny, y);
      maxx = Math.max(maxx, x);
      maxy = Math.max(maxy, y);
    }
    const midX = (minx + maxx) / 2;
    const midY = (miny + maxy) / 2;
    const w = (maxx - minx) / 2;
    const h = (maxy - miny) / 2;
    const span = Math.max(w, h);
    cx = midX;
    cy = midY;
    scale = Math.min(W, H) / (span * 2.1 || 1);
  }

  function canvasToX(xLin: number): number {
    return (xLin - cx) * scale + W / 2;
  }

  function canvasToY(yLin: number): number {
    return (cy - yLin) * scale + H / 2;
  }

  function isStationMarked(st: Station): boolean {
    return st.mode !== "walk";
  }

  function redraw() {
    const c = ctx;
    if (!c || !canvas) return;
    c.clearRect(0, 0, W, H);
    c.fillStyle = "#0f1923";
    c.fillRect(0, 0, W, H);

    // Grid
    for (let x = -1200000; x < 1200001; x += 600000) {
      c.beginPath();
      c.strokeStyle = "#1e293b";
      c.lineWidth = 1;
      c.moveTo(canvasToX(x), 0);
      c.lineTo(canvasToX(x), H);
      c.stroke();
    }
    for (let y = -850000; y < 850001; y += 425000) {
      c.beginPath();
      c.strokeStyle = "#1e293b";
      c.lineWidth = 1;
      c.moveTo(0, canvasToY(y));
      c.lineTo(W, canvasToY(y));
      c.stroke();
    }

    // Route geometry
    if (configuredRoute) {
      const route = configuredRoute as { legs?: Array<{ geometry?: [number, number][]; mode?: string }> };
      if (route.legs) {
        for (const leg of route.legs) {
          if (leg.geometry && leg.geometry.length >= 2) {
            c.beginPath();
            c.strokeStyle = getModeColor(leg.mode ?? "bus");
            c.lineWidth = 3;
            c.lineCap = "round";
            c.lineJoin = "round";
            const [firstLat, firstLon] = leg.geometry[0];
            const [fx, fy] = mmerc(firstLat, firstLon);
            c.moveTo(canvasToX(fx), canvasToY(fy));
            for (let i = 1; i < leg.geometry.length; i++) {
              const [lat, lon] = leg.geometry[i];
              const [x, y] = mmerc(lat, lon);
              c.lineTo(canvasToX(x), canvasToY(y));
            }
            c.stroke();
          }
        }
      }
    }

    // Stations
    for (const st of stations) {
      const [x, y] = mmerc(st.lat, st.lon);
      const px = canvasToX(x);
      const py = canvasToY(y);
      c.beginPath();
      c.fillStyle = isStationMarked(st) ? "#22d3ee" : "#f8fafc";
      c.arc(px, py, isStationMarked(st) ? 4 : 2, 0, Math.PI * 2);
      c.fill();
    }
  }

  onMount(async () => {
    ctx = canvas?.getContext("2d");
    if (!ctx) return;
    try {
      const geojson = await api.getStations();
      const features = (geojson as { features?: unknown[] }).features ?? [];
      stations = (features as Array<{ properties?: Record<string, unknown>; geometry?: { coordinates?: [number, number] } }>).map((f) => {
        const p = f.properties ?? {};
        return {
          id: String(p.id ?? ""),
          name: String(p.name ?? ""),
          name_en: String(p.name_en ?? p.name ?? ""),
          lat: f.geometry?.coordinates?.[1] ?? 0,
          lon: f.geometry?.coordinates?.[0] ?? 0,
          mode: String(p.mode ?? "walk"),
          operator: String(p.operator ?? ""),
          route_type: Number(p.route_type ?? 0),
          license_status: String(p.license_status ?? ""),
          city: String(p.city ?? ""),
          source: String(p.source ?? ""),
        };
      });
      const stops2d = stations.map((st) => mmerc(st.lat, st.lon));
      fit(stops2d);
      redraw();
      state = "ready";
    } catch (e) {
      // Don't block the UI if stations fail to load — user can still pick modes and route
      state = "ready";
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>

<div class="flex flex-col h-screen bg-slate-950 text-slate-100">
  <!-- Header -->
  <header class="flex items-center justify-between border-b border-slate-800 px-4 py-2">
    <h1 class="text-lg font-semibold">Bledi.tn — Planificateur d'itinéraire</h1>
    <div class="text-xs text-slate-400">
      {stations.length} stations · {routePlan?.itineraries?.length ?? 0} itinéraires
    </div>
  </header>

  <div class="flex flex-1 overflow-hidden">
    <!-- Sidebar -->
    <aside class="w-80 flex-shrink-0 border-r border-slate-800 overflow-y-auto p-4 space-y-4">
      <!-- Route inputs -->
      <section class="space-y-2">
        <h2 class="text-sm font-semibold text-slate-300">Départ</h2>
        <div class="flex gap-2">
          <input
            bind:value={startLat}
            placeholder="Lat"
            class="w-1/2 rounded bg-slate-800 border border-slate-700 px-2 py-1 text-sm"
          />
          <input
            bind:value={startLon}
            placeholder="Lon"
            class="w-1/2 rounded bg-slate-800 border border-slate-700 px-2 py-1 text-sm"
          />
        </div>
      </section>

      <section class="space-y-2">
        <h2 class="text-sm font-semibold text-slate-300">Arrivée</h2>
        <div class="flex gap-2">
          <input
            bind:value={endLat}
            placeholder="Lat"
            class="w-1/2 rounded bg-slate-800 border border-slate-700 px-2 py-1 text-sm"
          />
          <input
            bind:value={endLon}
            placeholder="Lon"
            class="w-1/2 rounded bg-slate-800 border border-slate-700 px-2 py-1 text-sm"
          />
        </div>
      </section>

      <!-- Objective -->
      <section class="space-y-2">
        <h2 class="text-sm font-semibold text-slate-300">Objectif</h2>
        <div class="flex gap-1">
          {#each OBJECTIVES as obj}
            <button
              class="flex-1 rounded px-2 py-1 text-xs font-medium transition-colors {objective === obj.id
                ? 'bg-cyan-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}"
              on:click={() => setObjective(obj.id)}
            >
              {obj.label}
            </button>
          {/each}
        </div>
      </section>

      <!-- Mode selection -->
      <section class="space-y-2">
        <h2 class="text-sm font-semibold text-slate-300">Moyens de transport</h2>
        <div class="space-y-1">
          {#each MODES as mode}
            <button
              class="w-full flex items-center gap-2 rounded px-2 py-1.5 text-xs font-medium transition-all {isModeSelected(mode.id)
                ? 'bg-cyan-900/50 text-cyan-200 ring-1 ring-cyan-500'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-300'}"
              on:click={() => toggleMode(mode.id)}
            >
              <span class="w-4 h-4 rounded border-2 flex items-center justify-center text-[10px] font-bold {isModeSelected(mode.id) ? 'bg-cyan-500 border-cyan-500 text-white' : 'border-slate-600 text-transparent'}">
                ✓
              </span>
              <span class="w-3 h-3 rounded-full" style="background:{mode.color}"></span>
              <span>{mode.icon} {mode.label}</span>
            </button>
          {/each}
        </div>
      </section>

      <!-- Compute button -->
      <button
        class="w-full rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed px-4 py-2 text-sm font-semibold text-white transition-colors"
        on:click={computeRoute}
        disabled={computingRoute || selectedModes.size === 0}
      >
        {computingRoute ? "Calcul..." : "Calculer l'itinéraire"}
      </button>

      {#if error}
        <div class="rounded bg-red-900/50 border border-red-700 p-2 text-xs text-red-200">
          {error}
        </div>
      {/if}

      <!-- Results -->
      {#if routePlan && routePlan.itineraries?.length}
        <section class="space-y-2">
          <h2 class="text-sm font-semibold text-slate-300">
            {routePlan.itineraries.length} itinéraire{routePlan.itineraries.length > 1 ? "s" : ""}
          </h2>
          <div class="space-y-2">
            {#each routePlan.itineraries as itin, i}
              <button
                class="w-full text-left rounded-lg border p-3 transition-colors {selectedItinerary === i
                  ? 'border-cyan-500 bg-slate-800'
                  : 'border-slate-700 bg-slate-800/50 hover:bg-slate-800'}"
                on:click={() => {
                  selectedItinerary = i;
                  configuredRoute = itin;
                  redraw();
                }}
              >
                <div class="flex items-center justify-between mb-1">
                  <span class="text-sm font-semibold">Option {i + 1}</span>
                  <span class="text-xs text-slate-400">
                    {itin.duration_min.toFixed(0)} min · {itin.transfers} correspondance{itin.transfers > 1 ? "s" : ""}
                  </span>
                </div>
                <div class="flex flex-wrap gap-1">
                  {#each itin.modes_used as mode}
                    <span
                      class="inline-block rounded px-1.5 py-0.5 text-[10px] font-medium text-white"
                      style="background:{getModeColor(mode)}"
                    >
                      {getModeLabel(mode)}
                    </span>
                  {/each}
                </div>
                {#if itin.fare_dinars > 0}
                  <div class="mt-1 text-xs text-slate-400">
                    ~{itin.fare_dinars.toFixed(2)} DT
                  </div>
                {/if}
                {#if itin.rank_reason}
                  <div class="mt-1 text-[11px] text-slate-500 italic">
                    {itin.rank_reason}
                  </div>
                {/if}
              </button>
            {/each}
          </div>
        </section>
      {:else if routePlan && !routePlan.itineraries?.length}
        <div class="rounded bg-amber-900/30 border border-amber-700 p-2 text-xs text-amber-200">
          Aucun itinéraire trouvé avec ces critères.
        </div>
      {/if}
    </aside>

    <!-- Map -->
    <main class="flex-1 relative bg-slate-950 overflow-hidden">
      <canvas
        bind:this={canvas}
        width={W}
        height={H}
        class="w-full h-full cursor-crosshair"
      />
      {#if state === "loading"}
        <div class="absolute inset-0 flex items-center justify-center text-slate-400">
          Chargement...
        </div>
      {/if}
    </main>
  </div>
</div>

<style>
  :global(body) {
    margin: 0;
    background: #0f1923;
  }
</style>
