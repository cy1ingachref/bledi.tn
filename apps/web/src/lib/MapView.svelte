<script>
  import { onMount } from 'svelte';
  let {
    path = [],
    rtl = false,
    stations = [],
    startLat = null,
    startLon = null,
    endLat = null,
    endLon = null,
    mapReady = false,
    zoomTo: onZoom = () => {},
  } = $props();

  let el, map, L, line, markers = [], stationMarkers = [];

  function haversine(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const toRad = (d) => (d * Math.PI) / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.asin(Math.sqrt(a));
  }

  function filterStations(stations, startLat, startLon, endLat, endLon, path) {
    if (!stations || !stations.length) return [];
    const buffer = 500; // meters
    if ((startLat == null || startLon == null) && (endLat == null || endLon == null)) {
      return [];
    }
    const pts = [];
    if (startLat != null && startLon != null) pts.push({ lat: startLat, lon: startLon });
    if (endLat != null && endLon != null) pts.push({ lat: endLat, lon: endLon });
    if (path && path.length >= 2) {
      for (const p of path) {
        if (Array.isArray(p) && p.length >= 2) pts.push({ lat: p[0], lon: p[1] });
      }
    }
    if (pts.length === 0) return [];
    const result = [];
    const seen = new Set();
    for (const s of stations) {
      if (seen.has(s.id)) continue;
      seen.add(s.id);
      let near = false;
      for (const p of pts) {
        if (haversine(s.lat, s.lon, p.lat, p.lon) <= buffer) {
          near = true;
          break;
        }
      }
      if (near) result.push(s);
    }
    return result;
  }

  // mode -> colour. Declared BEFORE draw() so it is never read in its
  // temporal-dead-zone (a const used above its declaration throws
  // ReferenceError and silently aborts the whole station loop).
  const modeColors = {
    bus: '#F4B400',
    louage: '#D7261E',
    metro: '#1F6F8B',
    rail: '#9B59B6',
    train: '#7B2D8E',
    taxi: '#D7261E',
    unknown: '#586972',
    tram: '#1F6F8B',
    louaj: '#D7261E',
  };

  function dot(color, size = 14, extraClass = '') {
    const cls = `map-marker-dot ${extraClass}`.trim();
    return L.divIcon({
      className: cls,
      iconSize: [size, size],
      html: `<span style="display:block;width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 1px 4px #0006"></span>`,
    });
  }

  $effect(() => {
    if (mapReady && map) {
      draw();
    }
  });

  function draw() {
    if (!map || !L) return;
    line?.remove();
    markers.forEach((m) => m.remove());
    stationMarkers.forEach((m) => m.remove());
    stationMarkers = [];
    markers = [];

    if (path.length >= 2) {
      // SVG renderer so CSS keyframes can animate stroke-dashoffset on the path
      line = L.polyline(path, {
        color: '#1F6F8B',
        weight: 5,
        opacity: 0.9,
        className: 'animated-route',
        renderer: L.svg({ padding: 0.5 }),
      }).addTo(map);
      markers = [
        L.marker(path[0], { icon: dot('#1F6F8B', 18, 'start-end-marker start-marker') }),
        L.marker(path.at(-1), { icon: dot('#D7261E', 18, 'start-end-marker end-marker') })
      ];
      markers.forEach((m) => m.addTo(map));
    }

    const start = (startLat != null && startLon != null)
      ? L.marker([startLat, startLon], { icon: dot('#1F6F8B', 18, 'start-end-marker start-marker'), zIndexOffset: 1000 }).addTo(map)
      : null;
    if (start) {
      const nm = stations.find((s) => s.lat === startLat && s.lon === startLon)?.name ?? 'Start';
      start.bindTooltip(`From: ${nm}`, { direction: 'top', offset: [0, -8] });
      markers.push(start);
    }
    const end = (endLat != null && endLon != null)
      ? L.marker([endLat, endLon], { icon: dot('#D7261E', 18, 'start-end-marker end-marker'), zIndexOffset: 1000 }).addTo(map)
      : null;
    if (end) {
      const nm = stations.find((s) => s.lat === endLat && s.lon === endLon)?.name ?? 'End';
      end.bindTooltip(`To: ${nm}`, { direction: 'top', offset: [0, -8] });
      markers.push(end);
    }

    if (start && end) {
      const sw = L.latLngBounds([[startLat, startLon], [endLat, endLon]]);
      const pad = innerWidth >= 800 ? 320 : 160;
      map.fitBounds(sw, { paddingTopLeft: [pad, 40], paddingBottomRight: [pad, pad + 60] });
      start.flyTo([startLat, startLon]);
      end.flyTo([endLat, endLon]);
    }

    const filteredStations = filterStations(stations, startLat, startLon, endLat, endLon, path);
    for (const s of filteredStations) {
      const color = modeColors[s.mode] || '#999';
      const m = L.marker([s.lat, s.lon], { icon: dot(color, 10, 'station-marker-pop'), keyboard: false }).addTo(map);
      m.bindTooltip(s.name, { direction: 'top', offset: [0, -8] });
      stationMarkers.push(m);
    }
  }

  onMount(() => {
    (async () => {
      L = (await import('leaflet')).default;
      await import('leaflet/dist/leaflet.css');
      map = L.map(el, { zoomControl: false, preferCanvas: true }).setView([36.84, 10.24], 12);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap', maxZoom: 19
      }).addTo(map);
      L.control.zoom({ position: rtl ? 'topleft' : 'topright' }).addTo(map);
      draw();
    })();
    return () => map?.remove();
  });

  const stationKey = $derived(`${stations ? stations.length : 0}`);
  $effect(() => {
    stationKey;
    if (stations && stations.length && map && L) draw();
  });
</script>

<div bind:this={el} class="map" role="region" aria-label="Map"></div>

<style>
  .map { position: absolute; inset: 0; }

  /* Route line draw animation (SVG path only) */
  .animated-route {
    stroke-dasharray: 1200;
    stroke-dashoffset: 1200;
    animation: drawLine 1.2s ease-out forwards;
  }
  @keyframes drawLine {
    from { stroke-dashoffset: 1200; }
    to { stroke-dashoffset: 0; }
  }

  /* Station marker pop-in */
  .station-marker-pop {
    animation: popIn 0.35s ease-out both;
  }
  @keyframes popIn {
    from { opacity: 0; transform: scale(0); }
    to { opacity: 1; transform: scale(1); }
  }

  /* Start / end marker special highlight */
  .start-end-marker {
    animation: pulseGlow 1.6s ease-in-out infinite;
  }
  @keyframes pulseGlow {
    0%, 100% { filter: drop-shadow(0 0 4px rgba(31, 111, 139, 0.5)); }
    50% { filter: drop-shadow(0 0 14px rgba(31, 111, 139, 0.9)); }
  }

  /* End marker gets a warm red glow variation */
  .end-marker {
    animation: pulseGlowRed 1.6s ease-in-out infinite;
  }
  @keyframes pulseGlowRed {
    0%, 100% { filter: drop-shadow(0 0 4px rgba(215, 38, 30, 0.5)); }
    50% { filter: drop-shadow(0 0 14px rgba(215, 38, 30, 0.9)); }
  }
</style>
