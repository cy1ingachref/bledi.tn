<script>
  import Board from '$lib/Board.svelte';
  import MapView from '$lib/MapView.svelte';
  import { ui } from '$lib/ui.svelte.js';
  import { dict } from '$lib/data.js';
  import { loadCatalog, modeColor } from '$lib/catalog.svelte.js';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { SvelteSet, SvelteURLSearchParams } from 'svelte/reactivity';

  // --- from/to: the *fuzzy* keys the user typed (display only) ---
  let fromText = $state('');
  let toText = $state('');
  let fromId = $state(null);
  let toId = $state(null);

  // --- picks: the station id we zoomed to (from/to) ---
  let fromPick = $state(null);
  let toPick = $state(null);

  // --- the *resolved* locations (lat/lon) we actually route over ---
  let startLat = $state(null);
  let startLon = $state(null);
  let endLat = $state(null);
  let endLon = $state(null);

  // --- suggestions lists (populated by the input listeners) ---
  let fromSuggestions = $state([]);
  let toSuggestions = $state([]);

  // debounce timers and loading states for geocode
  let fromTimeout = null;
  let toTimeout = null;
  let fromLoading = $state(false);
  let toLoading = $state(false);
  let fromError = $state(null);
  let toError = $state(null);

  // map zoom control (unlocked after we know where we are)
  let mapReady = $state(false);

  // stations rendered on the map — merged from the backend + the static catalog
  // (the catalog is the offline-safe fallback: it is built from the corrected
  // seed and shipped with the site, so the map shows the full network even
  // when no backend is running).
  let stations = $state([]);
  let loading = $state(true);

  // transport catalogue (static JSON)
  let catalog = $state([]);
  let catalogLoading = $state(true);

  const t = $derived(dict[ui.lang]);

  // safe coordinate formatter: 7 catalog stations have null lat/lon, and a
  // bare .toFixed() on null throws and aborts the whole panel render.
  const fmtCoord = (v) =>
    typeof v === 'number' && Number.isFinite(v) ? v.toFixed(4) : '—';

  // haversine helper (used for the nearby-station ordering)
  function haversine(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const toRad = (d) => (d * Math.PI) / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.asin(Math.sqrt(a));
  }

  // ---- merge the static catalog records into the map station list ----
  // The catalog is the authoritative, offline-capable source of every transport
  // resource (bus / louage / metro / rail / taxi / train / unknown). The backend
  // is merged on top when it answers, so a running backend can enrich the list.
  function mergeCatalog(raw) {
    if (!raw || !raw.modes) return;
    const out = [];
    const seen = new SvelteSet();
    for (const [mode, rec] of Object.entries(raw.modes)) {
      for (const st of rec.stations || []) {
        if (st.lat == null || st.lon == null) continue;
        if (seen.has(st.id)) continue;
        seen.add(st.id);
        out.push({
          id: st.id,
          name: st.name || st.id,
          lat: st.lat,
          lon: st.lon,
          mode: st.mode || mode,
          operator: st.operator || '',
        });
      }
    }
    if (out.length) stations = out;
  }

  // ---- resolve explicit coords from the two picks ----
  function reSolve() {
    if (fromId) {
      const a = stations.find((s) => s.id === fromId);
      if (a) { startLat = a.lat; startLon = a.lon; }
    }
    if (toId) {
      const b = stations.find((s) => s.id === toId);
      if (b) { endLat = b.lat; endLon = b.lon; }
    }
  }

  // ---- map: zoom to (and briefly highlight) a station ----
  function zoomTo(id) {
    mapReady = true;
    const st = stations.find((s) => s.id === id);
    if (st) reSolve();
  }

  // ---- nearby stations sorted by haversine distance to the from/to point ----
  function nearbyFrom() {
    if (!fromId) return [];
    const from = stations.find((s) => s.id === fromId);
    if (!from) return [];
    return stations
      .filter((s) => s.id !== fromId)
      .sort((a, b) => haversine(from.lat, from.lon, a.lat, a.lon) - haversine(from.lat, from.lon, b.lat, b.lon))
      .slice(0, 8)
      .map((s) => ({ id: s.id, name: s.name, lat: s.lat, lon: s.lon }));
  }

  function nearbyTo() {
    if (!toId) return [];
    const to = stations.find((s) => s.id === toId);
    if (!to) return [];
    return stations
      .filter((s) => s.id !== toId)
      .sort((a, b) => haversine(to.lat, to.lon, a.lat, a.lon) - haversine(to.lat, to.lon, b.lat, b.lon))
      .slice(0, 8)
      .map((s) => ({ id: s.id, name: s.name, lat: s.lat, lon: s.lon }));
  }

  // ---- geocode search via backend ----
  async function fetchGeocode(query, onResults, onLoading, onError) {
    const q = (query || '').trim();
    if (!q || q.length < 2) {
      onResults([]);
      onLoading(false);
      onError(null);
      return;
    }
    onLoading(true);
    onError(null);
    try {
      const res = await fetch('http://localhost:8000/api/v1/geocode?q=' + encodeURIComponent(q) + '&limit=8');
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        onResults([]);
        onError(body.error || 'Geocode failed');
        onLoading(false);
        return;
      }
      const data = await res.json();
      const results = (data.results || []).map((r) => ({
        id: 'geo:' + (r.lat != null ? r.lat.toFixed(4) : '0') + ':' + (r.lon != null ? r.lon.toFixed(4) : '0') + ':' + (r.display_name || '').replace(/\W+/g, '_'),
        name: r.display_name || r.name || r.display_name || '',
        lat: r.lat != null ? parseFloat(r.lat) : null,
        lon: r.lon != null ? parseFloat(r.lon) : null,
        mode: 'unknown',
        operator: '',
      }));
      onResults(results);
      onLoading(false);
    } catch {
      onResults([]);
      onError('Network error');
      onLoading(false);
    }
  }

  // ---- debounced input handlers ----
  function onFromInput(e) {
    fromText = e.currentTarget.value;
    if (fromTimeout) clearTimeout(fromTimeout);
    fromTimeout = setTimeout(() => {
      fetchGeocode(fromText, (results) => {
        fromSuggestions = results;
        if (results.length === 0) {
          // Fallback: try local station filter if nothing from geocode
          const q = (fromText || '').trim().toLowerCase();
          if (q) {
            fromSuggestions = stations
              .filter((s) => s.id !== fromId && s.name && s.name.toLowerCase().includes(q))
              .sort((a, b) => {
                const an = a.name.toLowerCase().startsWith(q) ? 0 : 1;
                const bn = b.name.toLowerCase().startsWith(q) ? 0 : 1;
                return an - bn || a.name.localeCompare(b.name);
              })
              .slice(0, 8)
              .map((s) => ({ id: s.id, name: s.name, lat: s.lat, lon: s.lon, mode: s.mode || 'unknown', operator: s.operator || '' }));
          } else {
            fromSuggestions = [];
          }
        }
      }, (loading) => { fromLoading = loading; }, (err) => { fromError = err; });
    }, 250);
    // Clear fromId if text no longer matches
    if (fromId) {
      const hit = stations.find((s) => s.id === fromId);
      if (hit && hit.name !== fromText) {
        fromId = null;
        fromPick = null;
        startLat = null; startLon = null;
      }
    }
  }
  function onToInput(e) {
    toText = e.currentTarget.value;
    if (toTimeout) clearTimeout(toTimeout);
    toTimeout = setTimeout(() => {
      fetchGeocode(toText, (results) => {
        toSuggestions = results;
        if (results.length === 0) {
          const q = (toText || '').trim().toLowerCase();
          if (q) {
            toSuggestions = stations
              .filter((s) => s.id !== toId && s.name && s.name.toLowerCase().includes(q))
              .sort((a, b) => {
                const an = a.name.toLowerCase().startsWith(q) ? 0 : 1;
                const bn = b.name.toLowerCase().startsWith(q) ? 0 : 1;
                return an - bn || a.name.localeCompare(b.name);
              })
              .slice(0, 8)
              .map((s) => ({ id: s.id, name: s.name, lat: s.lat, lon: s.lon, mode: s.mode || 'unknown', operator: s.operator || '' }));
          } else {
            toSuggestions = [];
          }
        }
      }, (loading) => { toLoading = loading; }, (err) => { toError = err; });
    }, 250);
    if (toId) {
      const hit = stations.find((s) => s.id === toId);
      if (hit && hit.name !== toText) {
        toId = null;
        toPick = null;
        endLat = null; endLon = null;
      }
    }
  }
  function closeFrom() { /* keep typed value */ }
  function closeTo() { /* keep typed value */ }

  function pickFrom(id) {
    let st = stations.find((s) => s.id === id);
    if (!st) {
      // If it's a geocode result that hasn't been added yet, try from suggestions
      const sugg = fromSuggestions.find((s) => s.id === id);
      if (sugg) {
        st = sugg;
        // Add to stations temporarily
        stations = [...stations, { ...st }];
      } else {
        return;
      }
    }
    fromId = id;
    fromText = st.name;
    fromSuggestions = [];
    fromError = null;
    reSolve();
    zoomTo(id);
  }
  function pickTo(id) {
    let st = stations.find((s) => s.id === id);
    if (!st) {
      const sugg = toSuggestions.find((s) => s.id === id);
      if (sugg) {
        st = sugg;
        stations = [...stations, { ...st }];
      } else {
        return;
      }
    }
    toId = id;
    toText = st.name;
    toSuggestions = [];
    toError = null;
    reSolve();
    zoomTo(id);
  }

  function swap() {
    const ft = fromText, fi = fromId, fp = fromPick;
    fromText = toText; fromId = toId; fromPick = toPick;
    toText = ft; toId = fi; toPick = fp;
    fromSuggestions = []; toSuggestions = [];
    reSolve();
  }

  // ---- URL-parameter routing (from=/to=) ----
  function syncUrl() {
    try {
      const params = new SvelteURLSearchParams();
      if (startLat != null && startLon != null) {
        params.set('from', `${startLat.toFixed(5)},${startLon.toFixed(5)}`);
      }
      if (endLat != null && endLon != null) {
        params.set('to', `${endLat.toFixed(5)},${endLon.toFixed(5)}`);
      }
      history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`);
    } catch { /* window/history unavailable (SSR) */ }
  }

  function applyUrlParams() {
    try {
      const params = new URLSearchParams(window.location.search);
      const f = params.get('from');
      const tt = params.get('to');
      if (f && fromText === '') {
        const [la, lo] = f.split(',').map(Number);
        if (la != null && lo != null) {
          const hit = stations.find((s) => Math.abs(s.lat - la) < 1e-4 && Math.abs(s.lon - lo) < 1e-4);
          if (hit) { fromText = hit.name; fromId = hit.id; fromPick = hit.id; zoomTo(hit.id); }
        }
      }
      if (tt && toText === '') {
        const [la, lo] = tt.split(',').map(Number);
        if (la != null && lo != null) {
          const hit = stations.find((s) => Math.abs(s.lat - la) < 1e-4 && Math.abs(s.lon - lo) < 1e-4);
          if (hit) { toText = hit.name; toId = hit.id; toPick = hit.id; zoomTo(hit.id); }
        }
      }
    } catch { /* window unavailable (SSR) */ }
  }

  // ---- auth check ----
  $effect(() => {
    document.documentElement.lang = ui.lang;
    document.documentElement.dir = ui.lang === 'ar' ? 'rtl' : 'ltr';
  });

  $effect(() => {
    syncUrl();
  });

  onMount(() => {
    const auth = localStorage.getItem('bledi_auth');
    if (!auth) {
      goto(resolve('/login'));
      return;
    }
    try {
      const parsed = JSON.parse(auth);
      if (!parsed.email || !parsed.token) {
        localStorage.removeItem('bledi_auth');
        goto(resolve('/login'));
      }
    } catch {
      localStorage.removeItem('bledi_auth');
      goto(resolve('/login'));
    }
  });

  // ---- data load ----
  onMount(async () => {
    // Load catalog but don't populate stations yet (wait for both from/to selection)
    try {
      const raw = await loadCatalog();
      catalog = raw;
      catalogLoading = false;
      applyUrlParams();
    } catch {
      catalogLoading = false;
    }
  });

  // Only populate stations when both fromId and toId are selected
  $effect(() => {
    if (fromId && toId) {
      if (catalog && catalog.modes) {
        mergeCatalog(catalog);
      }
      (async () => {
        try {
          const res = await fetch('http://localhost:8000/api/v1/stations');
          if (res.ok) {
            const data = await res.json();
            const feats = (data.features || [])
              .filter((f) => f.properties && f.geometry && f.geometry.coordinates)
              .map((f) => ({
                id: f.properties.id,
                name: f.properties.name,
                lat: f.geometry.coordinates[1],
                lon: f.geometry.coordinates[0],
                mode: f.properties.mode || 'unknown',
                operator: f.properties.operator || '',
              }));
            if (feats.length) {
              stations = feats;
            }
            reSolve();
            applyUrlParams();
            loading = false;
          } else {
            if (catalog && catalog.modes && stations.length === 0) {
              mergeCatalog(catalog);
              loading = false;
            }
          }
        } catch {
          if (catalog && catalog.modes && stations.length === 0) {
            mergeCatalog(catalog);
            loading = false;
          }
        }
      })();
    } else {
      // Minimal state: keep stations empty when one or both ids missing
      if (stations.length > 0) {
        stations = [];
      }
      loading = true;
    }
  });
</script>

<svelte:head>
  <title>bledi.tn — Tunisia Transit</title>
</svelte:head>

<main>
  <MapView
    path={[]}
    rtl={ui.lang === 'ar'}
    {stations}
    {startLat}
    {startLon}
    {endLat}
    {endLon}
    {mapReady}
    {zoomTo}
  />

  <section class="panel">
    <header>
          <h1>bledi<span>.tn</span></h1>
          <div class="header-actions">
            <button class="memories-link" onclick={() => goto(resolve('/memories'))}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
              Memories
            </button>
            <div class="langs" role="group" aria-label="Language">
              {#each [['fr', 'FR'], ['ar', 'ع'], ['en', 'EN']] as [code, label]}
                <button aria-pressed={ui.lang === code} onclick={() => (ui.lang = code)}>{label}</button>
              {/each}
            </div>
          </div>
        </header>

    <div class="search">
      <div class="autocomplete">
        <i class="dot a"></i>
        <input
          aria-label={t.from}
          placeholder={t.from}
          value={fromText}
          oninput={onFromInput}
          onblur={closeFrom}
          onfocus={closeFrom}
          autocomplete="off"
        />
        <datalist id="from-suggest">
          {#each fromSuggestions as s}
            <option value={s.name}></option>
          {/each}
        </datalist>
        <div class="suggestions">
          {#if fromLoading}
            <span class="loading" style="padding: 6px 8px; display:block;">Searching places...</span>
          {:else if fromError}
            <span class="loading" style="padding: 6px 8px; display:block; color: var(--red);">{fromError}</span>
          {/if}
          {#each fromSuggestions as s}
            <button class="suggestion" onclick={() => pickFrom(s.id)}>
              <span class="name">{s.name}</span>
              <span class="meta">{fmtCoord(s.lat)}, {fmtCoord(s.lon)}</span>
            </button>
          {/each}
        </div>
        <div class="nearby" class:hidden={!fromId}>
          {#each nearbyFrom() as s}
            <button class="suggestion" onclick={() => pickFrom(s.id)}>
              <span class="name">{s.name}</span>
              <span class="meta">{fmtCoord(s.lat)}, {fmtCoord(s.lon)}</span>
            </button>
          {/each}
        </div>
      </div>

      <div class="swap" onclick={swap} aria-label={t.swap}>
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 4v16M4 8l4-4 4 4M16 20V4M12 16l4 4 4-4" /></svg>
      </div>

      <div class="autocomplete">
        <i class="dot b"></i>
        <input
          aria-label={t.to}
          placeholder={t.to}
          value={toText}
          oninput={onToInput}
          onblur={closeTo}
          onfocus={closeTo}
          autocomplete="off"
        />
        <datalist id="to-suggest">
          {#each toSuggestions as s}
            <option value={s.name}></option>
          {/each}
        </datalist>
        <div class="suggestions">
          {#if toLoading}
            <span class="loading" style="padding: 6px 8px; display:block;">Searching places...</span>
          {:else if toError}
            <span class="loading" style="padding: 6px 8px; display:block; color: var(--red);">{toError}</span>
          {/if}
          {#each toSuggestions as s}
            <button class="suggestion" onclick={() => pickTo(s.id)}>
              <span class="name">{s.name}</span>
              <span class="meta">{fmtCoord(s.lat)}, {fmtCoord(s.lon)}</span>
            </button>
          {/each}
        </div>
        <div class="nearby" class:hidden={!toId}>
          {#each nearbyTo() as s}
            <button class="suggestion" onclick={() => pickTo(s.id)}>
              <span class="name">{s.name}</span>
              <span class="meta">{fmtCoord(s.lat)}, {fmtCoord(s.lon)}</span>
            </button>
          {/each}
        </div>
      </div>

      <button class="go" aria-label="Go" onclick={() => { fromPick = null; toPick = null; reSolve(); }}>
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
      </button>
    </div>

    <div class="status">
      {#if !fromId || !toId}
        <span class="loading">Select start and destination to view nearby stations and routes.</span>
      {:else if loading}
        <span class="loading">Loading stations...</span>
      {:else}
        <span class="count">{stations.length} stations</span>
      {/if}
    </div>

    <!-- pending route: feedback AFTER the user confirms (continues the FROM/TO) -->
    {#if false}
      <Board color="#1F6F8B" to={{fr:'—',ar:''}} minutes="" unit={t?.min ?? ''} />
    {/if}

    <div class="options" role="radiogroup" aria-label="Itinéraires">
      <div class="empty-state" style="padding: 12px; color: var(--muted); font-size: 0.9rem; text-align: center; width: 100%;">
        Route options unavailable — select stations to load transport plans.
      </div>
    </div>

    <ol class="steps">
      {#each [] as s}
        <li class={s.kind} style:--c={s.kind === 'walk' ? 'var(--muted)' : '#1F6F8B'}>
          <span>{s.label?.[ui.lang] ?? ''}</span>
          <small>{s.min ?? ''} {t?.min ?? ''}</small>
        </li>
      {/each}
      <li class="note-step" style="--c:var(--muted); padding-inline-start: 34px; font-size: 0.8rem; color: var(--muted);">
        <span>No active route — steps will appear once a transport plan is loaded.</span>
      </li>
    </ol>

    <!-- Transport catalogue panel -->
    <section class="catalog-section" aria-label="Transit resource catalog">
      <header>
        <h2>All transport resources</h2>
        <p class="sub">Every transport mean rendered: mode → station → line → route beginning, with coordinates and plan.</p>
      </header>

      {#if catalogLoading}
        <span class="loading">Loading catalog...</span>
      {:else if catalog && catalog.modes && Object.values(catalog.modes).length}
        <div class="catalog-grid">
          {#each Object.values(catalog.modes) as cat (cat.mode)}
            <div class="mode-card">
              <div class="mode-head">
                <span class="mode-dot" style="background:{modeColor(cat.mode)}"></span>
                <h3>{cat.name || cat.mode}</h3>
                <span class="mode-count">{cat.stations.length} stations</span>
              </div>
              <ul class="stations">
                {#each cat.stations as st (st.id)}
                  <li class="station">
                    <span class="name">{st.name}</span>
                    <span class="hub">{fmtCoord(st.lat)}, {fmtCoord(st.lon)}</span>
                    {#if st.lines_served && st.lines_served.length}
                      <ul class="lines">
                        {#each st.lines_served as ln}
                          <li class="line">
                            <span class="num">{ln.route_short_name ?? ln.route_id}</span>
                            <span class="dir">{ln.direction}</span>
                            <span class="color" style="background:{ln.route_color || '#999'}"></span>
                          </li>
                        {/each}
                      </ul>
                    {/if}
                    <span class="operator">{st.operator}</span>
                  </li>
                {/each}
              </ul>
              {#if cat.lines && cat.lines.length}
                <ul class="lines">
                  {#each cat.lines as ln (ln.id)}
                    <li class="line">
                      <span class="num">{ln.number ?? ln.id}</span>
                      <span class="name">{ln.name}</span>
                      <span class="mode">{ln.type ?? ln.mode}</span>
                    </li>
                  {/each}
                </ul>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    </section>
  </section>
</main>

<style>
  main { position: fixed; inset: 0; }
  .panel {
    position: absolute; inset-inline: 0; bottom: 0; z-index: 1001; max-height: 68dvh; overflow: auto;
    display: grid; gap: 14px; padding: 16px; background: var(--paper);
    border-radius: 20px 20px 0 0; box-shadow: 0 -8px 30px #0f223033;
  }
  @media (min-width: 800px) {
    .panel { inset: 16px auto 16px 16px; width: 420px; max-height: none; border-radius: 20px; align-content: start; }
    :global([dir='rtl']) .panel { inset: 16px 16px 16px auto; }
  }
  header { display: flex; align-items: center; justify-content: space-between; }
  .header-actions { display: flex; align-items: center; gap: 10px; }
  .memories-link {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 7px 14px; border-radius: 10px; font-size: 0.85rem; font-weight: 600;
    background: var(--sea); color: #fff; border: none; cursor: pointer;
  }
  .memories-link:hover { filter: brightness(1.15); }
  h1 { margin: 0; font-size: 1.6rem; font-weight: 700; letter-spacing: -0.02em; }
  h1 span { color: var(--sea); }
  .langs { display: flex; gap: 4px; }
  .langs button { min-width: 40px; height: 36px; border: 1px solid var(--rule); border-radius: 10px; background: #fff; }
  .langs button[aria-pressed='true'] { background: var(--ink); border-color: var(--ink); color: #fff; }

  .search { position: relative; display: grid; gap: 8px; }
  .search::before {
    content: ''; position: absolute; inset-inline-start: 21px; inset-block: 30px; width: 2px; background: var(--rule);
  }
  .search input {
    width: 100%; padding-block: 13px; padding-inline: 44px 60px;
    border: 1px solid var(--rule); border-radius: 12px; background: #fff;
  }
  .autocomplete { position: relative; }
  .suggestions { position: absolute; inset-inline-start: 0; inset-block: 100%; z-index: 10; }
  .nearby { position: absolute; inset-inline-start: 0; inset-block: 100%; z-index: 10; }
  .suggestions, .nearby { max-height: 240px; overflow: auto; }
  .suggestion {
    display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px;
    text-align: start; width: 100%; padding: 6px 8px; border-radius: 8px;
    background: #fff; border: 1px solid var(--rule); cursor: pointer;
  }
  .suggestion:hover, .suggestion:focus { background: var(--ink); color: #fff; border-color: var(--ink); }
  .name { font-size: 0.82rem; font-weight: 600; }
  .meta { font-size: 0.72rem; color: var(--sea); font-variant-numeric: tabular-nums; }
  .suggestion:focus .meta, .suggestion:hover .meta { color: #fff; }
  .dot { position: absolute; inset-inline-start: 15px; width: 14px; height: 14px; border-radius: 50%; z-index: 1; border: 3px solid #fff; }
  .dot.a { top: 19px; background: var(--sea); }
  .dot.b { bottom: 19px; background: var(--red); }
  .swap {
    position: absolute; inset-inline-end: 8px; top: 50%; translate: 0 -50%;
    width: 40px; height: 40px; border: 1px solid var(--rule); border-radius: 50%; background: #fff;
  }
  .go {
    position: absolute; inset-inline-end: 8px; top: 50%; translate: 0 -50%;
    width: 40px; height: 40px; border: 1px solid var(--rule); border-radius: 50%; background: #fff;
  }
  .go:hover { background: var(--ink); color: #fff; border-color: var(--ink); }

  .status { text-align: center; font-size: 0.85rem; color: var(--muted); }
  .status .count { color: var(--sea); font-weight: 600; }
  .status .loading { font-style: italic; }

  .badge { padding: 3px 9px; border-radius: 7px; color: #fff; font-size: 0.85rem; font-weight: 700; }
  .options { display: flex; gap: 8px; }
  .options button {
    flex: 1; display: grid; gap: 2px; justify-items: start; padding: 10px 12px; text-align: start;
    border: 1.5px solid var(--rule); border-radius: 12px; background: #fff;
  }
  .options button.on { border-color: var(--ink); box-shadow: 0 0 0 1px var(--ink); }
  .times { color: var(--muted); font-size: 0.85rem; font-variant-numeric: tabular-nums; }

  .steps { list-style: none; margin: 0; padding: 0; }
  .steps li { position: relative; display: flex; justify-content: space-between; gap: 12px; padding: 6px 0 16px; padding-inline-start: 34px; }
  .steps li::before { content: ''; position: absolute; inset-inline-start: 7px; top: 14px; bottom: -6px; border-inline-start: 3px solid var(--c); }
  .steps li.walk::before { border-inline-start-style: dotted; }
  .steps li::after {
    content: ''; position: absolute; inset-inline-start: 2px; top: 8px; width: 13px; height: 13px;
    border-radius: 50%; background: #fff; border: 3px solid var(--c);
  }
  .steps li:last-child::before { display: none; }
  .steps small { color: var(--muted); white-space: nowrap; }

  .hidden { opacity: 0; transform: translateY(-8px); max-height: 0; overflow: hidden; pointer-events: none; transition: opacity 0.3s ease, transform 0.3s ease, max-height 0.3s ease; }

  /* --- Transport resources section --- */
  .catalog-section {
    margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--rule);
    display: grid; gap: 14px;
  }
  .catalog-section header h2 { margin: 0 0 4px; font-size: 1.25rem; font-weight: 700; }
  .catalog-section header .sub { margin: 0 0 12px; color: var(--muted); font-size: 0.9rem; }

  .catalog-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px;
  }
  .mode-card {
    background: var(--paper); border: 1px solid var(--rule); border-radius: 14px; padding: 14px;
  }
  .mode-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .mode-dot { width: 12px; height: 12px; border-radius: 50%; flex: 0 0 auto; }
  .mode-card h3 { margin: 0 0 4px; font-size: 0.95rem; font-weight: 700; }
  .mode-count { font-size: 0.8rem; color: var(--muted); }

  .stations { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
  .station {
    display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px; padding: 6px 8px;
    border-radius: 8px; background: #fff; border: 1px solid var(--rule);
  }
  .station .name { font-size: 0.82rem; font-weight: 600; }
  .station .hub { font-size: 0.72rem; color: var(--sea); font-variant-numeric: tabular-nums; }
  .station .operator { font-size: 0.7rem; color: var(--muted); margin-top: 3px; }

  .station .lines { list-style: none; margin: 6px 0 0; padding: 0; display: grid; gap: 3px; }
  .station .lines .line {
    display: flex; flex-wrap: wrap; align-items: center; gap: 5px; font-size: 0.72rem;
    padding: 3px 6px; border-radius: 6px; background: #fff; border: 1px solid var(--rule);
  }
  .station .lines .line .num { font-weight: 700; min-width: 28px; }
  .station .lines .line .dir { flex: 1 1 auto; color: var(--sea); }

  .step { margin-top: 8px; font-size: 0.82rem; color: var(--muted); }
</style>
