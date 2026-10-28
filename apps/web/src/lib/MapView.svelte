<script>
  import { onMount } from 'svelte';
  import { modeColor } from '$lib/catalog.svelte.js';
  import { fetchMedia } from '$lib/api.js';

  let {
    path = [],
    rtl = false,
    stations = [],
    memories = [],
    mediaToken = null,
    photos = {},
    startLat = null,
    startLon = null,
    endLat = null,
    endLon = null,
    mapReady = false,
    overlayStations = [],
    onMapClick = null,
  } = $props();

  let el, map, L, line, zoom, markers = [], stationMarkers = [], memoryMarkers = [], overlayMarkers = [];

  // Photos the caller may see, keyed by their media URL. The page hands over the ones it
  // already fetched; the rest are fetched here with the token and kept, so the same
  // photo is fetched once and not once per redraw.
  let fetchedPhotos = {};
  let objectUrls = [];

  // Only internal constants and numbers reach this string, never user data.
  function dot(color, size = 14, extraClass = '') {
    const cls = `map-marker-dot ${extraClass}`.trim();
    return L.divIcon({
      className: cls,
      iconSize: [size, size],
      html: `<span style="display:block;width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 1px 4px #0006"></span>`,
    });
  }

  function louageColor(routeType) {
    if (routeType === 'long_distance') return '#D7261E'; // red stripe
    if (routeType === 'regional') return '#1F6F8B';     // blue stripe
    return '#E8B630';                                   // yellow stripe
  }

  // A memory title and photo come from other users, so the popup is built from DOM nodes
  // and never from an HTML string.
  function memoryPopup(memory) {
    const box = document.createElement('div');
    box.className = 'memory-popup';
    const safeMediaUrl = (u) => {
      if (typeof u !== 'string') return null;
      try {
        const p = new URL(u, location.href);
        return p.origin === location.origin || p.pathname.startsWith('/api/v1/media/') ? p.href : null;
      } catch (err) {
        console.warn('Invalid media url', err);
        return null;
      }
    };
    if (memory.media_url) {
      const img = document.createElement('img');
      img.alt = memory.title ?? 'Memory';
      img.loading = 'lazy';
      const known = photos?.[memory.media_url] ?? fetchedPhotos[memory.media_url];
      const src = known ?? safeMediaUrl(memory.media_url);
      if (src) {
        img.src = src;
      } else if (mediaToken) {
        fetchMedia(mediaToken, memory.media_url)
          .then((blob) => {
            const objectUrl = URL.createObjectURL(blob);
            fetchedPhotos[memory.media_url] = objectUrl;
            objectUrls.push(objectUrl);
            img.src = objectUrl;
          })
          .catch(() => {});
      }
      box.append(img);
    }
    const caption = document.createElement('p');
    caption.textContent = memory.title ?? '';
    box.append(caption);
    return box;
  }

  function fitTo(bounds) {
    const wide = innerWidth >= 800;
    map.fitBounds(bounds, {
      paddingTopLeft: [wide && !rtl ? 460 : 40, 40],
      paddingBottomRight: [
        wide && rtl ? 460 : 40,
        wide ? 40 : Math.round(innerHeight * 0.68) + 24
      ]
    });
  }

  function draw() {
    if (!map || !L) return;
    line?.remove();

    const existing = {};
    for (const m of stationMarkers) existing[m.stationId] = m;
    for (const m of memoryMarkers) existing[m.memoryId] = m;
    for (const m of overlayMarkers) existing[m.overlayId] = m;

    const nextStation = {};
    for (const s of stations) {
      if (s.lat == null || s.lon == null) continue;
      const key = `station:${s.id}`;
      let m = existing[key];
      if (!m) {
        m = L.marker([s.lat, s.lon], { icon: dot(modeColor(s.mode), 10, 'station-marker-pop station-marker') }).addTo(map);
        m.stationId = key;
      }
      m.setLatLng([s.lat, s.lon]);
      m.bindTooltip(s.name, { direction: 'top', offset: [0, -8] });
      nextStation[key] = m;
    }

    const nextMemory = {};
    for (const memory of memories) {
      if (memory.lat == null || memory.lon == null) continue;
      const key = `memory:${memory.id}`;
      let m = existing[key];
      if (!m) {
        m = L.marker([memory.lat, memory.lon], { icon: dot('#F4B400', 14, 'memory-marker') }).addTo(map);
        m.memoryId = key;
      }
      m.setLatLng([memory.lat, memory.lon]);
      m.setPopupContent(memoryPopup(memory));
      nextMemory[key] = m;
    }

    for (const m of stationMarkers) if (!nextStation[m.stationId]) m.remove();
    for (const m of memoryMarkers) if (!nextMemory[m.memoryId]) m.remove();
    stationMarkers = Object.values(nextStation);
    memoryMarkers = Object.values(nextMemory);

    const nextOverlay = {};
    for (const s of overlayStations) {
      if (s.lat == null || s.lon == null) continue;
      const key = `overlay:${s.id}`;
      let m = existing[key];
      if (!m) {
        m = L.marker([s.lat, s.lon], {
          icon: dot(louageColor(s.louage_route_type || 'local'), 12, 'station-marker-pop overlay-marker')
        }).addTo(map);
        m.overlayId = key;
      }
      m.setLatLng([s.lat, s.lon]);
      m.bindTooltip(s.name, { direction: 'top', offset: [0, -8] });
      nextOverlay[key] = m;
    }
    for (const m of overlayMarkers) if (!nextOverlay[m.overlayId]) m.remove();
    overlayMarkers = Object.values(nextOverlay);

    markers = markers.filter((m) => m != null && map.hasLayer(m));

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
      fitTo(sw);
      map?.flyTo([endLat, endLon]);
    } else if (start) {
      map?.flyTo([startLat, startLon], 14, { duration: 1 });
    } else if (end) {
      map?.flyTo([endLat, endLon], 14, { duration: 1 });
    } else if (line) {
      fitTo(line.getBounds());
    } else if (overlayMarkers.length) {
      const bounds = L.latLngBounds(overlayMarkers.map((m) => m.getLatLng()));
      fitTo(bounds);
    }
  }

  onMount(() => {
    (async () => {
      L = (await import('leaflet')).default;
      await import('leaflet/dist/leaflet.css');
      map = L.map(el, { zoomControl: false }).setView([36.84, 10.24], 12);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap', maxZoom: 19
      }).addTo(map);
      zoom = L.control.zoom({ position: rtl ? 'topleft' : 'topright' }).addTo(map);
      if (typeof onMapClick === 'function') {
        map.on('click', (e) => {
          const { lat, lng } = e.latlng;
          onMapClick({ lat, lon: lng });
        });
      }
      draw();
    })();
    return () => {
      objectUrls.forEach((u) => URL.revokeObjectURL(u));
      objectUrls = [];
      map?.remove();
    };
  });

  $effect(() => {
    if (mapReady && map) draw();
  });

  $effect(() => {
    zoom?.setPosition(rtl ? 'topleft' : 'topright');
    draw();
  });

  $effect(() => {
    if (stations && map && L) draw();
  });

  $effect(() => {
    if (overlayStations && map && L) draw();
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

  /* Memory markers stay still: they are places, not the route being drawn. */
  .memory-marker { filter: drop-shadow(0 0 6px rgba(244, 180, 0, 0.7)); }
  .overlay-marker { filter: drop-shadow(0 0 6px rgba(244, 180, 0, 0.85)); }

  :global(.memory-popup) { display: grid; gap: 6px; justify-items: center; }
  :global(.memory-popup img) {
    width: 160px; max-height: 160px; object-fit: cover; border-radius: 8px; display: block;
  }
  :global(.memory-popup p) { margin: 0; font-size: 0.85rem; text-align: center; }
</style>
