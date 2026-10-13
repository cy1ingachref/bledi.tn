<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "svelte/store";
  import Icon from "$lib/ui/Icon.svelte";
  import type {
    Endpoint,
    NetworkSegment,
    Objective,
    RouteLeg,
    RoutePlan,
    Station,
    StationDetail,
    StationsMeta,
    PlaceHit,
    MapOverlayFeature,
    LouageLink,
  } from "$lib/domain/transit";
  import {
    DEFAULT_MODES,
    defaultSelection,
    isStationShown,
    servedModes,
    uniqueModes,
  } from "$lib/domain/modes";
  import { fareOf, isWalkLeg, mergeLegs } from "$lib/domain/itinerary";
  import { planTrip, tripProblem } from "$lib/application/planTrip";
  import { loadBaseLayers, loadLouageLinks, louageDestinations } from "$lib/application/mapData";
  import {
    LANGS,
    translator,
    dirOf,
    formatDuration,
    legLabel,
    modeLabel,
    modeLabelFor,
    type Lang,
  } from "$lib/application/i18n";
  import { useTransit } from "$lib/ui/context";
  import { MODE_STYLE, modeColor, modeIcon } from "$lib/ui/modeStyle";
  import { TransitMap } from "./transitMap";
  import { initTheme, cycleTheme, resolvedTheme, themePref, type ThemePref } from "$lib/ui/theme";

  const OBJECTIVES: { id: Objective; icon: string }[] = [
    { id: "fastest", icon: "clock" },
    { id: "cheapest", icon: "coin" },
    { id: "fewest_transfers", icon: "transfer" },
  ];

  const transit = useTransit();

  // ── State ─────────────────────────────────────────────────────────────────
  let mapEl: HTMLDivElement | null = $state(null);
  let tmap: TransitMap | null = null;

  let lang = $state<Lang>("fr");
  const t = $derived(translator(lang));
  const dir = $derived(dirOf(lang));

  // Theme: auto follows the OS, but an explicit pick wins and persists.
  let theme = $state<ThemePref>("auto");
  const dark = $derived($resolvedTheme);
  const themeIcon = $derived(theme === "auto" ? "globe" : theme === "light" ? "sun" : "moon");
  const themeLabel = $derived(
    theme === "auto" ? t("theme.auto") : theme === "light" ? t("theme.light") : t("theme.dark")
  );

  function cycleThemeClick() {
    cycleTheme();
    theme = get(themePref);
  }

  // ── Data ──────────────────────────────────────────────────────────────────
  let stations = $state<Station[]>([]);
  let stationMeta = $state<StationsMeta>({ count: 0, total: 0, by_mode: {} });
  let loadingStations = $state(true);
  let network = $state<NetworkSegment[]>([]);
  let loadingNetwork = $state(true);
  let error = $state("");

  // Physical rail/road base layers, plus the louage connection graph.
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

  // Map layer visibility
  let showRoads = $state(true);
  let showRails = $state(true);
  let showUnclassified = $state(false);
  // When a route is on screen, dim everything that is not part of it until the
  // rider asks to see the rest of the network again.
  let focusRoute = $state(true);

  // Station inspector
  let inspected = $state<StationDetail | null>(null);
  let inspectLoading = $state(false);
  let inspectError = $state("");

  // Place search
  let query = $state("");
  let hits = $state<PlaceHit[]>([]);
  let searching = $state(false);
  let searchTimer: ReturnType<typeof setTimeout> | null = null;

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

  function isOn(id: string): boolean {
    return selected.has(id);
  }

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

  // ── Search ────────────────────────────────────────────────────────────────
  function runSearch() {
    const q = query.trim();
    if (q.length < 2) { hits = []; return; }
    searching = true;
    transit
      .searchPlaces(q, from ? { lat: from.lat, lon: from.lon } : null)
      .then((r) => { hits = r; })
      .catch(() => { hits = []; })
      .finally(() => { searching = false; });
  }

  function onQueryInput() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, 300);
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
    hits = [];
    query = "";
    pickMode = null;
  }

  // ── Routing ───────────────────────────────────────────────────────────────
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

  function legColor(leg: RouteLeg): string {
    return isWalkLeg(leg) ? "#8b83a8" : modeColor(leg.mode ?? "bus");
  }

  /** Steps for the selected itinerary, with same-line hops collapsed. */
  const steps = $derived.by(() => {
    const itin = routePlan?.itineraries?.[selectedItinerary];
    return itin ? mergeLegs(itin.legs ?? []) : [];
  });

  // ── Lifecycle ─────────────────────────────────────────────────────────────
  onMount(() => {
    // Theme first: the inline script in app.html already set data-theme before
    // first paint, so this only syncs the store and wires OS-change following.
    theme = ((): ThemePref => {
      try {
        const v = localStorage.getItem("bledi_theme");
        if (v === "light" || v === "dark" || v === "auto") return v;
      } catch { /* ignore */ }
      return "auto";
    })();
    initTheme();
    theme = get(themePref);

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
  <!-- ── Header ──────────────────────────────────────────────────────────── -->
  <header class="hdr">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"><Icon name="route" size={20} /></span>
      <span class="brand-text">
        <strong>Bledi<span class="dot">.tn</span></strong>
        <small>{t("app.tagline")}</small>
      </span>
    </div>
    <div class="hdr-right">
      <button class="theme-btn" onclick={cycleThemeClick} aria-label={themeLabel} title={themeLabel}>
        <Icon name={themeIcon} size={16} />
      </button>
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
    <!-- ── Panel column: scrollable content + pinned action footer ── -->
    <div class="panel-col">
      <aside class="side">
        <!-- ── Search: pick a place by NAME ─────────────────────────────── -->
        <section class="sec">
          <div class="sec-head">
            <h2>{t("search.usePlace")}</h2>
            <span class="mini-actions">
              <span class="count-pill">{shownStops} {t("status.stops")}</span>
            </span>
          </div>

          <div class="search-row" class:active={!!pickMode}>
            <Icon name="search" size={15} cls="s-ic" />
            <input
              bind:value={query}
              oninput={onQueryInput}
              placeholder={t("search.placeholder")}
              aria-label={t("search.placeholder")}
            />
            {#if searching}<span class="spin dark" aria-hidden="true"></span>{/if}
          </div>

          <div class="targets" role="group" aria-label={t("search.usePlace")}>
            <button
              class="tgt" class:on={pickMode === "from"}
              onclick={() => startPick("from")}
              aria-pressed={pickMode === "from"}
            >
              <span class="badge a sm">A</span>{t("trip.from")}
              <Icon name="crosshair" size={12} cls="tgt-ic" />
            </button>
            <button
              class="tgt" class:on={pickMode === "to"}
              onclick={() => startPick("to")}
              aria-pressed={pickMode === "to"}
            >
              <span class="badge b sm">B</span>{t("trip.to")}
              <Icon name="crosshair" size={12} cls="tgt-ic" />
            </button>
          </div>

          {#if pickMode}
            <p class="pick-note" role="status">
              <Icon name="crosshair" size={12} /> {t("trip.pickHint")}
            </p>
          {/if}

          {#if hits.length > 0}
            <ul class="hits">
              {#each hits as h}
                <li>
                  <button class="hit" onclick={() => pickHit(h)}>
                    <span class="hit-ic" style="--c:{h.kind === 'city' ? '#ffc400' : '#ff3d81'}">
                      <Icon name={h.kind === "city" ? "pin" : "target"} size={12} />
                    </span>
                    <span class="hit-tx">
                      <b>{h.name}</b>
                      <small>
                        {h.city}
                        {#if h.modes.length}· {h.modes.map((m) => modeLabelFor(t, m)).join(", ")}{/if}
                      </small>
                    </span>
                    <Icon name="arrowRight" size={13} cls="hit-go" />
                  </button>
                </li>
              {/each}
            </ul>
          {:else if query.trim().length >= 2 && !searching}
            <p class="no-hit">{t("search.noResults")}</p>
          {/if}

          <!-- Trip card: A and B as one connected control, with a swap. -->
          <div class="trip">
            <div class="trip-row">
              <span class="pin a" aria-hidden="true"></span>
              <button class="trip-in" onclick={() => startPick("from")}>
                <span class="trip-lbl">{t("trip.from")}</span>
                <span class="trip-val" class:empty={!from}>
                  {from ? from.name : t("trip.notSet")}
                </span>
              </button>
            </div>
            <div class="trip-row">
              <span class="pin b" aria-hidden="true"></span>
              <button class="trip-in" onclick={() => startPick("to")}>
                <span class="trip-lbl">{t("trip.to")}</span>
                <span class="trip-val" class:empty={!to}>
                  {to ? to.name : t("trip.notSet")}
                </span>
              </button>
            </div>
            <button class="swap" onclick={swapEndpoints} aria-label={t("trip.swap")} title={t("trip.swap")}>
              <Icon name="transfer" size={15} />
            </button>
          </div>

          <div class="quick">
            <button class="chip" onclick={useMyLocation} disabled={locating}>
              <Icon name="locate" size={13} />
              {locating ? t("trip.locating") : t("trip.myLocation")}
            </button>
            <button class="chip" onclick={() => startPick("from")}>
              <Icon name="crosshair" size={13} />
              {t("trip.pickOnMap")}
            </button>
          </div>
        </section>

        <!-- ── Priority ─────────────────────────────────────────────────── -->
        <section class="sec">
          <h2>{t("priority.title")}</h2>
          <div class="seg" role="group" aria-label={t("priority.title")}>
            <span
              class="seg-pill"
              aria-hidden="true"
              style="transform:translateX({OBJECTIVES.findIndex((o) => o.id === objective) * 100}%)"
            ></span>
            {#each OBJECTIVES as o}
              <button
                class="seg-btn"
                class:on={objective === o.id}
                onclick={() => (objective = o.id)}
                aria-pressed={objective === o.id}
              >
                <Icon name={o.icon} size={13} />
                <span>{t("priority." + o.id)}</span>
              </button>
            {/each}
          </div>
        </section>

        <!-- ── Modes: only the ones the network actually serves ──────────── -->
        <section class="sec">
          <div class="sec-head">
            <h2>
              {t("modes.title")}
              <span class="counter" class:zero={count === 0}>{count}/{chips.length}</span>
            </h2>
            <span class="mini-actions">
              <button class="mini" onclick={() => setAll(true)}>{t("modes.selectAll")}</button>
              <span class="sep">·</span>
              <button class="mini" onclick={() => setAll(false)}>{t("modes.clear")}</button>
            </span>
          </div>
          <div class="modes">
            {#each chips as m}
              <button
                class="mode"
                class:on={isOn(m.id)}
                onclick={() => toggleMode(m.id)}
                aria-pressed={isOn(m.id)}
                style={isOn(m.id) ? `--mc:${m.color}` : ""}
              >
                <span class="m-ic"><Icon name={m.icon} size={14} /></span>
                <span class="m-lbl">{modeLabel(t, m.id)}</span>
                <span class="m-n">{m.count.toLocaleString()}</span>
              </button>
            {/each}
          </div>
          {#if count === 0}
            <p class="hint-warn" role="status">
              <Icon name="alert" size={13} /> {t("error.noModes")}
            </p>
          {/if}
        </section>

        <!-- ── Map layers ───────────────────────────────────────────────── -->
        <section class="sec">
          <h2>{t("legend.network")}</h2>
          <div class="layers">
            <button class="layer" class:on={showRoads} onclick={() => (showRoads = !showRoads)} aria-pressed={showRoads}>
              <span class="ly-line road" aria-hidden="true"></span>
              <span class="ly-tx">{t("modes.bus")}</span>
              <Icon name={showRoads ? "eye" : "eyeOff"} size={13} />
            </button>
            <button class="layer" class:on={showRails} onclick={() => (showRails = !showRails)} aria-pressed={showRails}>
              <span class="ly-line rail" aria-hidden="true"></span>
              <span class="ly-tx">{t("modes.train")}</span>
              <Icon name={showRails ? "eye" : "eyeOff"} size={13} />
            </button>
            {#if unclassifiedCount > 0}
              <button
                class="layer"
                class:on={showUnclassified}
                onclick={() => (showUnclassified = !showUnclassified)}
                aria-pressed={showUnclassified}
              >
                <span class="ly-line unk" aria-hidden="true"></span>
                <span class="ly-tx">{t("modes.unclassified")}</span>
                <span class="m-n">{unclassifiedCount}</span>
              </button>
            {/if}
          </div>
        </section>

        {#if error}
          <div class="alert" role="alert">
            <Icon name="alert" size={15} /><span>{error}</span>
          </div>
        {/if}

        <!-- ── Results ──────────────────────────────────────────────────── -->
        {#if routePlan?.itineraries?.length}
          <section class="sec results" bind:this={resultsEl}>
            <div class="sec-head">
              <h2>{t("results.title")}</h2>
              <span class="sub">{t("results.subtitle")}</span>
            </div>

            {#each routePlan.itineraries as itin, i}
              {@const fare = fareOf(itin)}
              <button
                class="itin"
                class:on={selectedItinerary === i}
                onclick={() => { selectedItinerary = i; tmap?.route.draw(itin, dark); focusRoute = true; }}
                aria-pressed={selectedItinerary === i}
              >
                <div class="it-top">
                  <span class="it-n">{t("results.option")} {i + 1}</span>
                  <span class="it-dur">{formatDuration(itin.duration_min, t)}</span>
                </div>
                <div class="it-fare">
                  {#if fare > 0}<span class="it-price">{fare.toFixed(2)} DT</span>{/if}
                  <span class="it-mode">
                    {uniqueModes(itin.modes_used).map((mu) => modeLabelFor(t, mu)).join(" + ")}
                  </span>
                </div>
                <!-- Leg bar: one neon segment per transport type. -->
                <div class="legs" aria-hidden="true">
                  {#each uniqueModes(itin.modes_used) as mu}
                    <span class="leg" style="--c:{modeColor(mu)}"></span>
                  {/each}
                </div>
                <div class="it-meta">
                  <span>
                    <Icon name="transfer" size={12} />
                    {itin.transfers === 0
                      ? t("results.direct")
                      : `${itin.transfers} ${t(itin.transfers > 1 ? "results.transfersPlural" : "results.transfers")}`}
                  </span>
                  {#if i === 0}<span class="tag">{t("results.best")}</span>{/if}
                </div>
                {#if selectedItinerary === i && steps.length > 0}
                  <ol class="steps">
                    {#each steps as leg}
                      <li class="step" style="--c:{legColor(leg)}">
                        <span class="s-ic">
                          <Icon
                            name={isWalkLeg(leg) ? "walk" : modeIcon(leg.mode ?? "bus")}
                            size={12}
                          />
                        </span>
                        <span class="s-tx">{legLabel(t, leg)}</span>
                        {#if leg.duration_min}<span class="s-d">{Math.round(leg.duration_min)}′</span>{/if}
                      </li>
                    {/each}
                  </ol>
                {/if}
              </button>
            {/each}

            <!-- Focus control: show the route alone, or bring the whole
                 network back. The rider decides; the default is the route. -->
            <button
              class="focus-btn"
              class:on={focused}
              onclick={() => (focusRoute = !focusRoute)}
              aria-pressed={focused}
            >
              <Icon name={focused ? "eyeOff" : "network"} size={14} />
              {focused ? t("results.showNetwork") : t("results.hideNetwork")}
            </button>
            {#if focused}
              <p class="focus-note" role="status">
                <Icon name="info" size={12} /> {t("results.focused")}
              </p>
            {/if}
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
            {t("action.calculate")}
          {/if}
        </button>
      </div>
    </div><!-- /.panel-col -->

    <!-- ── Map ────────────────────────────────────────────────────────────── -->
    <main class="map-wrap" class:focused>
      <div bind:this={mapEl} class="map"></div>

      {#if loadingStations || loadingNetwork}
        <div class="float">
          <span class="spin dark"></span>
          {loadingStations ? t("loading.stations") : t("loading.network")}
        </div>
      {/if}

      {#if pickMode}
        <div class="pick-banner" role="status">
          <Icon name="crosshair" size={14} />
          {t("trip.pickHint")}
        </div>
      {/if}

      <!-- ── Station inspector ──────────────────────────────────────────────
           What actually calls at this stop: every line, the direction it runs
           in, and whether it starts, ends or passes here. -->
      {#if inspected || inspectLoading}
        <aside class="inspector" aria-live="polite">
          <div class="ins-head">
            <div class="ins-title">
              <span class="ins-eyebrow">{t("station.title")}</span>
              <h3>{inspected?.name ?? ""}</h3>
              {#if inspected?.city}<span class="ins-city">{inspected.city}</span>{/if}
            </div>
            <button class="ins-close" onclick={() => (inspected = null)} aria-label={t("results.steps")}>
              <Icon name="close" size={15} />
            </button>
          </div>

          {#if inspectLoading}
            <p class="ins-loading"><span class="spin dark"></span> {t("loading.station")}</p>
          {:else if inspectError}
            <div class="alert" role="alert"><Icon name="alert" size={14} /><span>{inspectError}</span></div>
          {:else if inspected}
            <div class="ins-modes">
              {#if inspected.modes.length}
                {#each inspected.modes as m}
                  <span class="ins-mode" style="--c:{modeColor(m)}">
                    <Icon name={modeIcon(m)} size={12} />{modeLabelFor(t, m)}
                  </span>
                {/each}
              {:else}
                <span class="ins-mode none"><Icon name="pin" size={12} />{t("modes.unclassified")}</span>
              {/if}
              <span class="ins-count">{inspected.count} {t("station.count")}</span>
            </div>

            <div class="ins-actions">
              <button
                class="ins-act"
                onclick={() => {
                  if (inspected?.lat && inspected?.lon)
                    setEndpoint("from", {
                      kind: "stop", id: inspected.id, name: inspected.name ?? "",
                      lat: inspected.lat, lon: inspected.lon, modes: inspected.modes,
                    });
                }}
                disabled={!inspected.lat}
              >
                <span class="badge a sm">A</span>{t("station.setFrom")}
              </button>
              <button
                class="ins-act"
                onclick={() => {
                  if (inspected?.lat && inspected?.lon)
                    setEndpoint("to", {
                      kind: "stop", id: inspected.id, name: inspected.name ?? "",
                      lat: inspected.lat, lon: inspected.lon, modes: inspected.modes,
                    });
                }}
                disabled={!inspected.lat}
              >
                <span class="badge b sm">B</span>{t("station.setTo")}
              </button>
            </div>

            <h4>{t("station.lines")}</h4>
            {#if inspected.lines.length}
              <ul class="lines">
                {#each inspected.lines as ln}
                  <li class="line" style="--c:{modeColor(ln.mode)}">
                    <span class="ln-ic"><Icon name={modeIcon(ln.mode)} size={13} /></span>
                    <span class="ln-body">
                      <span class="ln-top">
                        <b>{modeLabelFor(t, ln.mode)}{ln.number ? ` ${ln.number}` : ""}</b>
                        <span class="ln-role">
                          {ln.role === "origin"
                            ? t("station.from")
                            : ln.role === "terminus"
                              ? t("station.to")
                              : t("station.through")}
                        </span>
                      </span>
                      {#if ln.direction}<span class="ln-dir">{ln.direction}</span>{/if}
                      <span class="ln-meta">
                        {#if ln.operator}{ln.operator} · {/if}{ln.stops_count} {t("status.stops")}
                      </span>
                    </span>
                  </li>
                {/each}
              </ul>
            {:else}
              <p class="ins-none">
                {inspected.lines_known ? t("station.none") : t("station.unlisted")}
              </p>
            {/if}

            <!-- Louage connections: which places this louage station serves,
                 resolved from its own destination list against real station
                 records. Only shown for stops that ARE a louage terminal. -->
            {#if louageDestinations(louageLinks, inspected.id).length}
              <h4 class="ins-sub">{t("station.louage_links")}</h4>
              <ul class="ins-lines">
                {#each louageDestinations(louageLinks, inspected.id) as l}
                  <li>
                    <button
                      class="ln-btn"
                      onclick={() => focusStation(l.to, l.to_name)}
                      title={l.destination_raw}
                    >
                      <span class="ln-top">
                        <b>{l.to_name}</b>
                        <span class="ln-role">{t("station.serves")}</span>
                      </span>
                    </button>
                  </li>
                {/each}
              </ul>
            {/if}
          {/if}
        </aside>
      {/if}

      <!-- ── Legend ───────────────────────────────────────────────────────── -->
      <div class="legend">
        <div class="lg-grid">
          {#each chips as m}
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

  /* ── Header ─────────────────────────────────────────────────────────────── */
  .hdr {
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    padding: 12px 18px;
    background: var(--surf);
    border-bottom: 1px solid var(--line);
    backdrop-filter: blur(18px) saturate(1.3);
    flex-shrink: 0;
    z-index: 600;
    transition: background 0.35s ease, border-color 0.35s ease;
  }
  .brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .brand-mark {
    display: grid; place-items: center;
    width: 42px; height: 42px; flex-shrink: 0;
    border-radius: 14px;
    background: linear-gradient(135deg, var(--a1), var(--a2));
    color: var(--on-accent);
    box-shadow: 0 0 22px rgba(123, 92, 255, 0.5), 0 8px 24px rgba(0, 0, 0, 0.5);
    animation: float 4s ease-in-out infinite;
  }
  @keyframes float { 50% { transform: translateY(-3px) rotate(-4deg); } }
  .brand-text { display: flex; flex-direction: column; min-width: 0; }
  .brand-text strong { font-family: "Sora", system-ui, sans-serif; font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
  .brand-text .dot {
    background: linear-gradient(90deg, var(--a1), var(--a2));
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .brand-text small { color: var(--mu); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .hdr-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

  .theme-btn {
    display: grid; place-items: center;
    width: 34px; height: 34px;
    border-radius: 99px;
    border: 1px solid var(--line);
    background: var(--surf-2);
    color: var(--tx);
    cursor: pointer;
    transition: transform 0.25s ease, border-color 0.25s ease, color 0.25s ease;
  }
  .theme-btn:hover { border-color: var(--a1); color: var(--a1); transform: rotate(-12deg) scale(1.06); }

  .langs { display: flex; gap: 2px; padding: 3px; border: 1px solid var(--line); border-radius: 99px; background: var(--surf-2); flex-shrink: 0; }
  .lang {
    min-width: 34px; min-height: 28px;
    border: 0; border-radius: 99px;
    background: transparent; color: var(--mu);
    font: inherit; font-size: 11px; font-weight: 700;
    cursor: pointer;
    transition: background 0.25s ease, color 0.25s ease;
  }
  .lang:hover { color: var(--tx); background: var(--surf-2); }
  .lang.on { background: linear-gradient(135deg, var(--a1), var(--a2)); color: var(--on-accent); }

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

  /* ── Sections ───────────────────────────────────────────────────────────── */
  .sec { display: flex; flex-direction: column; gap: 10px; }
  .sec-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  h2 {
    display: flex; align-items: center; gap: 6px;
    margin: 0;
    font-family: "Sora", system-ui, sans-serif;
    font-size: 11px; font-weight: 600;
    letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--mu);
  }
  h4 {
    margin: 0;
    font-size: 11px; font-weight: 600;
    letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--mu-2);
  }
  .counter {
    padding: 2px 8px;
    border: 1px solid var(--line);
    border-radius: 99px;
    background: rgba(61, 242, 201, 0.1);
    color: var(--glow);
    font-size: 10px; font-weight: 700;
    letter-spacing: 0;
    font-variant-numeric: tabular-nums;
  }
  .counter.zero { border-color: rgba(255, 61, 129, 0.45); background: rgba(255, 61, 129, 0.12); color: #ff8fb3; }
  .sub { font-size: 10px; color: var(--mu-2); }
  .count-pill {
    font-size: 10px; font-weight: 600; color: var(--mu-2);
    padding: 2px 8px; border-radius: 99px; border: 1px solid var(--line);
    font-variant-numeric: tabular-nums;
  }

  .mini-actions { display: inline-flex; align-items: center; gap: 4px; }
  .mini {
    border: 0; background: none; padding: 2px 5px;
    color: var(--mu); font: inherit; font-size: 11px; font-weight: 600;
    cursor: pointer; border-radius: 6px;
    transition: color 0.25s ease;
  }
  .mini:hover { color: var(--a1); }
  .sep { color: var(--line); }

  /* ── Search ─────────────────────────────────────────────────────────────── */
  .search-row {
    display: flex; align-items: center; gap: 9px;
    padding: 0 12px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: var(--surf-2);
    transition: border-color 0.25s ease, box-shadow 0.25s ease;
  }
  .search-row:focus-within { border-color: var(--a1); box-shadow: 0 0 0 3px rgba(255, 138, 212, 0.15); }
  .search-row.active { border-color: var(--glow); box-shadow: 0 0 0 3px rgba(61, 242, 201, 0.14); }
  .search-row :global(svg.s-ic) { color: var(--mu); flex-shrink: 0; }
  .search-row input {
    flex: 1; min-width: 0; min-height: 42px;
    border: 0; background: none; outline: none;
    color: var(--tx); font: inherit; font-size: 14px;
  }
  .search-row input::placeholder { color: var(--mu-2); }

  .targets { display: flex; gap: 6px; }
  .tgt {
    display: inline-flex; align-items: center; gap: 6px;
    flex: 1; min-height: 36px; padding: 5px 10px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--surf-2);
    color: var(--mu);
    font: inherit; font-size: 11.5px; font-weight: 600;
    cursor: pointer;
    transition: all 0.25s ease;
  }
  .tgt:hover { border-color: rgba(255, 138, 212, 0.45); color: var(--tx); }
  .tgt.on { border-color: var(--glow); background: rgba(61, 242, 201, 0.1); color: var(--glow); }
  .tgt :global(svg.tgt-ic) { margin-inline-start: auto; opacity: 0.6; }
  .tgt.on :global(svg.tgt-ic) { opacity: 1; }

  .pick-note {
    display: flex; align-items: center; gap: 6px;
    margin: 0; padding: 7px 11px;
    border: 1px dashed rgba(61, 242, 201, 0.4);
    border-radius: 11px;
    background: rgba(61, 242, 201, 0.07);
    color: var(--glow);
    font-size: 11.5px;
  }

  .badge {
    display: grid; place-items: center;
    width: 20px; height: 20px; flex-shrink: 0;
    border-radius: 50%;
    font-size: 10px; font-weight: 800;
    color: #05020e;
  }
  .badge.sm { width: 17px; height: 17px; font-size: 9px; }
  .badge.a { background: #22d3ee; }
  .badge.b { background: #f472b6; }

  .hits {
    list-style: none; margin: 0; padding: 5px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: var(--bg);
    display: flex; flex-direction: column; gap: 2px;
    max-height: 230px; overflow-y: auto;
  }
  .hit {
    display: flex; align-items: center; gap: 9px;
    width: 100%; padding: 8px 9px;
    border: 0; border-radius: 11px;
    background: none; color: var(--mu);
    font: inherit; font-size: 12.5px; text-align: start;
    cursor: pointer;
    transition: background 0.2s ease, color 0.2s ease;
  }
  .hit:hover { background: rgba(255, 138, 212, 0.1); color: var(--tx); }
  .hit-ic {
    display: grid; place-items: center;
    width: 24px; height: 24px; flex-shrink: 0;
    border-radius: 8px;
    background: color-mix(in srgb, var(--c) 20%, transparent);
    color: var(--c);
  }
  .hit-tx { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .hit-tx b { font-weight: 600; color: var(--tx); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hit-tx small { font-size: 10.5px; color: var(--mu-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hit :global(svg.hit-go) { color: var(--mu-2); flex-shrink: 0; }
  .no-hit { margin: 0; padding: 2px 4px; color: var(--mu-2); font-size: 11.5px; }

  /* ── Trip card (A -> B as one connected control) ────────────────────────── */
  .trip {
    position: relative;
    background: var(--surf-2);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 6px 54px 6px 14px;
  }
  .trip::before {
    content: "";
    position: absolute;
    left: 20px; top: 34px; bottom: 34px;
    border-left: 2px dotted var(--mu-2);
  }
  .trip-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; position: relative; z-index: 1; }
  .trip-row + .trip-row { border-top: 1px solid var(--line); }
  .pin { width: 13px; height: 13px; border-radius: 50%; flex: none; }
  .pin.a { background: #22d3ee; box-shadow: 0 0 0 4px rgba(34, 211, 238, 0.2), 0 0 12px #22d3ee; }
  .pin.b { background: #f472b6; box-shadow: 0 0 0 4px rgba(244, 114, 182, 0.2), 0 0 12px #f472b6; }

  .trip-in {
    flex: 1; min-width: 0;
    display: flex; flex-direction: column; gap: 1px;
    border: 0; background: none; padding: 0;
    text-align: start; cursor: pointer; font: inherit;
  }
  .trip-lbl { font-size: 10px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--mu-2); }
  .trip-val {
    font-size: 14px; font-weight: 500; color: var(--tx);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .trip-val.empty { color: var(--mu-2); font-style: italic; }

  .swap {
    position: absolute; right: 11px; top: 50%; translate: 0 -50%;
    width: 34px; height: 34px;
    display: grid; place-items: center;
    border-radius: 50%;
    border: 1px solid var(--line);
    background: var(--bg); color: var(--tx);
    cursor: pointer;
    transition: transform 0.4s cubic-bezier(.3,1.4,.4,1), border-color 0.3s ease;
  }
  .swap:hover { transform: rotate(180deg); border-color: var(--a1); color: var(--a1); }

  /* ── Quick chips ────────────────────────────────────────────────────────── */
  .quick { display: flex; gap: 8px; flex-wrap: wrap; }
  .chip {
    display: inline-flex; align-items: center; gap: 6px;
    border: 1px solid var(--line);
    background: var(--surf-2);
    color: var(--tx);
    padding: 8px 13px;
    border-radius: 99px;
    font: 500 12.5px "DM Sans", system-ui, sans-serif;
    cursor: pointer;
    transition: transform 0.25s ease, border-color 0.25s ease;
  }
  .chip:hover:not(:disabled) { border-color: var(--a1); transform: translateY(-2px); }
  .chip:disabled { opacity: 0.55; cursor: default; }
  .chip :global(svg) { color: var(--glow); }

  /* ── Priority segmented control ─────────────────────────────────────────── */
  .seg {
    position: relative;
    display: grid; grid-template-columns: repeat(3, 1fr);
    background: rgba(255, 255, 255, 0.05);
    border-radius: 16px;
    padding: 4px;
  }
  .seg-pill {
    position: absolute; top: 4px; bottom: 4px; left: 4px;
    width: calc(33.333% - 2.7px);
    border-radius: 12px;
    background: linear-gradient(135deg, var(--a1), var(--a2));
    box-shadow: 0 0 18px rgba(123, 92, 255, 0.4);
    transition: transform 0.45s cubic-bezier(.3,1.4,.4,1);
    pointer-events: none;
  }
  .seg-btn {
    position: relative; z-index: 1;
    display: flex; align-items: center; justify-content: center; gap: 5px;
    background: none; border: 0;
    color: var(--mu);
    padding: 10px 4px;
    font: 600 11.5px "DM Sans", system-ui, sans-serif;
    cursor: pointer;
    transition: color 0.3s ease;
  }
  .seg-btn.on { color: var(--on-accent); }

  /* ── Mode chips: neon pill with the mode's own hue ──────────────────────── */
  .modes { display: flex; gap: 8px; flex-wrap: wrap; }
  .mode {
    --mc: var(--mu);
    display: flex; align-items: center; gap: 7px;
    padding: 8px 11px;
    border-radius: 14px;
    border: 1px solid var(--line);
    background: rgba(255, 255, 255, 0.03);
    color: var(--mu);
    cursor: pointer;
    font: 600 12.5px "DM Sans", system-ui, sans-serif;
    transition: all 0.3s ease;
  }
  .mode:hover { border-color: rgba(200, 180, 255, 0.28); }
  .m-ic { display: grid; place-items: center; flex-shrink: 0; color: var(--mu-2); transition: color 0.3s ease; }
  .m-lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .m-n {
    font-size: 10px; font-weight: 700; color: var(--mu-2);
    font-variant-numeric: tabular-nums;
    padding: 1px 5px; border-radius: 6px; background: rgba(255, 255, 255, 0.05);
  }
  .mode.on {
    color: var(--tx);
    border-color: var(--mc);
    background: color-mix(in srgb, var(--mc) 16%, transparent);
    box-shadow: 0 0 16px color-mix(in srgb, var(--mc) 34%, transparent),
                inset 0 0 12px color-mix(in srgb, var(--mc) 12%, transparent);
  }
  .mode.on .m-ic { color: var(--mc); filter: drop-shadow(0 0 5px var(--mc)); }
  .mode.on .m-n { color: var(--mc); background: color-mix(in srgb, var(--mc) 16%, transparent); }

  /* ── Map layer toggles ──────────────────────────────────────────────────── */
  .layers { display: flex; flex-wrap: wrap; gap: 8px; }
  .layer {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 7px 11px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--surf-2);
    color: var(--mu);
    font: 600 11.5px "DM Sans", system-ui, sans-serif;
    cursor: pointer;
    transition: all 0.25s ease;
  }
  .layer:hover { border-color: rgba(200, 180, 255, 0.3); color: var(--tx); }
  .layer.on { color: var(--tx); border-color: rgba(200, 180, 255, 0.35); background: rgba(255, 255, 255, 0.06); }
  .layer :global(svg) { color: var(--mu-2); }
  .layer.on :global(svg) { color: var(--glow); }
  .ly-tx { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ly-line { width: 18px; height: 3px; border-radius: 3px; flex-shrink: 0; }
  .ly-line.road { background: linear-gradient(90deg, var(--n-bus), var(--n-louaj)); box-shadow: 0 0 8px var(--n-bus); }
  .ly-line.rail { background: linear-gradient(90deg, var(--n-metro), var(--n-train)); box-shadow: 0 0 8px var(--n-train); }
  .ly-line.unk { background: repeating-linear-gradient(90deg, var(--n-unk) 0 4px, transparent 4px 7px); }

  .hint-warn {
    display: flex; align-items: center; gap: 6px;
    margin: 0; padding: 8px 11px;
    border: 1px solid rgba(255, 196, 0, 0.3);
    border-radius: 12px;
    background: rgba(255, 196, 0, 0.1);
    color: #ffd98a;
    font-size: 11.5px;
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

  .spin {
    width: 14px; height: 14px; flex-shrink: 0;
    border: 2px solid color-mix(in srgb, var(--mu) 35%, transparent);
    border-top-color: var(--mu);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  .spin.dark { border-color: color-mix(in srgb, var(--on-accent) 35%, transparent); border-top-color: var(--on-accent); }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Alerts / toast ─────────────────────────────────────────────────────── */
  .alert {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 10px 13px;
    border: 1px solid rgba(255, 61, 129, 0.32);
    border-radius: 14px;
    background: rgba(255, 61, 129, 0.1);
    color: #ffb3cc;
    font-size: 12px; line-height: 1.45;
  }
  .alert.warn { border-color: rgba(255, 196, 0, 0.32); background: rgba(255, 196, 0, 0.1); color: #ffd98a; }
  .alert :global(svg) { flex-shrink: 0; margin-top: 1px; }

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

  /* ── Results ────────────────────────────────────────────────────────────── */
  .results { gap: 10px; }
  .itin {
    display: flex; flex-direction: column; gap: 8px;
    width: 100%; padding: 14px;
    border: 1px solid var(--line);
    border-radius: 18px;
    background: var(--surf-2);
    color: inherit;
    font: inherit; text-align: start;
    cursor: pointer;
    transition: all 0.3s ease;
  }
  .itin:hover { border-color: rgba(200, 180, 255, 0.28); transform: translateX(3px); }
  .itin.on {
    border-color: var(--glow);
    background: rgba(61, 242, 201, 0.06);
    box-shadow: 0 0 22px rgba(61, 242, 201, 0.16);
    transform: translateX(4px);
  }
  .it-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
  .it-n { font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--mu-2); }
  .it-dur {
    font-family: "Sora", system-ui, sans-serif;
    font-size: 22px; font-weight: 700; color: var(--tx);
    font-variant-numeric: tabular-nums; letter-spacing: -0.4px;
  }
  .itin.on .it-dur { color: var(--glow); }

  .it-fare { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .it-price { font-size: 13px; font-weight: 700; color: var(--a1); font-variant-numeric: tabular-nums; }
  .it-mode { font-size: 11.5px; color: var(--mu); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* Leg bar: proportional neon segments, one per transport type. */
  .legs { display: flex; align-items: center; gap: 4px; }
  .leg {
    height: 8px; border-radius: 9px; flex: 1 1 0;
    background: var(--c);
    box-shadow: 0 0 10px color-mix(in srgb, var(--c) 70%, transparent);
    transform-origin: left;
    animation: grow 0.7s cubic-bezier(.2,.9,.2,1) both;
  }
  @keyframes grow { from { transform: scaleX(0); } }

  .it-meta { display: flex; align-items: center; gap: 10px; color: var(--mu); font-size: 11.5px; }
  .it-meta span { display: inline-flex; align-items: center; gap: 4px; }
  .tag {
    font-size: 10.5px; font-weight: 700;
    padding: 3px 9px;
    border-radius: 99px;
    background: rgba(61, 242, 201, 0.14);
    color: var(--glow);
    margin-inline-start: auto;
  }

  .steps {
    list-style: none; margin: 3px 0 0; padding: 9px 0 0;
    border-top: 1px dashed rgba(200, 180, 255, 0.16);
    display: flex; flex-direction: column; gap: 7px;
  }
  .step { display: flex; align-items: center; gap: 9px; font-size: 11.5px; color: var(--mu); }
  .s-ic {
    display: grid; place-items: center;
    width: 22px; height: 22px; flex-shrink: 0;
    border-radius: 7px;
    background: color-mix(in srgb, var(--c) 20%, transparent);
    color: var(--c);
  }
  .s-tx { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .s-d { color: var(--mu-2); font-variant-numeric: tabular-nums; }

  /* Focus control: dim the rest of the network, or bring it back. */
  .focus-btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 8px;
    width: 100%; padding: 11px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--surf-2);
    color: var(--mu);
    font: 600 12px "DM Sans", system-ui, sans-serif;
    cursor: pointer;
    transition: all 0.25s ease;
  }
  .focus-btn:hover { border-color: var(--a1); color: var(--tx); }
  .focus-btn.on { border-color: var(--glow); color: var(--glow); background: rgba(61, 242, 201, 0.08); }
  .focus-note {
    display: flex; align-items: center; gap: 6px;
    margin: 0; font-size: 11px; color: var(--mu-2);
  }

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

  /* ── Station inspector ──────────────────────────────────────────────────── */
  .inspector {
    position: absolute;
    top: 16px; inset-inline-end: 16px;
    width: min(340px, calc(100% - 32px));
    max-height: calc(100% - 32px);
    overflow-y: auto;
    z-index: 720;
    padding: 15px;
    border: 1px solid var(--line);
    border-radius: 20px;
    background: var(--surf);
    backdrop-filter: blur(22px) saturate(1.4);
    box-shadow: 0 0 30px rgba(123, 92, 255, 0.18), 0 18px 50px rgba(0, 0, 0, 0.65);
    display: flex; flex-direction: column; gap: 12px;
    animation: slideIn 0.32s cubic-bezier(.2,.9,.2,1);
  }
  @keyframes slideIn { from { opacity: 0; transform: translateY(-10px); } }

  .ins-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
  .ins-title { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .ins-eyebrow { font-size: 10px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--glow); }
  .ins-title h3 { margin: 0; font-size: 17px; font-weight: 700; letter-spacing: -0.2px; }
  .ins-city { font-size: 11.5px; color: var(--mu); }
  .ins-close {
    display: grid; place-items: center;
    width: 30px; height: 30px; flex-shrink: 0;
    border-radius: 50%;
    border: 1px solid var(--line);
    background: var(--surf-2); color: var(--mu);
    cursor: pointer;
    transition: all 0.25s ease;
  }
  .ins-close:hover { border-color: var(--a1); color: var(--a1); transform: rotate(90deg); }
  .ins-loading { display: flex; align-items: center; gap: 8px; margin: 0; color: var(--mu); font-size: 12px; }

  .ins-modes { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .ins-mode {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 9px;
    border-radius: 99px;
    border: 1px solid color-mix(in srgb, var(--c) 45%, transparent);
    background: color-mix(in srgb, var(--c) 14%, transparent);
    color: var(--c);
    font-size: 11px; font-weight: 600;
  }
  .ins-mode.none { --c: var(--n-unk); }
  .ins-count { margin-inline-start: auto; font-size: 10.5px; color: var(--mu-2); font-variant-numeric: tabular-nums; }

  .ins-actions { display: flex; gap: 7px; }
  .ins-act {
    display: inline-flex; align-items: center; gap: 6px;
    flex: 1; justify-content: center;
    padding: 9px 8px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--surf-2);
    color: var(--tx);
    font: 600 11.5px "DM Sans", system-ui, sans-serif;
    cursor: pointer;
    transition: all 0.25s ease;
  }
  .ins-act:hover:not(:disabled) { border-color: var(--glow); color: var(--glow); }
  .ins-act:disabled { opacity: 0.45; cursor: not-allowed; }

  .lines { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 7px; }
  .line {
    display: flex; gap: 9px;
    padding: 9px;
    border: 1px solid var(--line);
    border-inline-start: 3px solid var(--c);
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.025);
  }
  .ln-ic {
    display: grid; place-items: center;
    width: 24px; height: 24px; flex-shrink: 0;
    border-radius: 8px;
    background: color-mix(in srgb, var(--c) 18%, transparent);
    color: var(--c);
  }
  .ln-body { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
  .ln-top { display: flex; align-items: baseline; gap: 7px; flex-wrap: wrap; }
  .ln-top b { font-size: 12.5px; color: var(--tx); }
  .ln-role { font-size: 10px; font-weight: 600; color: var(--c); }
  .ln-dir { font-size: 11px; color: var(--mu); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ln-meta { font-size: 10.5px; color: var(--mu-2); }
  .ins-none { margin: 0; font-size: 11.5px; color: var(--mu-2); }
  /* Louage connections: a sub-heading under the line list, and a button row per
     destination so a rider can jump to the place the terminal serves. */
  .ins-sub {
    margin: 12px 0 6px;
    font-size: 10.5px;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--mu-2);
    font-weight: 700;
  }
  .ln-btn {
    display: block;
    width: 100%;
    text-align: start;
    background: var(--surf-2);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 7px 9px;
    cursor: pointer;
    transition: border-color .15s, background .15s;
  }
  .ln-btn:hover { border-color: var(--n-louaj); background: rgba(0, 229, 192, .08); }
  .ln-btn:focus-visible { outline: 2px solid var(--n-louaj); outline-offset: 2px; }

  .legend {
    position: absolute;
    bottom: 16px; inset-inline-start: 16px;
    z-index: 700;
    padding: 8px 12px;
    border: 1px solid var(--line);
    border-radius: 99px;
    background: var(--surf);
    backdrop-filter: blur(16px);
    box-shadow: 0 8px 26px rgba(0, 0, 0, 0.6);
    max-width: min(340px, calc(100% - 32px));
  }
  .lg-grid { display: flex; flex-wrap: wrap; gap: 6px 14px; }
  .lg-i {
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; color: var(--mu);
    transition: opacity 0.3s ease;
  }
  .lg-i i { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 6px currentColor; }
  .lg-i.off { opacity: 0.32; text-decoration: line-through; }

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
  .side::-webkit-scrollbar, .inspector::-webkit-scrollbar { width: 8px; }
  .side::-webkit-scrollbar-track, .inspector::-webkit-scrollbar-track { background: transparent; }
  .side::-webkit-scrollbar-thumb, .inspector::-webkit-scrollbar-thumb {
    background: rgba(200, 180, 255, 0.16); border-radius: 4px;
    border: 2px solid transparent; background-clip: content-box;
  }
  .side::-webkit-scrollbar-thumb:hover, .inspector::-webkit-scrollbar-thumb:hover {
    background: rgba(200, 180, 255, 0.32); background-clip: content-box;
  }

  .app :focus-visible { outline: 2px solid var(--glow); outline-offset: 2px; border-radius: 10px; }

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
    .legend { display: none; }
    .inspector {
      top: auto; bottom: 12px; inset-inline: 12px;
      width: auto; max-height: 52%;
    }
  }
  @media (max-width: 420px) {
    .hdr { padding: 10px 13px; }
    .side { padding: 13px; }
    .brand-text small { display: none; }
  }

  @media (prefers-reduced-motion: reduce) {
    .app *, .app *::before, .app *::after {
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
