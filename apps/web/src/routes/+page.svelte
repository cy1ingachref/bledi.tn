<script>
  import MapView from '$lib/MapView.svelte';
  import { ui } from '$lib/ui.svelte.js';
  import { dict, routes, fetchRoutePlan, normalizeRoutes, modeColors } from '$lib/data.js';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { SvelteURLSearchParams } from 'svelte/reactivity';

  let fromText = $state('');
  let toText = $state('');
  let fromId = $state(null);
  let toId = $state(null);

  let startLat = $state(null);
  let startLon = $state(null);
  let endLat = $state(null);
  let endLon = $state(null);

  let fromSuggestions = $state([]);
  let toSuggestions = $state([]);

  const MODES = ['bus', 'train', 'louage'];
  const modes = $state(MODES);

  let routeOptions = $state([]);
  let selectedOption = $state(null);
  let routeMinutes = $state(null);

  let fromTimeout = null;
  let toTimeout = null;
  let fromLoading = $state(false);
  let toLoading = $state(false);
  let fromError = $state(null);
  let toError = $state(null);
  let fromSeq = 0;
  let toSeq = 0;
  let fromAbort = null;
  let toAbort = null;

  let mapReady = $state(false);
  let stations = $state([]);
  let loading = $state(true);

  const t = $derived(dict[ui.lang]);

  const modeBadge = (mode) => ({train:'TGM/Train',bus:'Bus',louaj:'Louage',taxi:'Taxi',walk:'Marche'})[mode] || mode;

  const cityLabel = (text) => {
    if (!text) return '—';
    return text.split(',')[0].trim();
  };

  const fmtCoord = (v) =>
    typeof v === 'number' && Number.isFinite(v) ? v.toFixed(4) : '—';

  function reSolve() {
    if (fromId && startLat == null) {
      const a = stations.find((s) => s.id === fromId) || fromSuggestions.find((s) => s.id === fromId);
      if (a) { startLat = a.lat; startLon = a.lon; }
    }
    if (toId && endLat == null) {
      const b = stations.find((s) => s.id === toId) || toSuggestions.find((s) => s.id === toId);
      if (b) { endLat = b.lat; endLon = b.lon; }
    }
  }

  function zoomTo(id) {
    mapReady = true;
    const st = stations.find((s) => s.id === id);
    if (st) reSolve();
  }

  async function fetchGeocode(query) {
    const q = (query || '').trim();
    if (!q || q.length < 1) return [];
    const res = await fetch('/api/v1/geocode?q=' + encodeURIComponent(q) + '&limit=8');
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || 'Geocode failed');
    }
    const data = await res.json();
    return (data.results || []).map((r) => ({
      id: 'geo:' + (Number.isFinite(r.lat) ? r.lat.toFixed(4) : '0') + ':' + (Number.isFinite(r.lon) ? r.lon.toFixed(4) : '0') + ':' + (r.display_name || '').replace(/\W+/g, '_'),
      name: r.display_name || r.name || r.display_name || '',
      lat: Number.isFinite(r.lat) ? r.lat : null,
      lon: Number.isFinite(r.lon) ? r.lon : null,
      mode: 'unknown',
      operator: '',
      type: r.type || '',
    }));
  }

  async function onFromInput(e) {
    fromText = e.currentTarget.value;
    if (fromTimeout) clearTimeout(fromTimeout);
    if (fromAbort) fromAbort.abort();
    const seq = ++fromSeq;
    fromAbort = new AbortController();
    fromTimeout = setTimeout(async () => {
      try {
        const results = await fetchGeocode(fromText);
        if (seq !== fromSeq) return;
        fromSuggestions = results;
        if (results.length === 0) {
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
              .map((s) => ({ id: s.id, name: s.name, lat: s.lat, lon: s.lon, mode: s.mode || 'unknown', operator: s.operator || '', type: s.mode || 'station' }));
          } else {
            fromSuggestions = [];
          }
        } else {
          const q = (fromText || '').trim();
          const hit = results.find((s) => s.name === q);
          if (hit) pickFrom(hit.id);
        }
      } catch (err) {
        if (err.name === 'AbortError') return;
        fromError = err.message ?? 'Network error';
      } finally {
        fromLoading = false;
      }
    }, 180);
    if (fromId) {
      const hit = stations.find((s) => s.id === fromId);
      if (hit && hit.name !== fromText) {
        fromId = null;
        startLat = null; startLon = null;
      }
    }
  }

  async function onToInput(e) {
    toText = e.currentTarget.value;
    if (toTimeout) clearTimeout(toTimeout);
    if (toAbort) toAbort.abort();
    const seq = ++toSeq;
    toAbort = new AbortController();
    toTimeout = setTimeout(async () => {
      try {
        const results = await fetchGeocode(toText);
        if (seq !== toSeq) return;
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
              .map((s) => ({ id: s.id, name: s.name, lat: s.lat, lon: s.lon, mode: s.mode || 'unknown', operator: s.operator || '', type: s.mode || 'station' }));
          } else {
            toSuggestions = [];
          }
        } else {
          const q = (toText || '').trim();
          const hit = results.find((s) => s.name === q);
          if (hit) pickTo(hit.id);
        }
      } catch (err) {
        if (err.name === 'AbortError') return;
        toError = err.message ?? 'Network error';
      } finally {
        toLoading = false;
      }
    }, 180);
    if (toId) {
      const hit = stations.find((s) => s.id === toId);
      if (hit && hit.name !== toText) {
        toId = null;
        endLat = null; endLon = null;
      }
    }
  }

  function closeFrom() { /* keep typed value */ }
  function closeTo() { /* keep typed value */ }

  function pickFrom(id) {
    let st = stations.find((s) => s.id === id);
    if (!st) {
      const sugg = fromSuggestions.find((s) => s.id === id);
      if (sugg) {
        st = sugg;
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
    const ft = fromText, fi = fromId;
    fromText = toText; fromId = toId;
    toText = ft; toId = fi;
    fromSuggestions = []; toSuggestions = [];
    reSolve();
  }

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
        if (Number.isFinite(la) && Number.isFinite(lo)) {
          const hit = stations.find((s) => Math.abs(s.lat - la) < 1e-4 && Math.abs(s.lon - lo) < 1e-4);
          if (hit) { fromText = hit.name; fromId = hit.id; zoomTo(hit.id); }
        }
      }
      if (tt && toText === '') {
        const [la, lo] = tt.split(',').map(Number);
        if (Number.isFinite(la) && Number.isFinite(lo)) {
          const hit = stations.find((s) => Math.abs(s.lat - la) < 1e-4 && Math.abs(s.lon - lo) < 1e-4);
          if (hit) { toText = hit.name; toId = hit.id; zoomTo(hit.id); }
        }
      }
    } catch { /* window unavailable (SSR) */ }
  }

  $effect(() => {
    document.documentElement.lang = ui.lang;
    document.documentElement.dir = ui.lang === 'ar' ? 'rtl' : 'ltr';
    localStorage.setItem('bledi_lang', ui.lang);
  });

  let displayStations = $state([]);

  function computeRelevantStations(route, allStations) {
    if (!Array.isArray(allStations) || !allStations.length) return [];
    if (!route) return [];

    const names = new Set();
    const latLons = [];
    if (startLat != null && startLon != null) latLons.push([startLat, startLon]);
    if (endLat != null && endLon != null) latLons.push([endLat, endLon]);

    for (const leg of (route.legs || route.steps || [])) {
      if (leg.from_name) names.add(leg.from_name.trim().toLowerCase());
      if (leg.to_name) names.add(leg.to_name.trim().toLowerCase());
      if (Array.isArray(leg.geometry)) {
        for (const pt of leg.geometry) {
          if (Array.isArray(pt) && pt.length >= 2) latLons.push([pt[0], pt[1]]);
        }
      }
    }

    if (!latLons.length && !names.size) return [];

    const R = 6371000;
    const toRad = (v) => v * Math.PI / 180;

    return allStations.filter((s) => {
      if (s.lat == null || s.lon == null) return false;
      const name = (s.name || '').trim().toLowerCase();
      if (names.has(name)) return true;
      if (!latLons.length) return false;

      const threshold = s.mode === 'louaj' ? 1000 : 350;
      let minDist = Infinity;
      for (const [la, lo] of latLons) {
        const dLat = toRad(la - s.lat);
        const dLon = toRad(lo - s.lon);
        const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(s.lat)) * Math.cos(toRad(la)) * Math.sin(dLon / 2) ** 2;
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        const d = R * c;
        if (d < minDist) minDist = d;
      }
      return minDist <= threshold;
    });
  }

  $effect(() => {
    const activeRoute = routeOptions.find((o) => o.id === selectedOption) ?? routeOptions[0];
    displayStations = computeRelevantStations(activeRoute, stations);
  });

  onMount(() => {
    const savedLang = localStorage.getItem('bledi_lang');
    if (savedLang) ui.lang = savedLang;

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
    } catch (err) {
      console.error('Auth parse failed', err);
      localStorage.removeItem('bledi_auth');
      goto(resolve('/login'));
    }

    (async () => {
      try {
        const res = await fetch('/api/v1/stations');
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
              type: f.properties.mode || 'station',
            }));
          if (feats.length) {
            stations = feats;
          }
        }
      } catch (err) {
        console.error('stations fetch failed', err);
      } finally {
        applyUrlParams();
        reSolve();
        loading = false;
      }
    })();
  });

  $effect(() => {
    const modes = MODES;
    if (startLat != null && startLon != null && endLat != null && endLon != null) {
      (async () => {
        try {
          const res = await fetchRoutePlan({ startLat, startLon, endLat, endLon, modes });
          const normalized = normalizeRoutes(res);
          if (normalized.length > 0) {
            routeOptions = normalized;
            if (!selectedOption || !routeOptions.some((o) => o.id === selectedOption)) {
              selectedOption = routeOptions[0].id;
            }
            routeMinutes = routeOptions.find((o) => o.id === selectedOption)?.minutes ?? routeOptions[0].minutes;
          } else {
            routeOptions = [];
            selectedOption = null;
            routeMinutes = null;
          }
        } catch (err) {
          console.error('route plan failed', err);
          routeOptions = [];
          selectedOption = null;
          routeMinutes = null;
        }
      })();
    } else {
      routeOptions = [];
      selectedOption = null;
      routeMinutes = null;
    }
  });
</script>

<svelte:head>
  <title>bledi.tn — Tunisia Transit</title>
</svelte:head>

<main>
  <MapView
    path={routeOptions.find((o) => o.id === selectedOption)?.path ?? routeOptions[0]?.path ?? []}
    rtl={ui.lang === 'ar'}
    stations={displayStations}
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
          bind:value={fromText}
          oninput={onFromInput}
          onchange={(e) => {
            const q = (e.currentTarget.value || '').trim();
            if (!q) return;
            const hit = [...stations, ...fromSuggestions].find((s) => s.name === q);
            if (hit) pickFrom(hit.id);
          }}
          autocomplete="off"
          list="from-suggest"
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
            <button class="suggestion" tabindex="-1" onmousedown={(e) => { e.preventDefault(); pickFrom(s.id); }}>
              <span class="name">{s.name}</span>
              <span class="meta">{s.type || ''} · {fmtCoord(s.lat)}, {fmtCoord(s.lon)}</span>
            </button>
          {/each}
        </div>
      </div>

      <button class="swap" onclick={swap} aria-label={t.swap}>
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 4v16M4 8l4-4 4 4M16 20V4M12 16l4 4-6 6" /></svg>
      </button>

      <div class="autocomplete">
        <i class="dot b"></i>
        <input
          aria-label={t.to}
          placeholder={t.to}
          bind:value={toText}
          oninput={onToInput}
          onchange={(e) => {
            const q = (e.currentTarget.value || '').trim();
            if (!q) return;
            const hit = [...stations, ...toSuggestions].find((s) => s.name === q);
            if (hit) pickTo(hit.id);
          }}
          autocomplete="off"
          list="to-suggest"
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
            <button class="suggestion" tabindex="-1" onmousedown={(e) => { e.preventDefault(); pickTo(s.id); }}>
              <span class="name">{s.name}</span>
              <span class="meta">{s.type || ''} · {fmtCoord(s.lat)}, {fmtCoord(s.lon)}</span>
            </button>
          {/each}
        </div>
      </div>

      <button class="go" aria-label="Go" onclick={() => { reSolve(); }}>
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
      </button>
    </div>

    <div class="status">
      {#if !fromId || !toId}
        <span class="loading">Select start and destination to view nearby stations and routes.</span>
      {:else if loading}
        <span class="loading">Loading stations...</span>
      {:else if routeOptions.length > 0}
        <span class="count">{displayStations.length} stations</span>
      {/if}
    </div>

    {#if fromId && toId}
      {@const activeOpt = routeOptions.find((o) => o.id === selectedOption) ?? routeOptions[0]}
      <div class="board" aria-live="polite">
        <span class="badge" style:background={activeOpt?.color ?? '#1F6F8B'}>{activeOpt?.badge ?? '—'}</span>
        <div class="dest">
          <p class="fr">{cityLabel(fromText)} → {cityLabel(toText)}</p>
          <p class="ar" dir="rtl"></p>
        </div>
        <p class="eta">
          <strong>{activeOpt?.minutes ? String(activeOpt.minutes) : (routeMinutes ? String(routeMinutes) : '—')}</strong> {t?.min ?? 'min'}
        </p>
      </div>
    {/if}

    <div class="options" role="radiogroup" aria-label="Itinéraires">
      {#each routeOptions as opt}
        <button
          role="radio"
          aria-checked={selectedOption === opt.id}
          class:on={selectedOption === opt.id}
          onclick={() => (selectedOption = opt.id)}
        >
          <span class="badge" style:background={opt.color}>{opt.badge}</span>
          <span class="times"><bdi>{opt.depart}–{opt.arrive}</bdi></span>
          <strong>{opt.minutes} {t?.min ?? 'min'}</strong>
          {#if opt.identifier}
            <span class="opt-id">{opt.identifier}</span>
          {/if}
          {#if opt.fare_dinars != null && opt.fare_dinars > 0}
            <span class="opt-fare">{opt.fare_dinars} DT</span>
          {/if}
        </button>
      {:else}
        <button type="button" class="empty-state" style="padding: 12px; color: var(--muted); font-size: 0.9rem; text-align: center; width: 100%;">
          Route options unavailable — select stations to load transport plans.
        </button>
      {/each}
    </div>

    <ol class="steps">
      {#each (routeOptions.find((o) => o.id === selectedOption) ?? routeOptions[0])?.steps ?? [] as s, i}
        {@const seq = i + 1}
        {@const isLast = seq === ((routeOptions.find((o) => o.id === selectedOption) ?? routeOptions[0])?.steps?.length ?? 0)}
        {@const ride = s.kind === 'ride'}
        <li
          class={s.kind}
          style:--c={s.kind === 'walk' ? 'var(--muted)' : (modeColors[s.mode] || routeOptions.find((o) => o.id === selectedOption)?.color || '#1F6F8B')}
          class:milestone={ride && isLast}
        >
          <div class="step-main">
            <span>{s.label?.[ui.lang] ?? s.label?.fr ?? ''}</span>
            {#if s.identifier}
              <span class="step-id">{s.identifier}</span>
            {/if}
          </div>
          <div class="step-meta">
            <small>{s.min ?? ''} {t?.min ?? ''}</small>
            {#if Array.isArray(s.stations) && s.stations.length}
              <span class="stations">→ {s.stations.join(' · ')}</span>
            {/if}
            {#if typeof s.fare_dinars === 'number' && s.fare_dinars > 0}
              <span class="fare">{s.fare_dinars} DT</span>
            {/if}
            {#if ride && isLast}
              <span class="milestone-badge" style:background={routeOptions.find((o) => o.id === selectedOption)?.color ?? '#1F6F8B'}>
                {routeOptions.find((o) => o.id === selectedOption)?.badge ?? '—'}
              </span>
            {/if}
          </div>
        </li>
      {:else}
        <li class="note-step" style="--c:var(--muted); padding-inline-start: 34px; font-size: 0.8rem; color: var(--muted);">
          <span>No active route — steps will appear once a transport plan is loaded.</span>
        </li>
      {/each}
    </ol>

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
  .suggestions { position: absolute; inset-inline-start: 0; inset-block-start: 100%; z-index: 10; }
  .suggestions { max-height: 240px; overflow: auto; }
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
    width: 40px; height: 40px; border: 1px solid var(--rule); border-radius: 50%; background: #fff; cursor: pointer;
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
  .steps { display: grid; gap: 10px; }
  .steps li { display: grid; gap: 2px; }
  .milestone { position: relative; }
  .milestone-badge { justify-self: end; padding: 3px 10px; border-radius: 999px; color: #fff; font-size: 0.78rem; font-weight: 700; }

  /* LED board */
  .board {
    position: relative; display: grid; grid-template-columns: auto 1fr auto;
    align-items: center; gap: 14px; padding: 16px 18px; border-radius: 14px;
    background: #0a0a0a; color: var(--amber); text-shadow: 0 0 10px rgb(244 180 0 / 0.45);
  }
  .board::after {
    content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
    background: radial-gradient(circle, #0a0a0a 28%, transparent 31%) 0 0 / 3px 3px;
  }
  .board .badge { min-width: 52px; padding: 6px 10px; border-radius: 8px; text-align: center; position: relative; z-index: 1; color: #fff; font-weight: 700; text-shadow: none; }
  .dest p { margin: 0; }
  .fr { font-size: 1.35rem; font-weight: 700; line-height: 1.2; }
  .ar { font-size: 1.5rem; font-weight: 600; line-height: 1.3; }
  .eta { margin: 0; text-align: end; font-size: 0.9rem; position: relative; z-index: 1; }
  .eta strong { display: block; font-size: 2rem; line-height: 1; font-variant-numeric: tabular-nums; }

  .options { display: flex; gap: 8px; }
  .options button {
    flex: 1; display: grid; gap: 2px; justify-items: start; padding: 10px 12px; text-align: start;
    border: 1.5px solid var(--rule); border-radius: 12px; background: #fff;
  }
  .options button.on { border-color: var(--ink); box-shadow: 0 0 0 1px var(--ink); }
  .times { color: var(--muted); font-size: 0.85rem; font-variant-numeric: tabular-nums; }
  .opt-id { color: var(--muted); font-size: 0.75rem; }
  .opt-fare { color: var(--sea); font-size: 0.75rem; font-weight: 700; }

  .identifier { display: block; font-size: 0.75rem; color: var(--muted); }
  .fare { color: var(--sea); font-weight: 700; }

  .step-main { display: flex; flex-direction: column; gap: 2px; }
  .step-id { font-size: 0.75rem; color: var(--muted); }
  .step-meta { display: flex; flex-direction: column; align-items: end; gap: 2px; text-align: end; }
  .stations { color: var(--ink); font-size: 0.72rem; }

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

  .step { margin-top: 8px; font-size: 0.82rem; color: var(--muted); }
</style>
