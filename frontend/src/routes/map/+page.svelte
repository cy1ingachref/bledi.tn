<script lang="ts">
  import { onMount } from "svelte";
  import L from "leaflet";
  import Icon from "$lib/Icon.svelte";
  import { api, type RoutePlan, type Station } from "$lib/router";
  import { LANGS, translator, dirOf, formatDuration, modeLabel, type Lang } from "$lib/i18n";

  // ── Transport modes ───────────────────────────────────────────────────────
  // Colours follow the project's established dark palette (see docs/frontend-notes.md
  // and the archived bledi-map.html): distinct, high-contrast hues on dark surfaces.
  const MODES = [
    { id: "bus", icon: "bus", color: "#ef4444" },
    { id: "metro", icon: "metro", color: "#3b82f6" },
    { id: "tram", icon: "tram", color: "#f59e0b" },
    { id: "train", icon: "train", color: "#8b5cf6" },
    { id: "rfr", icon: "rfr", color: "#f97316" },
    { id: "louaj", icon: "louaj", color: "#10b981" },
    { id: "taxi", icon: "taxi", color: "#eab308" },
    { id: "walk", icon: "walk", color: "#64748b" },
  ] as const;

  type ModeId = (typeof MODES)[number]["id"];

  const OBJECTIVES = [
    { id: "fastest", icon: "clock" },
    { id: "cheapest", icon: "coin" },
    { id: "fewest_transfers", icon: "transfer" },
  ] as const;

  // ── State ─────────────────────────────────────────────────────────────────
  let mapEl: HTMLDivElement | null = $state(null);
  let map: L.Map | null = null;
  let stationLayer: L.LayerGroup | null = null;
  let routeLayer: L.LayerGroup | null = null;
  let startMarker: L.Marker | null = null;
  let endMarker: L.Marker | null = null;

  let lang = $state<Lang>("fr");
  const t = $derived(translator(lang));
  const dir = $derived(dirOf(lang));

  let stations: Station[] = $state([]);
  let loadingStations = $state(true);
  let error = $state("");

  let startLat = $state("36.8065");
  let startLon = $state("10.1815");
  let endLat = $state("36.7528");
  let endLon = $state("10.2108");

  let busOn = $state(true);
  let metroOn = $state(true);
  let tramOn = $state(true);
  let trainOn = $state(true);
  let rfrOn = $state(true);
  let louajOn = $state(false);
  let taxiOn = $state(false);
  let walkOn = $state(false);

  let objective = $state<string>("fastest");
  let routePlan: RoutePlan | null = $state(null);
  let computing = $state(false);
  let selectedItinerary = $state(0);
  let locating = $state(false);
  let sideEl: HTMLElement | null = $state(null);
  let resultsEl: HTMLElement | null = $state(null);

  // Place search (docs note that raw coordinates are unfriendly; the backend
  // exposes /api/v1/geocode for this).
  type Geo = { lat: number; lon: number; display_name: string };
  let query = $state("");
  let results = $state<Geo[]>([]);
  let searching = $state(false);
  let target: "from" | "to" = $state("to");
  let searchTimer: ReturnType<typeof setTimeout> | null = null;

  function runSearch() {
    const q = query.trim();
    if (q.length < 3) { results = []; return; }
    searching = true;
    api.geocode(q)
      .then((r) => { results = r.slice(0, 6); })
      .catch(() => { results = []; })
      .finally(() => { searching = false; });
  }

  function onQueryInput() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, 350);
  }

  function pick(g: Geo) {
    if (target === "from") {
      startLat = g.lat.toFixed(5);
      startLon = g.lon.toFixed(5);
    } else {
      endLat = g.lat.toFixed(5);
      endLon = g.lon.toFixed(5);
    }
    results = [];
    query = "";
    placeEndpoints();
    map?.setView([g.lat, g.lon], 14);
  }

  function shortName(s: string): string {
    return s.split(",").slice(0, 2).join(",").trim();
  }

  const getters: Record<string, () => boolean> = {
    bus: () => busOn,
    metro: () => metroOn,
    tram: () => tramOn,
    train: () => trainOn,
    rfr: () => rfrOn,
    louaj: () => louajOn,
    taxi: () => taxiOn,
    walk: () => walkOn,
  };

  function isOn(id: string): boolean {
    const g = getters[id];
    return typeof g === "function" ? g() : false;
  }

  function toggleMode(id: ModeId) {
    switch (id) {
      case "bus": busOn = !busOn; break;
      case "metro": metroOn = !metroOn; break;
      case "tram": tramOn = !tramOn; break;
      case "train": trainOn = !trainOn; break;
      case "rfr": rfrOn = !rfrOn; break;
      case "louaj": louajOn = !louajOn; break;
      case "taxi": taxiOn = !taxiOn; break;
      case "walk": walkOn = !walkOn; break;
    }
    refreshStations();
  }

  function setAll(on: boolean) {
    busOn = metroOn = tramOn = trainOn = rfrOn = louajOn = taxiOn = walkOn = on;
    refreshStations();
  }

  const selectedCount = $derived(MODES.filter((m) => isOn(m.id)).length);

  function modeColor(id: string): string {
    return MODES.find((m) => m.id === id)?.color ?? "#94a3b8";
  }
  function modeIcon(id: string): string {
    return MODES.find((m) => m.id === id)?.icon ?? "pin";
  }

  // ── Map ───────────────────────────────────────────────────────────────────
  function initMap() {
    if (!mapEl) return;
    map = L.map(mapEl, {
      center: [36.8065, 10.1815],
      zoom: 12,
      zoomControl: false,
      attributionControl: true,
    });
    L.control.zoom({ position: "topright" }).addTo(map);

    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
      className: "map-tiles-dark",
    }).addTo(map);

    stationLayer = L.layerGroup().addTo(map);
    routeLayer = L.layerGroup().addTo(map);
  }

  function stationIcon(mode: string) {
    const c = modeColor(mode);
    return L.divIcon({
      className: "",
      html: `<span style="display:block;width:10px;height:10px;border-radius:50%;
        background:${c};border:1.5px solid rgba(6,10,20,.85);
        box-shadow:0 0 0 2px ${c}33;"></span>`,
      iconSize: [10, 10],
      iconAnchor: [5, 5],
    });
  }

  function endpointIcon(label: string, color: string) {
    return L.divIcon({
      className: "",
      html: `<span style="display:flex;width:28px;height:28px;border-radius:50%;
        align-items:center;justify-content:center;
        background:${color};color:#04070f;font-weight:800;font-size:12px;
        border:2.5px solid #e8eef7;box-shadow:0 3px 14px rgba(0,0,0,.7);">${label}</span>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
  }

  function refreshStations() {
    if (!map || !stationLayer) return;
    stationLayer.clearLayers();
    const visible = stations.filter((s) => isOn(s.mode));
    const MAX = 900;
    const step = Math.max(1, Math.ceil(visible.length / MAX));
    for (let i = 0; i < visible.length; i += step) {
      const s = visible[i];
      L.marker([s.lat, s.lon], { icon: stationIcon(s.mode), title: s.name })
        .bindTooltip(
          `<b>${s.name}</b><br/><span style="opacity:.65">${modeLabel(t, s.mode)}</span>`,
          { direction: "top", offset: [0, -6] }
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
    if (!isNaN(sLat) && !isNaN(sLon))
      startMarker = L.marker([sLat, sLon], { icon: endpointIcon("A", "#22d3ee") })
        .bindTooltip(t("trip.from"), { direction: "top" }).addTo(map);
    if (!isNaN(eLat) && !isNaN(eLon))
      endMarker = L.marker([eLat, eLon], { icon: endpointIcon("B", "#f472b6") })
        .bindTooltip(t("trip.to"), { direction: "top" }).addTo(map);
  }

  type Leg = {
    type?: string;
    mode?: string;
    line?: string;
    from?: { lat: number; lon: number };
    to?: { lat: number; lon: number };
    geometry?: [number, number][];
    duration_min?: number;
  };

  function drawItinerary(itin: RoutePlan["itineraries"][number]) {
    if (!map || !routeLayer) return;
    routeLayer.clearLayers();
    const legs = (itin.legs ?? []) as unknown as Leg[];

    for (const leg of legs) {
      if (leg.geometry && leg.geometry.length >= 2) {
        const isWalk = (leg.type ?? "").toLowerCase() === "walk";
        const pts = leg.geometry.map(([a, b]) => [a, b] as [number, number]);
        const color = isWalk ? "#94a3b8" : modeColor(leg.mode ?? "bus");

        // Casing: a wider dark stroke underneath keeps the route legible
        // against same-coloured station dots on the map.
        if (!isWalk) {
          L.polyline(pts, {
            color: "#050a12",
            weight: 9,
            opacity: 0.9,
            lineCap: "round",
            lineJoin: "round",
          }).addTo(routeLayer);
        }

        L.polyline(pts, {
          color,
          weight: isWalk ? 3 : 5,
          opacity: isWalk ? 0.8 : 1,
          dashArray: isWalk ? "1 7" : undefined,
          lineCap: "round",
          lineJoin: "round",
        }).addTo(routeLayer);
      }
    }

    const pts: [number, number][] = [];
    for (const l of legs) if (l.geometry) pts.push(...l.geometry);
    if (pts.length) {
      map.fitBounds(L.latLngBounds(pts).pad(0.18));
    } else {
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
      if ([sLat, sLon, eLat, eLon].some(isNaN)) throw new Error(t("error.coords"));

      const modesInclude = MODES.filter((m) => isOn(m.id)).map((m) => m.id).join(",");
      if (!modesInclude) throw new Error(t("error.noModes"));

      placeEndpoints();
      const plan = await api.routePlan({
        startLat: sLat, startLon: sLon, endLat: eLat, endLon: eLon,
        modesInclude, objective,
      });
      routePlan = plan;
      selectedItinerary = 0;
      if (plan.itineraries?.length) drawItinerary(plan.itineraries[0]);
      // Bring results into view so they are never hidden below the fold.
      if (plan.itineraries?.length) {
        requestAnimationFrame(() => {
          resultsEl?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      computing = false;
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) { error = t("error.geoUnsupported"); return; }
    locating = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        startLat = pos.coords.latitude.toFixed(5);
        startLon = pos.coords.longitude.toFixed(5);
        locating = false;
        placeEndpoints();
        map?.setView([pos.coords.latitude, pos.coords.longitude], 14);
      },
      () => { locating = false; error = t("error.geo"); },
      { timeout: 10000 }
    );
  }

  /** Fare field differs across API versions; read whichever is present. */
  function fareOf(itin: Record<string, unknown>): number {
    const v = itin.fare_estimate_dinars ?? itin.fare_dinars ?? 0;
    return typeof v === "number" ? v : 0;
  }

  /**
   * Human-readable step label. The API's `line` is an internal id like
   * "rail_19_a" / "bus_21b", so pull a readable token out of it rather than
   * showing the raw id.
   */
  function legLabel(leg: Leg): string {
    if ((leg.type ?? "").toLowerCase() === "walk") return t("step.walk");
    const base = modeLabel(t, leg.mode ?? "bus");
    // `line` is an internal id ("rail_19_a", "bus_21b"); surface the line
    // number so every transit leg is equally identifiable.
    const raw = leg.line ?? "";
    const m = raw.match(/(\d+[A-Za-z]?)/);
    return m ? `${base} ${m[1]}` : base;
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
        }>)
          .map((f) => {
            const p = f.properties ?? {};
            return {
              id: String(p.id ?? ""),
              name: String(p.name ?? ""),
              lat: f.geometry?.coordinates?.[1] ?? 0,
              lon: f.geometry?.coordinates?.[0] ?? 0,
              mode: String(p.mode ?? "walk"),
            };
          })
          .filter((s) => s.lat !== 0 && s.lon !== 0);
        refreshStations();
      } catch (e) {
        error = t("error.stations") + ": " + (e instanceof Error ? e.message : String(e));
      } finally {
        loadingStations = false;
      }
    })();
    return () => { map?.remove(); map = null; };
  });
</script>

<svelte:head>
  <title>Bledi.tn — {t("app.tagline")}</title>
</svelte:head>

<div class="app" dir={dir} lang={lang}>
  <!-- ── Header ──────────────────────────────────────────────────────────── -->
  <header class="hdr">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"><Icon name="route" size={19} /></span>
      <span class="brand-text">
        <strong>Bledi<span class="dot">.tn</span></strong>
        <small>{t("app.tagline")}</small>
      </span>
    </div>

    <div class="hdr-right">
      <span class="chip" title={t("status.stops")}>
        <Icon name="pin" size={13} /> {stations.length.toLocaleString("fr-FR")} <em>{t("status.stops")}</em>
      </span>
      {#if routePlan?.itineraries?.length}
        <span class="chip chip-accent">
          <Icon name="route" size={13} /> {routePlan.itineraries.length} <em>{t("status.routes")}</em>
        </span>
      {/if}

      <div class="langs" role="group" aria-label="Language">
        {#each LANGS as l}
          <button
            class="lang"
            class:on={lang === l.id}
            onclick={() => (lang = l.id)}
            aria-pressed={lang === l.id}
            title={l.label}
          >{l.short}</button>
        {/each}
      </div>
    </div>
  </header>

  <div class="body">
    <!-- ── Sidebar ───────────────────────────────────────────────────────── -->
    <aside class="side" bind:this={sideEl}>
      <!-- Trip -->
      <section class="sec">
        <div class="sec-head">
          <h2>{t("trip.title")}</h2>
          <button class="ghost" onclick={useMyLocation} disabled={locating}>
            <Icon name="locate" size={14} />
            {locating ? t("trip.locating") : t("trip.myLocation")}
          </button>
        </div>

        <!-- Place search -->
        <div class="search">
          <div class="search-row">
            <Icon name="search" size={14} cls="s-ic" />
            <input
              bind:value={query}
              oninput={onQueryInput}
              placeholder={t("search.placeholder")}
              aria-label={t("search.placeholder")}
            />
            {#if searching}
              <span class="spin dark" aria-hidden="true"></span>
            {/if}
          </div>

          <div class="targets" role="group" aria-label={t("search.usePlace")}>
            <button class="tgt" class:on={target === "from"} onclick={() => (target = "from")} aria-pressed={target === "from"}>
              <span class="badge a sm">A</span> {t("trip.from")}
            </button>
            <button class="tgt" class:on={target === "to"} onclick={() => (target = "to")} aria-pressed={target === "to"}>
              <span class="badge b sm">B</span> {t("trip.to")}
            </button>
          </div>

          {#if results.length > 0}
            <ul class="hits">
              {#each results as g}
                <li>
                  <button class="hit" onclick={() => pick(g)}>
                    <Icon name="pin" size={13} />
                    <span class="hit-tx">{shortName(g.display_name)}</span>
                  </button>
                </li>
              {/each}
            </ul>
          {:else if query.trim().length >= 3 && !searching}
            <p class="no-hit">{t("search.noResults")}</p>
          {/if}
        </div>

        <div class="field">
          <span class="badge a">A</span>
          <div class="inputs">
            <input bind:value={startLat} onchange={placeEndpoints} aria-label="{t('trip.from')} {t('trip.lat')}" placeholder={t("trip.lat")} inputmode="decimal" />
            <input bind:value={startLon} onchange={placeEndpoints} aria-label="{t('trip.from')} {t('trip.lon')}" placeholder={t("trip.lon")} inputmode="decimal" />
          </div>
        </div>
        <div class="field">
          <span class="badge b">B</span>
          <div class="inputs">
            <input bind:value={endLat} onchange={placeEndpoints} aria-label="{t('trip.to')} {t('trip.lat')}" placeholder={t("trip.lat")} inputmode="decimal" />
            <input bind:value={endLon} onchange={placeEndpoints} aria-label="{t('trip.to')} {t('trip.lon')}" placeholder={t("trip.lon")} inputmode="decimal" />
          </div>
        </div>
      </section>

      <!-- Priority -->
      <section class="sec">
        <h2>{t("priority.title")}</h2>
        <div class="grid3">
          {#each OBJECTIVES as o}
            <button
              class="opt"
              class:on={objective === o.id}
              onclick={() => (objective = o.id)}
              aria-pressed={objective === o.id}
            >
              <Icon name={o.icon} size={16} />
              <span>{t("priority." + o.id)}</span>
            </button>
          {/each}
        </div>
      </section>

      <!-- Modes -->
      <section class="sec">
        <div class="sec-head">
          <h2>{t("modes.title")}</h2>
          <span class="mini-actions">
            <button class="mini" onclick={() => setAll(true)}>{t("modes.selectAll")}</button>
            <span class="sep">·</span>
            <button class="mini" onclick={() => setAll(false)}>{t("modes.clear")}</button>
          </span>
        </div>
        <div class="grid2">
          {#each MODES as m}
            <button
              class="mode"
              class:on={isOn(m.id)}
              onclick={() => toggleMode(m.id)}
              aria-pressed={isOn(m.id)}
            >
              <span class="tick" style={isOn(m.id) ? `background:${m.color};border-color:${m.color}` : ""}>
                {#if isOn(m.id)}<Icon name="check" size={11} stroke={3.2} />{/if}
              </span>
              <span class="m-ic" style={isOn(m.id) ? `color:${m.color}` : ""}>
                <Icon name={m.icon} size={16} />
              </span>
              <span class="m-lbl">{t("modes." + m.id)}</span>
            </button>
          {/each}
        </div>
      </section>

      <button class="cta" onclick={computeRoute} disabled={computing || selectedCount === 0}>
        {#if computing}
          <span class="spin" aria-hidden="true"></span> {t("action.calculating")}
        {:else}
          <Icon name="search" size={16} /> {t("action.calculate")}
        {/if}
      </button>

      {#if error}
        <div class="alert" role="alert">
          <Icon name="alert" size={15} />
          <span>{error}</span>
        </div>
      {/if}

      <!-- Results -->
      {#if routePlan?.itineraries?.length}
        <section class="sec results" bind:this={resultsEl}>
          <div class="sec-head">
            <h2>{t("results.title")}</h2>
            <span class="sub">{t("results.subtitle")}</span>
          </div>

          {#each routePlan.itineraries as itin, i}
            {@const it = itin as unknown as Record<string, unknown>}
            {@const fare = fareOf(it)}
            <button
              class="itin"
              class:on={selectedItinerary === i}
              onclick={() => { selectedItinerary = i; drawItinerary(itin); }}
              aria-pressed={selectedItinerary === i}
            >
              <div class="it-top">
                <span class="it-n">{t("results.option")} {i + 1}</span>
                <span class="it-dur">{formatDuration(itin.duration_min, t)}</span>
              </div>

              <div class="it-pills">
                {#each itin.modes_used as mu}
                  <span class="pill" style="background:{modeColor(mu)}">
                    <Icon name={modeIcon(mu)} size={11} stroke={2.2} />
                    {modeLabel(t, mu)}
                  </span>
                {/each}
              </div>

              <div class="it-meta">
                <span>
                  <Icon name="transfer" size={12} />
                  {itin.transfers === 0
                    ? t("results.direct")
                    : `${itin.transfers} ${t(itin.transfers > 1 ? "results.transfersPlural" : "results.transfers")}`}
                </span>
                {#if fare > 0}
                  <span><Icon name="coin" size={12} /> {fare.toFixed(2)} DT</span>
                {/if}
              </div>

              {#if selectedItinerary === i && (itin.legs?.length ?? 0) > 0}
                <ol class="steps">
                  {#each (itin.legs as unknown as Leg[]) as leg}
                    {@const walk = (leg.type ?? "").toLowerCase() === "walk"}
                    <li class="step" style="--c:{walk ? '#94a3b8' : modeColor(leg.mode ?? 'bus')}">
                      <span class="s-ic"><Icon name={walk ? "walk" : modeIcon(leg.mode ?? "bus")} size={12} /></span>
                      <span class="s-tx">
                        {legLabel(leg)}
                      </span>
                      {#if leg.duration_min}
                        <span class="s-d">{Math.round(leg.duration_min)}′</span>
                      {/if}
                    </li>
                  {/each}
                </ol>
              {/if}
            </button>
          {/each}
        </section>
      {:else if routePlan}
        <div class="alert warn">
          <Icon name="alert" size={15} />
          <span>{t("results.none")}</span>
        </div>
      {/if}
    </aside>

    <!-- ── Map ────────────────────────────────────────────────────────────── -->
    <main class="map-wrap">
      <div bind:this={mapEl} class="map"></div>

      {#if loadingStations}
        <div class="float">
          <span class="spin"></span> {t("loading.stations")}
        </div>
      {/if}

      <div class="legend">
        <p class="lg-h"><Icon name="layers" size={12} /> {t("legend.title")}</p>
        <div class="lg-grid">
          {#each MODES as m}
            <span class="lg-i" class:off={!isOn(m.id)}>
              <i style="background:{m.color}"></i>
              {t("modes." + m.id)}
            </span>
          {/each}
        </div>
      </div>
    </main>
  </div>
</div>

<style>
  /* ── Design tokens (GitHub-dark lineage, refined) ───────────────────────── */
  .app {
    --bg: #080d17;
    --panel: #0d1524;
    --panel-2: #111c30;
    --line: #1b2a44;
    --line-soft: #16233a;
    --tx: #e8eef7;
    --tx-2: #a3b3c9;
    --tx-3: #8496ae;
    --accent: #22d3ee;
    --accent-2: #06b6d4;
    --radius: 12px;

    display: flex;
    flex-direction: column;
    height: 100vh;
    height: 100dvh;
    background: var(--bg);
    color: var(--tx);
    font-size: 14px;
    line-height: 1.5;
    overflow: hidden;
  }

  /* ── Header ─────────────────────────────────────────────────────────────── */
  .hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 16px;
    background: linear-gradient(180deg, #0d1524, #0a1120);
    border-bottom: 1px solid var(--line);
    flex-shrink: 0;
  }
  .brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .brand-mark {
    display: grid;
    place-items: center;
    width: 34px; height: 34px;
    border-radius: 10px;
    background: linear-gradient(140deg, var(--accent), #0891b2);
    color: #04121a;
    box-shadow: 0 4px 16px rgba(34, 211, 238, 0.22);
    flex-shrink: 0;
  }
  .brand-text { display: flex; flex-direction: column; min-width: 0; }
  .brand-text strong { font-size: 15px; letter-spacing: -0.2px; }
  .brand-text .dot { color: var(--accent); }
  .brand-text small { color: var(--tx-3); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .hdr-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  .chip {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 9px;
    border: 1px solid var(--line);
    border-radius: 999px;
    background: rgba(17, 28, 48, 0.6);
    color: var(--tx-2);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
  }
  .chip-accent { border-color: rgba(34, 211, 238, 0.35); color: var(--accent); background: rgba(34, 211, 238, 0.08); }
  .chip em { font-style: normal; color: var(--tx-3); }
  .chip-accent em { color: inherit; opacity: 0.7; }

  .langs { display: flex; gap: 2px; padding: 2px; border: 1px solid var(--line); border-radius: 9px; background: rgba(8, 13, 23, 0.7); }
  .lang {
    min-width: 30px; min-height: 26px;
    border: 0; border-radius: 7px;
    background: transparent; color: var(--tx-3);
    font: inherit; font-size: 11px; font-weight: 700;
    cursor: pointer;
    transition: background 0.16s ease, color 0.16s ease;
  }
  .lang:hover { color: var(--tx); background: rgba(148, 163, 184, 0.1); }
  .lang.on { background: var(--accent); color: #04121a; }

  /* ── Layout ─────────────────────────────────────────────────────────────── */
  .body { display: flex; flex: 1; min-height: 0; }

  .side {
    width: 344px;
    flex-shrink: 0;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 14px;
    background: var(--panel);
    border-inline-end: 1px solid var(--line);
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  /* ── Sections ───────────────────────────────────────────────────────────── */
  .sec { display: flex; flex-direction: column; gap: 8px; }
  .sec-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  h2 {
    margin: 0;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--tx-3);
  }
  .sub { font-size: 10px; color: var(--tx-3); }

  .ghost {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 6px 9px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: rgba(17, 28, 48, 0.5);
    color: var(--accent);
    font: inherit; font-size: 11px; font-weight: 600;
    cursor: pointer;
    transition: border-color 0.16s ease, background 0.16s ease;
  }
  .ghost:hover:not(:disabled) { border-color: rgba(34, 211, 238, 0.5); background: rgba(34, 211, 238, 0.08); }
  .ghost:disabled { opacity: 0.55; cursor: default; }

  .mini-actions { display: inline-flex; align-items: center; gap: 4px; }
  .mini {
    border: 0; background: none; padding: 2px 4px;
    color: var(--tx-3); font: inherit; font-size: 10.5px; font-weight: 600;
    cursor: pointer; border-radius: 5px;
    transition: color 0.16s ease;
  }
  .mini:hover { color: var(--accent); }
  .sep { color: var(--line); }

  /* ── Place search ───────────────────────────────────────────────────────── */
  .search { display: flex; flex-direction: column; gap: 7px; position: relative; }
  .search-row {
    display: flex; align-items: center; gap: 8px;
    padding: 0 10px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: #070c15;
    transition: border-color 0.16s ease, box-shadow 0.16s ease;
  }
  .search-row:focus-within { border-color: var(--accent-2); box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.13); }
  .search-row :global(svg.s-ic) { color: var(--tx-3); flex-shrink: 0; }
  .search-row input {
    flex: 1; min-width: 0;
    min-height: 36px;
    border: 0; background: none; outline: none;
    color: var(--tx); font: inherit; font-size: 12.5px;
  }
  .search-row input::placeholder { color: #4a5b76; }
  .spin.dark { border-color: rgba(34, 211, 238, 0.25); border-top-color: var(--accent); }

  .targets { display: flex; gap: 6px; }
  .tgt {
    display: inline-flex; align-items: center; gap: 6px;
    flex: 1;
    min-height: 32px; padding: 5px 9px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: rgba(17, 28, 48, 0.45);
    color: var(--tx-3);
    font: inherit; font-size: 11px; font-weight: 600;
    cursor: pointer;
    transition: all 0.16s ease;
  }
  .tgt:hover { border-color: #24354f; color: var(--tx-2); }
  .tgt.on { border-color: rgba(34, 211, 238, 0.5); background: rgba(34, 211, 238, 0.09); color: var(--accent); }
  .badge.sm { width: 17px; height: 17px; font-size: 9px; }

  .hits {
    list-style: none; margin: 0; padding: 4px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: #0a1220;
    display: flex; flex-direction: column; gap: 2px;
    max-height: 208px; overflow-y: auto;
  }
  .hit {
    display: flex; align-items: center; gap: 8px;
    width: 100%; padding: 7px 8px;
    border: 0; border-radius: 7px;
    background: none; color: var(--tx-2);
    font: inherit; font-size: 11.5px; text-align: start;
    cursor: pointer;
    transition: background 0.14s ease, color 0.14s ease;
  }
  .hit:hover { background: rgba(34, 211, 238, 0.1); color: var(--tx); }
  .hit :global(svg) { color: var(--accent); flex-shrink: 0; }
  .hit-tx { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .no-hit { margin: 0; padding: 2px 4px; color: var(--tx-3); font-size: 11px; }

  /* ── Trip fields ────────────────────────────────────────────────────────── */
  .field { display: flex; align-items: center; gap: 9px; }
  .badge {
    display: grid; place-items: center;
    width: 25px; height: 25px; flex-shrink: 0;
    border-radius: 50%;
    font-size: 10.5px; font-weight: 800; color: #04121a;
  }
  .badge.a { background: var(--accent); }
  .badge.b { background: #f472b6; }
  .inputs { display: flex; gap: 7px; flex: 1; min-width: 0; }
  .inputs input {
    width: 100%; min-width: 0; min-height: 34px;
    padding: 6px 9px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: #070c15;
    color: var(--tx);
    font: inherit; font-size: 12px;
    font-variant-numeric: tabular-nums;
    outline: none;
    transition: border-color 0.16s ease, box-shadow 0.16s ease;
  }
  .inputs input:focus { border-color: var(--accent-2); box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.13); }

  /* ── Priority ───────────────────────────────────────────────────────────── */
  .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
  .opt {
    display: flex; flex-direction: column; align-items: center; gap: 5px;
    min-height: 56px; padding: 8px 4px;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: rgba(17, 28, 48, 0.45);
    color: var(--tx-3);
    font: inherit; font-size: 10px; font-weight: 600; text-align: center;
    cursor: pointer;
    transition: all 0.16s ease;
  }
  .opt:hover { border-color: #24354f; color: var(--tx-2); }
  .opt.on {
    border-color: rgba(34, 211, 238, 0.55);
    background: rgba(34, 211, 238, 0.1);
    color: var(--accent);
    box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.12);
  }
  .opt span { line-height: 1.25; }

  /* ── Modes ──────────────────────────────────────────────────────────────── */
  .grid2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
  .mode {
    display: flex; align-items: center; gap: 7px;
    min-height: 40px; padding: 7px 9px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: rgba(17, 28, 48, 0.45);
    color: var(--tx-3);
    font: inherit; font-size: 11.5px; font-weight: 600;
    cursor: pointer;
    transition: all 0.16s ease;
  }
  .mode:hover { border-color: #24354f; color: var(--tx-2); }
  .mode.on { background: rgba(30, 45, 71, 0.75); border-color: #2c3f5c; color: var(--tx); }
  .tick {
    display: grid; place-items: center;
    width: 15px; height: 15px; flex-shrink: 0;
    border: 1.5px solid #2c3f5c;
    border-radius: 5px;
    color: #04121a;
    transition: background 0.16s ease, border-color 0.16s ease;
  }
  .m-ic { display: grid; place-items: center; color: var(--tx-3); transition: color 0.16s ease; }
  .m-lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* ── CTA ────────────────────────────────────────────────────────────────── */
  .cta {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    width: 100%; min-height: 46px;
    border: 0; border-radius: 11px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #04121a;
    font: inherit; font-size: 13.5px; font-weight: 800;
    cursor: pointer;
    box-shadow: 0 6px 20px rgba(34, 211, 238, 0.2);
    transition: transform 0.12s ease, box-shadow 0.16s ease, filter 0.16s ease;
  }
  .cta:hover:not(:disabled) { filter: brightness(1.07); box-shadow: 0 8px 26px rgba(34, 211, 238, 0.28); }
  .cta:active:not(:disabled) { transform: scale(0.985); }
  .cta:disabled { opacity: 0.45; cursor: not-allowed; box-shadow: none; }

  .spin {
    width: 13px; height: 13px;
    border: 2px solid rgba(4, 18, 26, 0.3);
    border-top-color: #04121a;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Alerts ─────────────────────────────────────────────────────────────── */
  .alert {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 9px 11px;
    border: 1px solid rgba(248, 113, 113, 0.3);
    border-radius: 9px;
    background: rgba(127, 29, 29, 0.22);
    color: #fca5a5;
    font-size: 11.5px; line-height: 1.45;
  }
  .alert.warn { border-color: rgba(251, 191, 36, 0.3); background: rgba(120, 53, 15, 0.2); color: #fcd34d; }
  .alert svg { flex-shrink: 0; margin-top: 1px; }

  /* ── Results ────────────────────────────────────────────────────────────── */
  .results { gap: 7px; }
  .itin {
    display: flex; flex-direction: column; gap: 7px;
    width: 100%; padding: 11px;
    border: 1px solid var(--line);
    border-radius: 11px;
    background: rgba(17, 28, 48, 0.5);
    color: inherit;
    font: inherit; text-align: start;
    cursor: pointer;
    transition: all 0.16s ease;
  }
  .itin:hover { border-color: #2c3f5c; }
  .itin.on {
    border-color: rgba(34, 211, 238, 0.5);
    background: rgba(23, 38, 62, 0.9);
    box-shadow: 0 5px 20px rgba(34, 211, 238, 0.09);
  }
  .it-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
  .it-n { font-size: 10.5px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--tx-3); }
  .it-dur { font-size: 17px; font-weight: 800; color: var(--tx); font-variant-numeric: tabular-nums; letter-spacing: -0.3px; }
  .itin.on .it-dur { color: var(--accent); }

  .it-pills { display: flex; flex-wrap: wrap; gap: 4px; }
  .pill {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 7px;
    border-radius: 5px;
    color: #04070f;
    font-size: 10px; font-weight: 700;
  }
  .it-meta { display: flex; align-items: center; gap: 12px; color: var(--tx-3); font-size: 11px; }
  .it-meta span { display: inline-flex; align-items: center; gap: 4px; }

  .steps {
    list-style: none; margin: 3px 0 0; padding: 8px 0 0;
    border-top: 1px dashed var(--line-soft);
    display: flex; flex-direction: column; gap: 6px;
  }
  .step { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--tx-2); }
  .s-ic {
    display: grid; place-items: center;
    width: 21px; height: 21px; flex-shrink: 0;
    border-radius: 6px;
    background: color-mix(in srgb, var(--c) 18%, transparent);
    color: var(--c);
  }
  .s-tx { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .s-d { color: var(--tx-3); font-variant-numeric: tabular-nums; }

  /* ── Map ────────────────────────────────────────────────────────────────── */
  .map-wrap { position: relative; flex: 1; min-width: 0; }
  .map { position: absolute; inset: 0; }

  .float {
    position: absolute;
    top: 14px; left: 50%;
    transform: translateX(-50%);
    display: flex; align-items: center; gap: 8px;
    padding: 7px 13px;
    border: 1px solid var(--line);
    border-radius: 999px;
    background: rgba(13, 21, 36, 0.92);
    backdrop-filter: blur(10px);
    color: var(--tx-2);
    font-size: 11.5px;
    box-shadow: 0 8px 26px rgba(0, 0, 0, 0.5);
    pointer-events: none;
    z-index: 500;
  }
  .float .spin { border-color: rgba(34, 211, 238, 0.25); border-top-color: var(--accent); }

  .legend {
    position: absolute;
    bottom: 14px; inset-inline-start: 14px;
    z-index: 500;
    padding: 9px 11px;
    border: 1px solid var(--line);
    border-radius: 11px;
    background: rgba(13, 21, 36, 0.92);
    backdrop-filter: blur(10px);
    box-shadow: 0 8px 26px rgba(0, 0, 0, 0.5);
    max-width: min(260px, calc(100% - 28px));
  }
  .lg-h {
    display: flex; align-items: center; gap: 5px;
    margin: 0 0 7px;
    font-size: 9.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--tx-3);
  }
  .lg-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 12px; }
  .lg-i {
    display: flex; align-items: center; gap: 6px;
    font-size: 10.5px; color: var(--tx-2);
    transition: opacity 0.16s ease;
  }
  .lg-i i { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .lg-i.off { opacity: 0.35; text-decoration: line-through; }

  /* ── Scrollbar ──────────────────────────────────────────────────────────── */
  .side::-webkit-scrollbar { width: 8px; }
  .side::-webkit-scrollbar-track { background: transparent; }
  .side::-webkit-scrollbar-thumb { background: #1b2a44; border-radius: 4px; border: 2px solid var(--panel); }
  .side::-webkit-scrollbar-thumb:hover { background: #2c3f5c; }

  /* ── Focus visibility (keyboard nav) ────────────────────────────────────── */
  .app :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    border-radius: 8px;
  }

  /* ── Responsive ─────────────────────────────────────────────────────────── */
  @media (max-width: 900px) {
    .body { flex-direction: column; }
    .side {
      width: 100%;
      max-height: 46vh;
      border-inline-end: 0;
      border-bottom: 1px solid var(--line);
    }
    .map-wrap { flex: 1; min-height: 40vh; }
    .brand-text small { display: none; }
  }
  @media (max-width: 420px) {
    .grid3 { grid-template-columns: 1fr; }
    .hdr { padding: 9px 12px; }
  }

  /* ── Reduced motion ─────────────────────────────────────────────────────── */
  @media (prefers-reduced-motion: reduce) {
    .app *, .app *::before, .app *::after {
      animation-duration: 0.001ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.001ms !important;
    }
  }
</style>
