<script lang="ts">
  import { onMount } from "svelte";
  import L from "leaflet";
  import Icon from "$lib/Icon.svelte";
  import { api, type RoutePlan, type Station } from "$lib/router";
  import { LANGS, translator, dirOf, formatDuration, modeLabel, type Lang } from "$lib/i18n";

  // ── Transport modes ───────────────────────────────────────────────────────
  // Colour per mode so the selection state is readable at a glance. Modes are
  // the ones the backend actually serves (docs/master-plan.md lists taxi among
  // the core modes; the API returns it).
  const MODES = [
    { id: "bus", icon: "bus", color: "#ef4444" },
    { id: "metro", icon: "metro", color: "#3b82f6" },
    { id: "tram", icon: "tram", color: "#f59e0b" },
    { id: "train", icon: "train", color: "#8b5cf6" },
    { id: "rfr", icon: "rfr", color: "#f97316" },
    { id: "louaj", icon: "louaj", color: "#10b981" },
    { id: "taxi", icon: "taxi", color: "#eab308" },
    { id: "walk", icon: "walk", color: "#94a3b8" },
  ] as const;

  type ModeId = (typeof MODES)[number]["id"];

  // Defaults match the most common Tunisian public-transport combination:
  // scheduled modes on, informal modes (louage/taxi) and walking off.
  const DEFAULT_ON: ModeId[] = ["bus", "metro", "tram", "train", "rfr"];

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

  // Per-mode selection. A Set of ids keeps the count trivial and makes
  // "is this on?" a single lookup.
  let selected = $state<Set<ModeId>>(new Set(DEFAULT_ON));

  let objective = $state<string>("fastest");
  let routePlan: RoutePlan | null = $state(null);
  let computing = $state(false);
  let selectedItinerary = $state(0);
  let locating = $state(false);
  let resultsEl: HTMLElement | null = $state(null);
  let toast = $state("");

  // Place search
  type Geo = { lat: number; lon: number; display_name: string };
  let query = $state("");
  let results = $state<Geo[]>([]);
  let searching = $state(false);
  let target: "from" | "to" = $state("to");
  let searchTimer: ReturnType<typeof setTimeout> | null = null;
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  function isOn(id: ModeId): boolean {
    return selected.has(id);
  }

  function toggleMode(id: ModeId) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selected = next;
    refreshStations();
  }

  function setAll(on: boolean) {
    selected = on ? new Set(MODES.map((m) => m.id)) : new Set();
    refreshStations();
  }

  const count = $derived(selected.size);
  const total = MODES.length;

  function showToast(msg: string) {
    toast = msg;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = ""), 4000);
  }

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
      preferCanvas: true,
    });
    L.control.zoom({ position: "bottomright" }).addTo(map);

    // Esri "World Dark Gray" — a real cartographic dark basemap, no API key.
    // Previously this used OSM tiles with an invert()/hue-rotate CSS filter,
    // which turns road colours muddy and makes labels hard to read.
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 16, attribution: "Esri, HERE, Garmin, © OpenStreetMap contributors" }
    ).addTo(map);
    // Labels on a separate reference layer so they stay crisp above the base.
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 16, pane: "shadowPane" }
    ).addTo(map);

    stationLayer = L.layerGroup().addTo(map);
    routeLayer = L.layerGroup().addTo(map);
  }

  function stationIcon(mode: string) {
    const c = modeColor(mode);
    return L.divIcon({
      className: "",
      html: `<span style="display:block;width:9px;height:9px;border-radius:50%;
        background:${c};border:1.5px solid rgba(3,7,14,.9);
        box-shadow:0 0 0 2px ${c}2e;"></span>`,
      iconSize: [9, 9],
      iconAnchor: [4.5, 4.5],
    });
  }

  function endpointIcon(label: string, color: string) {
    return L.divIcon({
      className: "",
      html: `<span style="display:flex;width:30px;height:30px;border-radius:50%;
        align-items:center;justify-content:center;
        background:${color};color:#04070f;font-weight:800;font-size:13px;
        border:2.5px solid #f1f5fb;box-shadow:0 3px 16px rgba(0,0,0,.75);">${label}</span>`,
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    });
  }

  function refreshStations() {
    if (!map || !stationLayer) return;
    stationLayer.clearLayers();
    const visible = stations.filter((s) => selected.has(s.mode as ModeId));
    const MAX = 700;
    const step = Math.max(1, Math.ceil(visible.length / MAX));
    for (let i = 0; i < visible.length; i += step) {
      const s = visible[i];
      L.marker([s.lat, s.lon], { icon: stationIcon(s.mode), title: s.name })
        .bindTooltip(`<b>${s.name}</b>`, { direction: "top", offset: [0, -6] })
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
      if (!leg.geometry || leg.geometry.length < 2) continue;
      const isWalk = (leg.type ?? "").toLowerCase() === "walk";
      const pts = leg.geometry.map(([a, b]) => [a, b] as [number, number]);
      const color = isWalk ? "#94a3b8" : modeColor(leg.mode ?? "bus");
      // Casing keeps the route legible over same-coloured station dots.
      if (!isWalk) {
        L.polyline(pts, { color: "#04080f", weight: 9, opacity: 0.85, lineCap: "round" }).addTo(routeLayer);
      }
      L.polyline(pts, {
        color,
        weight: isWalk ? 3 : 5,
        opacity: isWalk ? 0.85 : 1,
        dashArray: isWalk ? "2 7" : undefined,
        lineCap: "round",
        lineJoin: "round",
      }).addTo(routeLayer);
    }

    const all: [number, number][] = [];
    for (const l of legs) if (l.geometry) all.push(...l.geometry);
    if (all.length) map.fitBounds(L.latLngBounds(all).pad(0.18));
  }

  async function computeRoute() {
    // Zero modes: the button is disabled, but keep the guard so a keyboard
    // activation or a stale click still gets an explanation.
    if (selected.size === 0) {
      showToast(t("error.noModes"));
      return;
    }
    computing = true;
    routePlan = null;
    error = "";
    try {
      const sLat = parseFloat(startLat), sLon = parseFloat(startLon);
      const eLat = parseFloat(endLat), eLon = parseFloat(endLon);
      if ([sLat, sLon, eLat, eLon].some(isNaN)) throw new Error(t("error.coords"));

      const modesInclude = MODES.filter((m) => isOn(m.id)).map((m) => m.id).join(",");
      placeEndpoints();
      const plan = await api.routePlan({
        startLat: sLat, startLon: sLon, endLat: eLat, endLon: eLon,
        modesInclude, objective,
      });
      routePlan = plan;
      selectedItinerary = 0;
      if (plan.itineraries?.length) {
        drawItinerary(plan.itineraries[0]);
        requestAnimationFrame(() =>
          resultsEl?.scrollIntoView({ behavior: "smooth", block: "start" })
        );
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      computing = false;
    }
  }

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

  function useMyLocation() {
    if (!navigator.geolocation) { showToast(t("error.geoUnsupported")); return; }
    locating = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        startLat = pos.coords.latitude.toFixed(5);
        startLon = pos.coords.longitude.toFixed(5);
        locating = false;
        placeEndpoints();
        map?.setView([pos.coords.latitude, pos.coords.longitude], 14);
      },
      () => { locating = false; showToast(t("error.geo")); },
      { timeout: 10000 }
    );
  }

  /** Fare field differs across API versions; read whichever is present. */
  function fareOf(itin: Record<string, unknown>): number {
    const v = itin.fare_estimate_dinars ?? itin.fare_dinars ?? 0;
    return typeof v === "number" ? v : 0;
  }

  /** Human-readable step label; `line` is an internal id like "rail_19_a". */
  function legLabel(leg: Leg): string {
    if ((leg.type ?? "").toLowerCase() === "walk") return t("step.walk");
    const base = modeLabel(t, leg.mode ?? "bus");
    const m = (leg.line ?? "").match(/(\d+[A-Za-z]?)/);
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
      <span class="brand-mark" aria-hidden="true"><Icon name="route" size={18} /></span>
      <span class="brand-text">
        <strong>Bledi<span class="dot">.tn</span></strong>
        <small>{t("app.tagline")}</small>
      </span>
    </div>
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
  </header>

  <div class="body">
    <!-- ── Panel column: scrollable content + pinned action footer ── -->
    <div class="panel-col">
    <!-- ── Panel ─────────────────────────────────────────────────────────── -->
    <aside class="side">
      <!-- Search -->
      <section class="sec">
        <div class="search-row">
          <Icon name="search" size={15} cls="s-ic" />
          <input
            bind:value={query}
            oninput={onQueryInput}
            placeholder={t("search.placeholder")}
            aria-label={t("search.placeholder")}
          />
          {#if searching}<span class="spin" aria-hidden="true"></span>{/if}
        </div>

        <div class="targets" role="group" aria-label={t("search.usePlace")}>
          <button class="tgt" class:on={target === "from"} onclick={() => (target = "from")} aria-pressed={target === "from"}>
            <span class="badge a sm">A</span>{t("trip.from")}
          </button>
          <button class="tgt" class:on={target === "to"} onclick={() => (target = "to")} aria-pressed={target === "to"}>
            <span class="badge b sm">B</span>{t("trip.to")}
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

        <button class="ghost" onclick={useMyLocation} disabled={locating}>
          <Icon name="locate" size={14} />
          {locating ? t("trip.locating") : t("trip.myLocation")}
        </button>

        <!-- Coordinates -->
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
            <button class="opt" class:on={objective === o.id} onclick={() => (objective = o.id)} aria-pressed={objective === o.id}>
              <Icon name={o.icon} size={16} />
              <span>{t("priority." + o.id)}</span>
            </button>
          {/each}
        </div>
      </section>

      <!-- Modes: counter + bulk actions -->
      <section class="sec">
        <div class="sec-head">
          <h2>
            {t("modes.title")}
            <span class="counter" class:zero={count === 0}>{count}/{total}</span>
          </h2>
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
              style={isOn(m.id) ? `--mc:${m.color}` : ""}
            >
              <span class="tick" style={isOn(m.id) ? `background:${m.color};border-color:${m.color}` : ""}>
                {#if isOn(m.id)}<Icon name="check" size={11} stroke={3.4} />{/if}
              </span>
              <span class="m-ic"><Icon name={m.icon} size={17} /></span>
              <span class="m-lbl">{modeLabel(t, m.id)}</span>
            </button>
          {/each}
        </div>
        {#if count === 0}
          <p class="hint-warn" role="status">
            <Icon name="alert" size={13} /> {t("error.noModes")}
          </p>
        {/if}
      </section>

      {#if error}
        <div class="alert" role="alert">
          <Icon name="alert" size={15} /><span>{error}</span>
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
                    <Icon name={modeIcon(mu)} size={11} stroke={2.2} />{modeLabel(t, mu)}
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
                {#if fare > 0}<span><Icon name="coin" size={12} /> {fare.toFixed(2)} DT</span>{/if}
              </div>
              {#if selectedItinerary === i && (itin.legs?.length ?? 0) > 0}
                <ol class="steps">
                  {#each (itin.legs as unknown as Leg[]) as leg}
                    {@const walk = (leg.type ?? "").toLowerCase() === "walk"}
                    <li class="step" style="--c:{walk ? '#94a3b8' : modeColor(leg.mode ?? 'bus')}">
                      <span class="s-ic"><Icon name={walk ? "walk" : modeIcon(leg.mode ?? "bus")} size={12} /></span>
                      <span class="s-tx">{legLabel(leg)}</span>
                      {#if leg.duration_min}<span class="s-d">{Math.round(leg.duration_min)}′</span>{/if}
                    </li>
                  {/each}
                </ol>
              {/if}
            </button>
          {/each}
        </section>
      {:else if routePlan}
        <div class="alert warn" role="status">
          <Icon name="alert" size={15} /><span>{t("results.none")}</span>
        </div>
      {/if}
    </aside>

    <!-- Primary action: a footer of the panel column, OUTSIDE the scroll
         container so it can never scroll out of reach. -->
    <div class="cta-bar">
      <button class="cta" onclick={computeRoute} disabled={computing || count === 0}>
        {#if computing}
          <span class="spin dark" aria-hidden="true"></span> {t("action.calculating")}
        {:else}
          <Icon name="search" size={17} /> {t("action.calculate")}
        {/if}
      </button>
    </div>

    </div><!-- /.panel-col -->

    <!-- ── Map ────────────────────────────────────────────────────────────── -->
    <main class="map-wrap">
      <div bind:this={mapEl} class="map"></div>

      {#if loadingStations}
        <div class="float"><span class="spin dark"></span> {t("loading.stations")}</div>
      {/if}

      <div class="legend">
        <div class="lg-grid">
          {#each MODES as m}
            <span class="lg-i" class:off={!isOn(m.id)}>
              <i style="background:{m.color}"></i>{modeLabel(t, m.id)}
            </span>
          {/each}
        </div>
      </div>
    </main>
  </div>

  {#if toast}
    <div class="toast" role="alert">{toast}</div>
  {/if}
</div>

<style>
  /* ── Tokens ─────────────────────────────────────────────────────────────── */
  .app {
    --bg: #070b14;
    --panel: #0c1422;
    --panel-2: #121d31;
    --line: #1a2942;
    --tx: #eaf1fa;
    --tx-2: #9fb0c8;
    --tx-3: #7e91ab;
    --accent: #22d3ee;
    --accent-2: #06b6d4;

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
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    padding: 9px 14px;
    background: linear-gradient(180deg, #0c1422, #080f1b);
    border-bottom: 1px solid var(--line);
    flex-shrink: 0;
  }
  .brand { display: flex; align-items: center; gap: 9px; min-width: 0; }
  .brand-mark {
    display: grid; place-items: center;
    width: 32px; height: 32px; flex-shrink: 0;
    border-radius: 10px;
    background: linear-gradient(140deg, var(--accent), #0891b2);
    color: #04121a;
    box-shadow: 0 4px 14px rgba(34, 211, 238, 0.2);
  }
  .brand-text { display: flex; flex-direction: column; min-width: 0; }
  .brand-text strong { font-size: 15px; letter-spacing: -0.2px; }
  .brand-text .dot { color: var(--accent); }
  .brand-text small { color: var(--tx-3); font-size: 10.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .langs { display: flex; gap: 2px; padding: 2px; border: 1px solid var(--line); border-radius: 9px; background: rgba(7, 11, 20, 0.7); flex-shrink: 0; }
  .lang {
    min-width: 32px; min-height: 27px;
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
  /* Panel column: the scrollable content and the pinned action footer are
     SIBLINGS in a flex column, so the footer is laid out after the scroll area
     rather than inside it and cannot scroll out of reach. */
  .panel-col {
    display: flex;
    flex-direction: column;
    width: 340px; flex-shrink: 0;
    min-height: 0;
    background: var(--panel);
    border-inline-end: 1px solid var(--line);
  }
  .side {
    flex: 1;
    min-height: 0;
    overflow-y: auto; overflow-x: hidden;
    padding: 12px;
    display: flex; flex-direction: column; gap: 12px;
  }

  /* ── Sections ───────────────────────────────────────────────────────────── */
  .sec { display: flex; flex-direction: column; gap: 8px; }
  .sec-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  h2 {
    display: flex; align-items: center; gap: 6px;
    margin: 0;
    font-size: 10.5px; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--tx-3);
  }
  .counter {
    padding: 1px 6px;
    border: 1px solid var(--line);
    border-radius: 999px;
    background: rgba(34, 211, 238, 0.08);
    color: var(--accent);
    font-size: 10px; font-weight: 700;
    letter-spacing: 0;
    font-variant-numeric: tabular-nums;
  }
  .counter.zero { border-color: rgba(248, 113, 113, 0.4); background: rgba(127, 29, 29, 0.25); color: #fca5a5; }
  .sub { font-size: 10px; color: var(--tx-3); }

  .mini-actions { display: inline-flex; align-items: center; gap: 4px; }
  .mini {
    border: 0; background: none; padding: 2px 4px;
    color: var(--tx-3); font: inherit; font-size: 10.5px; font-weight: 600;
    cursor: pointer; border-radius: 5px;
    transition: color 0.16s ease;
  }
  .mini:hover { color: var(--accent); }
  .sep { color: var(--line); }

  /* ── Search ─────────────────────────────────────────────────────────────── */
  .search-row {
    display: flex; align-items: center; gap: 8px;
    padding: 0 10px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: #05090f;
    transition: border-color 0.16s ease, box-shadow 0.16s ease;
  }
  .search-row:focus-within { border-color: var(--accent-2); box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.12); }
  .search-row :global(svg.s-ic) { color: var(--tx-3); flex-shrink: 0; }
  .search-row input {
    flex: 1; min-width: 0; min-height: 37px;
    border: 0; background: none; outline: none;
    color: var(--tx); font: inherit; font-size: 12.5px;
  }
  .search-row input::placeholder { color: #4d5f79; }

  .targets { display: flex; gap: 6px; }
  .tgt {
    display: inline-flex; align-items: center; gap: 6px;
    flex: 1; min-height: 33px; padding: 5px 9px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: rgba(18, 29, 49, 0.45);
    color: var(--tx-3);
    font: inherit; font-size: 11px; font-weight: 600;
    cursor: pointer;
    transition: all 0.16s ease;
  }
  .tgt:hover { border-color: #24354f; color: var(--tx-2); }
  .tgt.on { border-color: rgba(34, 211, 238, 0.5); background: rgba(34, 211, 238, 0.09); color: var(--accent); }

  .hits {
    list-style: none; margin: 0; padding: 4px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: #070d18;
    display: flex; flex-direction: column; gap: 2px;
    max-height: 200px; overflow-y: auto;
  }
  .hit {
    display: flex; align-items: center; gap: 8px;
    width: 100%; padding: 8px;
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

  .ghost {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    min-height: 36px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: rgba(18, 29, 49, 0.5);
    color: var(--accent);
    font: inherit; font-size: 11.5px; font-weight: 600;
    cursor: pointer;
    transition: border-color 0.16s ease, background 0.16s ease;
  }
  .ghost:hover:not(:disabled) { border-color: rgba(34, 211, 238, 0.5); background: rgba(34, 211, 238, 0.08); }
  .ghost:disabled { opacity: 0.55; cursor: default; }

  /* ── Coordinates ────────────────────────────────────────────────────────── */
  .field { display: flex; align-items: center; gap: 9px; }
  .badge {
    display: grid; place-items: center;
    width: 25px; height: 25px; flex-shrink: 0;
    border-radius: 50%;
    font-size: 10.5px; font-weight: 800; color: #04121a;
  }
  .badge.a { background: var(--accent); }
  .badge.b { background: #f472b6; }
  .badge.sm { width: 17px; height: 17px; font-size: 9px; }
  .inputs { display: flex; gap: 7px; flex: 1; min-width: 0; }
  .inputs input {
    width: 100%; min-width: 0; min-height: 35px;
    padding: 6px 9px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: #05090f;
    color: var(--tx);
    font: inherit; font-size: 12px;
    font-variant-numeric: tabular-nums;
    outline: none;
    transition: border-color 0.16s ease, box-shadow 0.16s ease;
  }
  .inputs input:focus { border-color: var(--accent-2); box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.12); }

  /* ── Priority ───────────────────────────────────────────────────────────── */
  .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
  .opt {
    display: flex; flex-direction: column; align-items: center; gap: 5px;
    min-height: 58px; padding: 8px 4px;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: rgba(18, 29, 49, 0.45);
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
    min-height: 42px; padding: 7px 9px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: rgba(18, 29, 49, 0.4);
    color: var(--tx-3);
    font: inherit; font-size: 11.5px; font-weight: 600;
    cursor: pointer;
    transition: all 0.16s ease;
  }
  .mode:hover { border-color: #24354f; }
  /* Unchecked modes are greyed out COMPLETELY — border, icon, tick and label
     all drop to a muted grey, not merely losing the checkmark, so the active
     set reads instantly. */
  .mode:not(.on) { background: rgba(12, 20, 34, 0.5); border-color: #142135; color: #55677f; }
  .mode:not(.on) .m-ic { color: #44546a; opacity: 0.65; }
  .mode:not(.on) .m-lbl { opacity: 0.6; }
  .mode.on {
    background: color-mix(in srgb, var(--mc) 12%, rgba(18, 29, 49, 0.75));
    border-color: color-mix(in srgb, var(--mc) 45%, transparent);
    color: var(--tx);
  }
  .mode.on .m-ic { color: var(--mc); }

  .tick {
    display: grid; place-items: center;
    width: 16px; height: 16px; flex-shrink: 0;
    border: 1.5px solid #26364f;
    border-radius: 5px;
    color: #04121a;
    transition: background 0.16s ease, border-color 0.16s ease;
  }
  .m-ic { display: grid; place-items: center; flex-shrink: 0; transition: color 0.16s ease; }
  .m-lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .hint-warn {
    display: flex; align-items: center; gap: 6px;
    margin: 0; padding: 7px 9px;
    border: 1px solid rgba(251, 191, 36, 0.3);
    border-radius: 8px;
    background: rgba(120, 53, 15, 0.18);
    color: #fcd34d;
    font-size: 11px;
  }

  /* ── CTA ────────────────────────────────────────────────────────────────── */
  .cta {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    width: 100%; min-height: 48px;
    border: 0; border-radius: 11px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #04121a;
    font: inherit; font-size: 14px; font-weight: 800;
    cursor: pointer;
    box-shadow: 0 6px 20px rgba(34, 211, 238, 0.2);
    transition: transform 0.12s ease, box-shadow 0.16s ease, filter 0.16s ease;
  }
  /* The CTA lives in a bar pinned to the bottom of the panel, outside the
     scrolling area. `position: sticky` was tried first and failed: once the
     panel scrolls past the button's own offset the sticky element leaves the
     viewport entirely (measured ctaTop = -3 after auto-scroll to results),
     so the primary action became unreachable exactly when results arrived.
     A separate non-scrolling bar cannot have that failure mode. */
  .cta-bar {
    flex-shrink: 0;
    padding: 10px 12px 12px;
    background: var(--panel);
    border-top: 1px solid var(--line);
  }
  .cta:hover:not(:disabled) { filter: brightness(1.07); box-shadow: 0 8px 26px rgba(34, 211, 238, 0.28); }
  .cta:active:not(:disabled) { transform: scale(0.985); }
  .cta:disabled { opacity: 0.4; cursor: not-allowed; box-shadow: none; }

  .spin {
    width: 13px; height: 13px; flex-shrink: 0;
    border: 2px solid rgba(148, 163, 184, 0.3);
    border-top-color: var(--tx-2);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  .spin.dark { border-color: rgba(4, 18, 26, 0.3); border-top-color: #04121a; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Alerts / toast ─────────────────────────────────────────────────────── */
  .alert {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 9px 11px;
    border: 1px solid rgba(248, 113, 113, 0.3);
    border-radius: 9px;
    background: rgba(127, 29, 29, 0.2);
    color: #fca5a5;
    font-size: 11.5px; line-height: 1.45;
  }
  .alert.warn { border-color: rgba(251, 191, 36, 0.3); background: rgba(120, 53, 15, 0.18); color: #fcd34d; }
  .alert svg { flex-shrink: 0; margin-top: 1px; }

  .toast {
    position: fixed;
    bottom: 22px; left: 50%;
    transform: translateX(-50%);
    z-index: 2000;
    max-width: min(92vw, 420px);
    padding: 11px 18px;
    border: 1px solid rgba(248, 113, 113, 0.45);
    border-radius: 10px;
    background: rgba(127, 29, 29, 0.95);
    color: #fee2e2;
    font-size: 12.5px; font-weight: 600;
    box-shadow: 0 10px 34px rgba(0, 0, 0, 0.6);
    animation: rise 0.22s ease;
  }
  @keyframes rise { from { opacity: 0; transform: translate(-50%, 12px); } }

  /* ── Results ────────────────────────────────────────────────────────────── */
  .results { gap: 7px; }
  .itin {
    display: flex; flex-direction: column; gap: 7px;
    width: 100%; padding: 11px;
    border: 1px solid var(--line);
    border-radius: 11px;
    background: rgba(18, 29, 49, 0.5);
    color: inherit;
    font: inherit; text-align: start;
    cursor: pointer;
    transition: all 0.16s ease;
  }
  .itin:hover { border-color: #2c3f5c; }
  .itin.on {
    border-color: rgba(34, 211, 238, 0.5);
    background: rgba(22, 36, 60, 0.92);
    box-shadow: 0 5px 20px rgba(34, 211, 238, 0.08);
  }
  .it-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
  .it-n { font-size: 10.5px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--tx-3); }
  .it-dur { font-size: 18px; font-weight: 800; color: var(--tx); font-variant-numeric: tabular-nums; letter-spacing: -0.3px; }
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
    border-top: 1px dashed #16233a;
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
    position: absolute; top: 14px; left: 50%;
    transform: translateX(-50%);
    display: flex; align-items: center; gap: 8px;
    padding: 7px 13px;
    border: 1px solid var(--line);
    border-radius: 999px;
    background: rgba(12, 20, 34, 0.94);
    backdrop-filter: blur(10px);
    color: var(--tx-2);
    font-size: 11.5px;
    box-shadow: 0 8px 26px rgba(0, 0, 0, 0.5);
    pointer-events: none;
    z-index: 500;
  }

  .legend {
    position: absolute;
    bottom: 12px; inset-inline-start: 12px;
    z-index: 500;
    padding: 8px 10px;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: rgba(12, 20, 34, 0.92);
    backdrop-filter: blur(10px);
    box-shadow: 0 8px 26px rgba(0, 0, 0, 0.5);
    max-width: min(250px, calc(100% - 24px));
  }
  .lg-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 3px 12px; }
  .lg-i {
    display: flex; align-items: center; gap: 6px;
    font-size: 10.5px; color: var(--tx-2);
    transition: opacity 0.16s ease;
  }
  .lg-i i { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .lg-i.off { opacity: 0.3; text-decoration: line-through; }

  /* ── Scrollbar / focus ──────────────────────────────────────────────────── */
  .side::-webkit-scrollbar { width: 8px; }
  .side::-webkit-scrollbar-track { background: transparent; }
  .side::-webkit-scrollbar-thumb { background: #1a2942; border-radius: 4px; border: 2px solid var(--panel); }
  .side::-webkit-scrollbar-thumb:hover { background: #2c3f5c; }

  .app :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 8px; }

  /* ── Responsive: mobile-first, panel above map on small screens ─────────── */
  @media (max-width: 860px) {
    .body { flex-direction: column; }
    /* Mobile: the panel column takes the top slice, the map fills the rest.
       The CTA bar stays a footer of the column, so it remains tappable. */
    .panel-col {
      width: 100%;
      max-height: 62vh;
      border-inline-end: 0;
      border-bottom: 1px solid var(--line);
    }
    .side { padding: 10px; }
    .map-wrap { flex: 1; min-height: 34vh; }
  }
  @media (max-width: 400px) {
    .grid3 { grid-template-columns: 1fr; }
    .hdr { padding: 8px 11px; }
    .side { padding: 10px; }
  }

  @media (prefers-reduced-motion: reduce) {
    .app *, .app *::before, .app *::after {
      animation-duration: 0.001ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.001ms !important;
    }
  }
</style>
