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
  } = $props();

  let el, map, L, line, zoom, markers = [], stationMarkers = [], memoryMarkers = [];

  // Photos the caller may see, keyed by their media URL. The page hands over the ones it
  // already fetched; the rest are fetched here with the token and kept, so the same
  // photo is fetched once and not once per redraw.
  let fetchedPhotos = {};

  // Only internal constants and numbers reach this string, never user data.
  function dot(color, size = 14, extraClass = '') {
    const cls = `map-marker-dot ${extraClass}`.trim();
    return L.divIcon({
      className: cls,
      iconSize: [size, size],
      html: `<span style="display:block;width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 1px 4px #0006"></span>`,
    });
  }

  // A memory title and photo come from other users, so the popup is built from DOM nodes
  // and never from an HTML string.
  function memoryPopup(memory) {
    const box = document.createElement('div');
    box.className = 'memory-popup';
    if (memory.media_url) {
      const img = document.createElement('img');
      img.alt = memory.title ?? 'Memory';
      img.loading = 'lazy';
      const known = photos?.[memory.media_url] ?? fetchedPhotos[memory.media_url];
      if (known) {
        img.src = known;
      } else if (mediaToken) {
        // The media endpoint needs the caller's token, so an <img> cannot load it: the
        // bytes are fetched here and shown through an object URL.
        fetchMedia(mediaToken, memory.media_url)
          .then((blob) => {
            const objectUrl = URL.createObjectURL(blob);
            fetchedPhotos[memory.media_url] = objectUrl;
            img.src = objectUrl;
          })
          .catch(() => {
            // The photo stays out of the popup when the server refuses it.
          });
      } else {
        img.src = memory.media_url;
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
    markers.forEach((m) => m.remove());
    stationMarkers.forEach((m) => m.remove());
    memoryMarkers.forEach((m) => m.remove());
    stationMarkers = [];
    memoryMarkers = [];
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
      fitTo(sw);
      start.flyTo([startLat, startLon]);
      end.flyTo([endLat, endLon]);
    } else if (line) {
      fitTo(line.getBounds());
    }

    for (const s of stations) {
      if (s.lat == null || s.lon == null) continue;
      const m = L.marker([s.lat, s.lon], { icon: dot(modeColor(s.mode), 10, 'station-marker-pop'), keyboard: false }).addTo(map);
      m.bindTooltip(s.name, { direction: 'top', offset: [0, -8] });
      stationMarkers.push(m);
    }

    for (const memory of memories) {
      if (memory.lat == null || memory.lon == null) continue;
      const m = L.marker([memory.lat, memory.lon], { icon: dot('#F4B400', 14, 'memory-marker'), keyboard: false }).addTo(map);
      m.bindPopup(memoryPopup(memory));
      memoryMarkers.push(m);
    }
  }

  onMount(() => {
    (async () => {
      L = (await import('leaflet')).default;
      await import('leaflet/dist/leaflet.css');
      map = L.map(el, { zoomControl: false }).setView([36.84, 10.24], 12);
      L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '© OpenStreetMap, © CARTO', maxZoom: 19
      }).addTo(map);
      zoom = L.control.zoom({ position: rtl ? 'topleft' : 'topright' }).addTo(map);
      draw();
    })();
    return () => map?.remove();
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

  :global(.memory-popup) { display: grid; gap: 6px; justify-items: center; }
  :global(.memory-popup img) {
    width: 160px; max-height: 160px; object-fit: cover; border-radius: 8px; display: block;
  }
  :global(.memory-popup p) { margin: 0; font-size: 0.85rem; text-align: center; }
</style>
