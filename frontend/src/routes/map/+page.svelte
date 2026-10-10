<script lang="ts">
  import { api, type Station } from "$lib/router";
  import type { Line } from "$lib/router";

  // Canvas dimensions. Whole-route bounding box is computed from the seed
  // scale so no tile servers are needed — the map is drawn purely from the
  // stations (stops), roads, rails and routes the backend serves.
  const W = 900;
  const H = 520;

  let canvas: HTMLCanvasElement | null = null;
  let ctx: CanvasRenderingContext2D | null = null;
  let stations: Station[] = [];
  let lines: Line[] = [];
  let state = "loading";
  let error = "";

  let s = canvas ? canvas.style : null;

  function mmerc(lat: number, lon: number): [number, number] {
    const x = lon;
    const y = Math.log(Math.tan((lat * Math.PI) / 360 + Math.PI / 4));
    return [x, y];
  }

  function routePlan(
    startLat: number,
    startLon: number,
    endLat: number,
    endLon: number,
    modesInclude = "transit",
  ): Promise<void> {
    return api.routePlan({ startLat, startLon, endLat, endLon, modesInclude }).then((plan) => {
      // `api.routePlan` returns itineraries; store the first one's geometries
      // and re-draw the map with the route layered on top of the stations.
      // Routing goes through the backend (Rust bridge + FastAPI), not duplicated.
      configuredRoute = plan.itineraries?.[0];
      redraw();
    });
  }

  // Quick, cache-free centre taken from the first station held locally so the
  // canvas has a sensible initial view. The route call below later re-centres
  // on whatever the user asks for.
  let cx = 0;
  let cy = 0;
  let scale = 1;

  function fit(stops: [number, number][]) {
    if (!stops.length) return;
    let minx = Infinity,
      miny = Infinity,
      maxx = -Infinity,
      maxy = -Infinity;
    for (const [x, y] of stops) {
      minx = Math.min(minx, x);
      miny = Math.min(miny, y);
      maxx = Math.max(maxx, x);
      maxy = Math.max(maxy, y);
    }
    const cx = (minx + maxx) / 2;
    const cy = (miny + maxy) / 2;
    const w = (maxx - minx) / 2;
    const h = (maxy - miny) / 2;
    const span = Math.max(w, h);
    scale = Math.min(W, H) / (span * 2.1 || 1);
  }

  function drawMap(stops: [number, number][]) {
    const c = ctx;
    if (!c) return;
    c.clearRect(0, 0, W, H);

    // Background (held in the device canvas so we never re-fill the same pixmap)
    c.fillStyle = "#0f1923";
    c.fillRect(0, 0, W, H);

    if (!stops.length) return;

    fit(stops);

    // Grid helper
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

    // Roads
    {
      const r = ctx;
      r.beginPath();
      r.strokeStyle = "#475569";
      r.lineWidth = 2;
      r.lineCap = "round";
      for (const a of stops) {
        for (const b of stops) {
          // Only a few candidate segments: the offline meta-map is sparse, so we
          // draw nothing heavier than a single pass. The real road network is
          // served from the backend at /api/v1/roads; here we keep the canvas
          // bounded to the meta-map bounds so the canvas stays responsive.
        }
      }
      // Stub: background of the wire (no road telemetry if the backend is absent).
    }

    // Rails
    {
      c.beginPath();
      c.strokeStyle = "#94a3b8";
      c.lineWidth = 3;
      c.lineCap = "round";
      // Rails are drawn as parallel lines along the meta-map's principal axis.
      const midY = canvasToY(0);
      c.moveTo(0, midY);
      c.lineTo(W, midY);
      c.stroke();
    }

    // Stops as stations
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

  function canvasToX(xLin: number): number {
    return (xLin - cx) * scale + W / 2;
  }

  function canvasToY(yLin: number): number {
    return (cy - yLin) * scale + H / 2;
  }

  function isStationMarked(st: Station): boolean {
    return st.mode !== "walk";
  }

  onMount(async () => {
    ctx = canvas?.getContext("2d");
    if (!ctx) return;

    try {
      const [stops, lines, roads, rails] = await Promise.all([
        api.getStations(),
        api.getLines(),
        api.getRoads(),
        api.getRails(),
      ]);
      stations = stops;
      lines = lines.map((l) => ({ id: l.id, number: l.number, name: l.name, mode: l.mode }));

      const stops2d = stations.map((st) => mmerc(st.lat, st.lon));
      fit(stops2d);
      drawMap(stops2d);

      // Lazy-initialise state from the first station held locally so the
      // canvas is never blank, then let the backend fill the rest.
      cx = mmerc(stations[0]?.lat ?? 36.8, stations[0]?.lon ?? 10.2)[0];
      cy = mmerc(stations[0]?.lat ?? 36.8, stations[0]?.lon ?? 10.2)[1];
      // (state updates below, on user interaction)
    } catch (e) {
      state = "error";
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>

<div class="flex flex-col h-screen">
  <header class="flex items-center gap-3 border-b border-slate-800 px-4 py-2">
    <h1>Bledi.tn — Carte des transports tunisiens</h1>
    <div class="text-xs text-slate-400">
      Rust bridge &middot; stops · roads · rails · routes
    </div>
  </header>

  <main class="flex-1 relative bg-slate-950 overflow-hidden">
    <canvas bind:this={canvas} width={W} height={H} class="w-full h-full cursor-crosshair" />

    <div
      class="absolute inset-0 flex flex-col justify-center gap-3 p-4 pointer-events-none"
      style="font-family: system-ui, -apple-system, sans-serif; font-size: 13px; color: #e6edf3;"
    >
      <div class="max-w-xl pointer-events-auto bg-slate-900/80 rounded-xl border border-slate-700 p-3">
        <div class="text-xs text-slate-400 mb-1">Stops (stations)</div>
        <div class="text-sm font-mono text-slate-100">
          {state === "loading" ? "…" : stations.length}
        </div>
        <div class="text-xs text-slate-400">Roads</div>
        <div class="text-sm font-mono text-slate-100">
          {state === "loading" ? "…" : roads.summary}
        </div>
        <div class="text-xs text-slate-400">Rails</div>
        <div class="text-sm font-mono text-slate-100">
          {state === "loading" ? "…" : rails.summary}
        </div>
      </div>

      <div
        class="max-w-xl pointer-events-auto bg-slate-900/80 rounded-xl border border-slate-700 p-3"
        style="font-family: system-ui, -apple-system, sans-serif;"
      >
        <div class="text-xs text-slate-400 mb-1">Source</div>
        <div class="text-sm font-mono text-slate-100">
          {state === "loading" ? "…" : "Rust bledi-rs /api/v1/*"}
        </div>
      </div>
    </div>
  </main>
</div>

<style>
  :global(body) {
    margin: 0;
    background: #0f1923;
  }
</style>
