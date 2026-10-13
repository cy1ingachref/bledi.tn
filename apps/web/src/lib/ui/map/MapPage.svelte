<script lang="ts">
  import { onMount } from "svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import Alert from "$lib/ui/Alert.svelte";
  import Spinner from "$lib/ui/Spinner.svelte";
  import type {
    Endpoint,
    NetworkSegment,
    Objective,
    RoutePlan,
    Station,
    StationDetail,
    StationsMeta,
    PlaceHit,
    MapOverlayFeature,
    LouageLink,
  } from "$lib/domain/transit";
  import { DEFAULT_MODES, defaultSelection, isStationShown, servedModes } from "$lib/domain/modes";
  import { planTrip, tripProblem } from "$lib/application/planTrip";
  import { loadBaseLayers, loadLouageLinks } from "$lib/application/mapData";
  import { translator, dirOf, modeLabelFor, type Lang } from "$lib/application/i18n";
  import { useTransit } from "$lib/ui/context";
  import { MODE_STYLE } from "$lib/ui/modeStyle";
  import { initTheme, resolvedTheme } from "$lib/ui/theme";
  import { TransitMap } from "./transitMap";
  import AppHeader from "./AppHeader.svelte";
  import PlaceSearch from "./PlaceSearch.svelte";
  import TripOptions from "./TripOptions.svelte";
  import RouteResults from "./RouteResults.svelte";
  import StationInspector from "./StationInspector.svelte";
  import MapLegend from "./MapLegend.svelte";

  const transit = useTransit();

  let mapEl: HTMLDivElement | null = $state(null);
  let tmap: TransitMap | null = null;

  let lang = $state<Lang>("fr");
  const t = $derived(translator(lang));
  const dir = $derived(dirOf(lang));
  const dark = $derived($resolvedTheme);

  let stations = $state<Station[]>([]);
  let stationMeta = $state<StationsMeta>({ count: 0, total: 0, by_mode: {} });
  let loadingStations = $state(true);
  let network = $state<NetworkSegment[]>([]);
  let loadingNetwork = $state(true);
  let error = $state("");

  let baseRail = $state<MapOverlayFeature[]>([]);
  let baseRoads = $state<MapOverlayFeature[]>([]);
  let louageLinks = $state<LouageLink[]>([]);

  let from = $state<Endpoint | null>(null);
  let to = $state<Endpoint | null>(null);
  /** Which endpoint the next map click (or search pick) will fill. */
  let pickMode = $state<"from" | "to" | null>(null);
  let locating = $state(false);

  let selected = $state<Set<string>>(new Set(DEFAULT_MODES));
  let objective = $state<Objective>("fastest");
  let routePlan = $state<RoutePlan | null>(null);
  let computing = $state(false);
  let selectedItinerary = $state(0);
  let resultsEl: HTMLElement | null = $state(null);
  let toast = $state("");
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  let showRoads = $state(true);
  let showRails = $state(true);
  let showUnclassified = $state(false);
  // When a route is on screen, dim everything that is not part of it until the
  // rider asks to see the rest of the network again.
  let focusRoute = $state(true);

  let inspected = $state<StationDetail | null>(null);
  let inspectLoading = $state(false);
  let inspectError = $state("");

  const count = $derived(selected.size);
  const hasRoute = $derived((routePlan?.itineraries?.length ?? 0) > 0);
  const focused = $derived(focusRoute && hasRoute);

  const chips = $derived(
    servedModes(stationMeta.by_mode ?? {}).map((m) => ({ ...m, ...MODE_STYLE[m.id] }))
  );

  const unclassifiedCount = $derived(stationMeta.by_mode?.unclassified ?? 0);
  const shownStops = $derived(
    stations.filter((s) => isStationShown(s, selected, showUnclassified)).length
  );

  function toggleMode(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selected = next;
    refreshStations();
  }

  function setAll(on: boolean) {
    selected = on
      ? new Set(chips.map((c) => c.id))
      : new Set<string>();
    refreshStations();
  }

  function showToast(msg: string) {
    toast = msg;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = ""), 4200);
  }

  function applyNetworkVisibility() {
    tmap?.setNetworkVisibility(showRoads, showRails);
  }

  function buildNetwork() {
    tmap?.drawNetwork(network);
  }

  function buildBaseLayers() {
    tmap?.drawBaseLayers(baseRail, baseRoads);
  }

  /** Centre the map on a station and open its inspector. */
  function focusStation(id: string, name: string) {
    const s = stations.find((x) => x.id === id);
    if (s) tmap?.focus(s.lat, s.lon, 13);
    inspectStation(id, name);
  }

  function refreshStations() {
    tmap?.drawStations(
      stations.filter((s) => isStationShown(s, selected, showUnclassified)),
      (mode) => modeLabelFor(t, mode),
      (s) => inspectStation(s.id, s.name)
    );
  }

  function placeEndpoints() {
    tmap?.placeEndpoints(from, to, { from: t("trip.from"), to: t("trip.to") });
  }

  function onMapClick(lat: number, lon: number) {
    if (!pickMode) return;
    setEndpoint(pickMode, {
      kind: "map",
      name: `${lat.toFixed(4)}, ${lon.toFixed(4)}`,
      lat,
      lon,
    });
    pickMode = null;
  }

  function setEndpoint(which: "from" | "to", ep: Endpoint) {
    if (which === "from") from = ep;
    else to = ep;
    placeEndpoints();
    tmap?.focus(ep.lat, ep.lon, 14);
  }

  function startPick(which: "from" | "to") {
    pickMode = pickMode === which ? null : which;
    if (pickMode) showToast(t("trip.pickHint"));
  }

  function swapEndpoints() {
    const f = from;
    from = to;
    to = f;
    placeEndpoints();
  }

  function useMyLocation() {
    if (!navigator.geolocation) { showToast(t("error.geoUnsupported")); return; }
    locating = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        locating = false;
        setEndpoint("from", {
          kind: "gps",
          name: t("trip.myLocation"),
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
        });
      },
      () => { locating = false; showToast(t("error.geo")); },
      { timeout: 10000 }
    );
  }

  async function inspectStation(id: string, fallbackName = "") {
    inspectLoading = true;
    inspectError = "";
    inspected = {
      id, name: fallbackName, lat: null, lon: null, city: null,
      modes: [], lines: [], count: 0,
    };
    try {
      inspected = await transit.station(id);
    } catch {
      inspectError = t("error.station");
      inspected = null;
    } finally {
      inspectLoading = false;
    }
  }

  /** Fill whichever endpoint is currently targeted from a search hit. */
  function pickHit(h: PlaceHit) {
    const which = pickMode ?? (from ? "to" : "from");
    setEndpoint(which, {
      kind: h.kind,
      name: h.name,
      lat: h.lat,
      lon: h.lon,
      id: h.id,
      modes: h.modes,
    });
    pickMode = null;
  }

  async function computeRoute() {
    const problem = tripProblem(selected, from, to);
    if (problem || !from || !to) {
      showToast(t(problem === "no_modes" ? "error.noModes" : "error.coords"));
      return;
    }
    computing = true;
    routePlan = null;
    error = "";
    inspected = null;
    try {
      const plan = await planTrip(transit, { from, to, selected, objective });
      routePlan = plan;
      selectedItinerary = 0;
      if (plan.itineraries?.length) {
        tmap?.route.draw(plan.itineraries[0], dark);
        focusRoute = true;
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

  function selectItinerary(i: number) {
    selectedItinerary = i;
    const itin = routePlan?.itineraries[i];
    if (itin) tmap?.route.draw(itin, dark);
    focusRoute = true;
  }

  onMount(() => {
    // The inline script in app.html already set data-theme before first paint,
    // so this only syncs the store and wires OS-change following.
    initTheme();

    if (mapEl) tmap = new TransitMap(mapEl, onMapClick);
    tmap?.setBasemap(dark);
    placeEndpoints();

    const unsubTheme = resolvedTheme.subscribe((r) => {
      tmap?.setBasemap(r);
      tmap?.route.setShade(r);
      // Station dots and network strokes take literal colours, so they have to
      // be redrawn to follow the theme.
      refreshStations();
      buildNetwork();
      buildBaseLayers();
    });

    (async () => {
      try {
        const inventory = await transit.stations();
        stations = inventory.stations;
        stationMeta = inventory.meta;
        selected = defaultSelection(inventory.meta.by_mode ?? {});
        refreshStations();
      } catch (e) {
        error = t("error.stations") + ": " + (e instanceof Error ? e.message : String(e));
      } finally {
        loadingStations = false;
      }
    })();

    (async () => {
      try {
        network = await transit.network();
        buildNetwork();
        applyNetworkVisibility();
      } catch {
        error = t("error.network");
      } finally {
        loadingNetwork = false;
      }
    })();

    (async () => {
      const base = await loadBaseLayers(transit);
      baseRail = base.rail;
      baseRoads = base.roads;
      buildBaseLayers();
      louageLinks = await loadLouageLinks(transit);
    })();

    return () => {
      unsubTheme();
      tmap?.destroy();
      tmap = null;
    };
  });

  // Layer toggles re-apply to the live map.
  $effect(() => {
    void showRoads;
    void showRails;
    applyNetworkVisibility();
  });
  $effect(() => {
    void showUnclassified;
    refreshStations();
  });
</script>

<svelte:head>
  <title>Bledi.tn — {t("app.tagline")}</title>
</svelte:head>

<div class="app" dir={dir} lang={lang}>
  <AppHeader bind:lang {t} />

  <div class="body">
    <div class="panel-col">
      <aside class="side">
        <PlaceSearch
          {t}
          {shownStops}
          {pickMode}
          {from}
          {to}
          {locating}
          onStartPick={startPick}
          onPick={pickHit}
          onSwap={swapEndpoints}
          onLocate={useMyLocation}
        />

        <TripOptions
          {t}
          {chips}
          {selected}
          {unclassifiedCount}
          bind:objective
          bind:showRoads
          bind:showRails
          bind:showUnclassified
          onToggleMode={toggleMode}
          onSetAll={setAll}
        />

        {#if error}
          <Alert message={error} />
        {/if}

        {#if routePlan}
          <RouteResults
            {t}
            plan={routePlan}
            selectedIndex={selectedItinerary}
            {focused}
            bind:el={resultsEl}
            onSelect={selectItinerary}
            onToggleFocus={() => (focusRoute = !focusRoute)}
          />
        {/if}
      </aside>

      <!-- Primary action: a footer of the panel column, OUTSIDE the scroll
           container so it can never scroll out of reach. -->
      <div class="cta-bar">
        <button class="cta" onclick={computeRoute} disabled={computing || count === 0}>
          {#if computing}
            <Spinner /> {t("action.calculating")}
          {:else}
            {t("action.calculate")}
          {/if}
        </button>
      </div>
    </div>

    <main class="map-wrap" class:focused>
      <div bind:this={mapEl} class="map"></div>

      {#if loadingStations || loadingNetwork}
        <div class="float">
          <Spinner />
          {loadingStations ? t("loading.stations") : t("loading.network")}
        </div>
      {/if}

      {#if pickMode}
        <div class="pick-banner" role="status">
          <Icon name="crosshair" size={14} />
          {t("trip.pickHint")}
        </div>
      {/if}

      {#if inspected || inspectLoading}
        <StationInspector
          {t}
          station={inspected}
          loading={inspectLoading}
          error={inspectError}
          {louageLinks}
          onClose={() => (inspected = null)}
          onSetEndpoint={setEndpoint}
          onFocusStation={focusStation}
        />
      {/if}

      <MapLegend {t} {chips} {selected} />
    </main>
  </div>

  {#if toast}
    <div class="toast" role="alert">{toast}</div>
  {/if}
</div>

<style>
  /* ── Neon Dusk tokens ────────────────────────────────────────────────────
     Deep violet night with saturated neon for the transport types. Each
     transport owns one hue, declared once as --n-<mode> and reused for the
     mode chip, the network line and the route leg, so a rider only has to
     learn the mapping once. */
  .app {
    --bg: #05030c;
    --surf: rgba(13, 9, 26, 0.74);
    --surf-2: rgba(255, 255, 255, 0.035);
    --line: rgba(150, 120, 255, 0.16);
    --tx: #ece7f7;
    --mu: #8b83a8;
    --mu-2: #635d7d;
    --a1: #ff8ad4;
    --a2: #7b5cff;
    --glow: #3df2c9;
    --casing: #03010a;
    --on-accent: #07030f;

    --n-bus: #ff3d81;
    --n-tram: #ffc400;
    --n-metro: #2f7bff;
    --n-train: #a855f7;
    --n-louaj: #00e5c0;
    --n-walk: #8b83a8;
    --n-unk: #5a5473;

    display: flex;
    flex-direction: column;
    height: 100vh;
    height: 100dvh;
    background: var(--bg);
    color: var(--tx);
    font-family: "DM Sans", ui-sans-serif, system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    overflow: hidden;
    transition: background 0.35s ease, color 0.35s ease;
  }

  /* ── Light theme ─────────────────────────────────────────────────────────
     Daytime variant: a cool off-white ground with the same neon hues
     darkened until they clear WCAG AA against it. Measured in-browser against
     #f6f3ff: bus 5.34, tram 4.91, metro 6.23, train 6.86, louaj 5.88,
     a1 5.46, a2 6.60, glow 4.83, mu 5.80 — all >= 4.5. The undarkened neon
     values came in between 1.9 and 2.6 and failed badly. */
  :global(:root[data-theme="light"]) .app {
    --bg: #f6f3ff;
    --surf: rgba(255, 255, 255, 0.86);
    --surf-2: rgba(40, 20, 80, 0.045);
    --line: rgba(50, 30, 100, 0.16);
    --tx: #1a1330;
    --mu: #635a80;
    --mu-2: #8b83a8;
    --a1: #b81f7a;
    --a2: #5b34d6;
    --glow: #0a7a62;
    --casing: rgba(255, 253, 250, 0.94);
    --on-accent: #fffaff;

    --n-bus: #c4135b;
    --n-tram: #8a6400;
    --n-metro: #1b53c4;
    --n-train: #6d28c9;
    --n-louaj: #046b5c;
    --n-walk: #6b7280;
    --n-unk: #7a7392;
  }
  .app :global(h1), .app :global(h2), .app :global(h3), .app :global(h4) {
    font-family: "Sora", ui-sans-serif, system-ui, sans-serif;
  }

  /* ── Layout ─────────────────────────────────────────────────────────────── */
  .body { display: flex; flex: 1; min-height: 0; }
  /* Panel column: the scrollable content and the pinned action footer are
     SIBLINGS in a flex column, so the footer is laid out after the scroll
     area rather than inside it and cannot scroll out of reach. */
  .panel-col {
    display: flex;
    flex-direction: column;
    width: 386px; flex-shrink: 0;
    min-height: 0;
    background: var(--surf);
    backdrop-filter: blur(22px) saturate(1.4);
    border-inline-end: 1px solid var(--line);
    box-shadow: 30px 0 80px rgba(0, 0, 0, 0.5);
    z-index: 500;
  }
  .side {
    flex: 1;
    min-height: 0;
    overflow-y: auto; overflow-x: hidden;
    padding: 18px;
    display: flex; flex-direction: column; gap: 18px;
  }

  /* ── CTA ────────────────────────────────────────────────────────────────── */
  .cta {
    position: relative; overflow: hidden;
    display: flex; align-items: center; justify-content: center; gap: 8px;
    width: 100%; min-height: 52px;
    border: 0; border-radius: 18px;
    background: linear-gradient(135deg, var(--a1), var(--a2));
    color: var(--on-accent);
    font-family: "Sora", system-ui, sans-serif;
    font-size: 15px; font-weight: 700;
    cursor: pointer;
    box-shadow: 0 0 26px rgba(123, 92, 255, 0.45), 0 14px 34px rgba(0, 0, 0, 0.45);
    transition: transform 0.25s ease, box-shadow 0.3s ease;
  }
  .cta::after {
    content: "";
    position: absolute; inset: 0;
    background: linear-gradient(110deg, transparent 30%, rgba(255, 255, 255, 0.45) 50%, transparent 70%);
    translate: -100% 0;
    animation: shine 3.2s infinite;
  }
  @keyframes shine { to { translate: 100% 0; } }
  /* The CTA lives in a bar pinned to the bottom of the panel, outside the
     scrolling area. `position: sticky` was tried first and failed: once the
     panel scrolls past the button's own offset the sticky element leaves the
     viewport entirely, so the primary action became unreachable exactly when
     results arrived. A separate non-scrolling bar cannot have that failure. */
  .cta-bar {
    flex-shrink: 0;
    padding: 12px 18px 16px;
    background: var(--surf);
    border-top: 1px solid var(--line);
    backdrop-filter: blur(18px);
  }
  .cta:hover:not(:disabled) { transform: translateY(-2px) scale(1.01); }
  .cta:active:not(:disabled) { transform: scale(0.99); }
  .cta:disabled { opacity: 0.45; cursor: not-allowed; box-shadow: none; }
  .cta:disabled::after { animation: none; }

  .toast {
    position: fixed;
    bottom: 26px; left: 50%;
    transform: translateX(-50%);
    z-index: 2000;
    max-width: min(92vw, 460px);
    padding: 11px 20px;
    border: 1px solid var(--glow);
    border-radius: 99px;
    background: var(--surf);
    color: var(--tx);
    font-size: 13px; font-weight: 600;
    box-shadow: 0 0 22px rgba(61, 242, 201, 0.35), 0 12px 40px rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(16px);
    animation: rise 0.35s cubic-bezier(.2,.9,.2,1);
  }
  @keyframes rise { from { opacity: 0; transform: translate(-50%, 12px); } }

  /* ── Map ────────────────────────────────────────────────────────────────── */
  .map-wrap { position: relative; flex: 1; min-width: 0; }
  .map { position: absolute; inset: 0; }

  /* ── Route focus: only the calculated route stays lit ────────────────────
     Everything the rider did not ask for — the rest of the road and rail
     network, and every station dot — drops to a ghost, so the route reads as
     the single bright thing on the map. The A/B endpoints and the traveller
     dot live in their own panes and are deliberately NOT dimmed. The rider
     can bring the network back with the toggle in the results section. */
  .map-wrap :global(.leaflet-marker-pane),
  .map-wrap :global(.leaflet-net_bus-pane),
  .map-wrap :global(.leaflet-net_taxi_louage-pane),
  .map-wrap :global(.leaflet-net_tram-pane),
  .map-wrap :global(.leaflet-net_metro-pane),
  .map-wrap :global(.leaflet-net_train-pane) {
    transition: opacity 0.5s ease;
  }
  .map-wrap.focused :global(.leaflet-marker-pane),
  .map-wrap.focused :global(.leaflet-net_bus-pane),
  .map-wrap.focused :global(.leaflet-net_taxi_louage-pane),
  .map-wrap.focused :global(.leaflet-net_tram-pane),
  .map-wrap.focused :global(.leaflet-net_metro-pane),
  .map-wrap.focused :global(.leaflet-net_train-pane) {
    opacity: 0.1;
  }
  .map-wrap.focused :global(.leaflet-net_train-pane),
  .map-wrap.focused :global(.leaflet-net_metro-pane) {
    opacity: 0.16;
  }

  /* Neon glow, applied per network pane. A canvas has no per-line element, so
     the glow is a drop-shadow on that pane's single canvas — which is exactly
     why each transport type gets its own pane instead of sharing one. */
  .map-wrap :global(.leaflet-net_bus-pane canvas) { filter: drop-shadow(0 0 3px var(--n-bus)); }
  .map-wrap :global(.leaflet-net_taxi_louage-pane canvas) { filter: drop-shadow(0 0 3px var(--n-louaj)); }
  .map-wrap :global(.leaflet-net_tram-pane canvas) { filter: drop-shadow(0 0 3px var(--n-tram)); }
  .map-wrap :global(.leaflet-net_metro-pane canvas) { filter: drop-shadow(0 0 4px var(--n-metro)); }
  .map-wrap :global(.leaflet-net_train-pane canvas) { filter: drop-shadow(0 0 4px var(--n-train)); }

  /* Per-transport glow on the route. The route is SVG (not canvas) precisely
     so each leg can carry a class and therefore its own hue's glow. */
  .map-wrap :global(path.route-leg-bus) { filter: drop-shadow(0 0 6px var(--n-bus)); }
  .map-wrap :global(path.route-leg-taxi_louage) { filter: drop-shadow(0 0 6px var(--n-louaj)); }
  .map-wrap :global(path.route-leg-tram) { filter: drop-shadow(0 0 6px var(--n-tram)); }
  .map-wrap :global(path.route-leg-metro) { filter: drop-shadow(0 0 6px var(--n-metro)); }
  .map-wrap :global(path.route-leg-train) { filter: drop-shadow(0 0 6px var(--n-train)); }
  .map-wrap :global(path.route-leg-walk) { filter: none; }

  .float {
    position: absolute; top: 16px; left: 50%;
    transform: translateX(-50%);
    display: flex; align-items: center; gap: 8px;
    padding: 8px 15px;
    border: 1px solid var(--line);
    border-radius: 99px;
    background: var(--surf);
    backdrop-filter: blur(16px);
    color: var(--mu);
    font-size: 12px;
    box-shadow: 0 8px 26px rgba(0, 0, 0, 0.6);
    pointer-events: none;
    z-index: 700;
  }

  .pick-banner {
    position: absolute; top: 16px; left: 50%;
    transform: translateX(-50%);
    display: flex; align-items: center; gap: 8px;
    padding: 9px 16px;
    border: 1px solid var(--glow);
    border-radius: 99px;
    background: var(--surf);
    backdrop-filter: blur(16px);
    color: var(--glow);
    font-size: 12px; font-weight: 600;
    box-shadow: 0 0 22px rgba(61, 242, 201, 0.3), 0 8px 26px rgba(0, 0, 0, 0.6);
    pointer-events: none;
    z-index: 700;
  }

  /* ── Route animation ─────────────────────────────────────────────────────
     The draw-in is applied imperatively (see RouteDrawing) so it re-runs on
     every itinerary change; the flowing dash is pure CSS on a second polyline. */
  .map-wrap :global(.route-flow) { animation: bledi-flow 1s linear infinite; }
  @keyframes bledi-draw { to { stroke-dashoffset: 0; } }
  @keyframes bledi-flow { to { stroke-dashoffset: -16; } }

  /* ── Marker clusters ────────────────────────────────────────────────────── */
  .map-wrap :global(.marker-cluster) { background: transparent !important; }
  .map-wrap :global(.bl-cluster) {
    position: relative;
    width: 40px; height: 40px;
    display: grid; place-items: center;
  }
  .map-wrap :global(.bl-halo) {
    position: absolute; inset: 0;
    border-radius: 50%;
    background: color-mix(in srgb, var(--glow) 22%, transparent);
    animation: bledi-pulse 2.6s ease-out infinite;
  }
  .map-wrap :global(.bl-cluster.no-pulse .bl-halo) { animation: none; opacity: 0.5; }
  @keyframes bledi-pulse {
    0% { transform: scale(0.72); opacity: 0.55; }
    100% { transform: scale(1.35); opacity: 0; }
  }
  .map-wrap :global(.bl-n) {
    position: relative; z-index: 1;
    width: 32px; height: 32px;
    display: grid; place-items: center;
    border: 1px solid color-mix(in srgb, var(--glow) 50%, transparent);
    border-radius: 50%;
    background: color-mix(in srgb, var(--bg) 88%, transparent);
    color: var(--glow);
    font-size: 11px; font-weight: 700;
    font-variant-numeric: tabular-nums;
    box-shadow: 0 0 14px color-mix(in srgb, var(--glow) 30%, transparent), 0 3px 14px rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
  }
  .map-wrap :global(.marker-cluster-medium .bl-n) {
    color: var(--n-tram);
    border-color: color-mix(in srgb, var(--n-tram) 55%, transparent);
  }
  .map-wrap :global(.marker-cluster-large .bl-n) {
    color: var(--n-bus);
    border-color: color-mix(in srgb, var(--n-bus) 55%, transparent);
  }
  .map-wrap :global(.tt-sub) { display: block; font-size: 10px; opacity: 0.7; }

  /* ── Scrollbar / focus ──────────────────────────────────────────────────── */
  .side::-webkit-scrollbar { width: 8px; }
  .side::-webkit-scrollbar-track { background: transparent; }
  .side::-webkit-scrollbar-thumb {
    background: rgba(200, 180, 255, 0.16); border-radius: 4px;
    border: 2px solid transparent; background-clip: content-box;
  }
  .side::-webkit-scrollbar-thumb:hover {
    background: rgba(200, 180, 255, 0.32); background-clip: content-box;
  }

  /* Reaches into the child components but not into Leaflet's own DOM, which
     the scoped rule never styled. */
  .app :global(:focus-visible:not(.leaflet-container *)) { outline: 2px solid var(--glow); outline-offset: 2px; border-radius: 10px; }

  /* ── Responsive: panel above map on small screens ───────────────────────── */
  @media (max-width: 900px) {
    .body { flex-direction: column; }
    .panel-col {
      width: 100%;
      max-height: 60vh;
      border-inline-end: 0;
      border-bottom: 1px solid var(--line);
    }
    .side { padding: 14px; }
    .map-wrap { flex: 1; min-height: 36vh; }
  }
  @media (max-width: 420px) {
    .side { padding: 13px; }
  }

  @media (prefers-reduced-motion: reduce) {
    .app :global(:not(.leaflet-container *)),
    .app :global(:not(.leaflet-container *)::before),
    .app :global(:not(.leaflet-container *)::after) {
      animation-duration: 0.001ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.001ms !important;
    }
    /* The route draw-in sets stroke-dashoffset inline; make sure a paused
       animation still leaves the line fully visible rather than invisible. */
    .map-wrap :global(.route-flow) { animation: none !important; opacity: 0 !important; }
    .map-wrap :global(path.route-draw) { stroke-dashoffset: 0 !important; }
  }
</style>
