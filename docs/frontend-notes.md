# Frontend notes

## Canonical frontend: `frontend/index.html`

`index.html` is the canonical Leaflet UI. It talks to the FastAPI backend at
`/api/v1/*` and depends on a running server (no embedded data).

## Archived frontend: `frontend/bledi-map.html`

`bledi-map.html` is a **self-contained** single-file app (Leaflet + all 1,711
stations + 232 lines embedded as compact JS arrays, ~241 KB). It does **not**
require a backend for routing — the multi-modal Dijkstra engine and all data
are inline. It also does not call any external API except OSM tiles and
Nominatim geocoding.

### Features `bledi-map.html` has that `index.html` lacks

- Fully offline-routable (embedded dataset + client-side Dijkstra).
- Larger, richer results panel with ranked options, step-by-step walk/transit/
  taxi/transfer legs, indicative fares, and map drawing of the selected option
  along real stop sequences.
- Taxi as a direct road fallback with indicative metered fare.
- Quick-city dropdowns and a departure-time picker wired into the router.

### Features `index.html` has that `bledi-map.html` lacks

- Live backend integration: `/api/v1/stations`, `/api/v1/lines`,
  `/api/v1/route` (OSRM driving geometry), `/api/v1/geocode` (Nominatim via
  backend with server-side caching).
- Smaller initial load (no embedded 1,711-station dataset).
- Designed to be served by `uvicorn` alongside the API.

## Migration status

- `index.html` is the file the consolidated backend is wired to serve
  (`GET /` → `frontend/index.html`).
- `bledi-map.html` is kept as an archival/self-contained deliverable and is NOT
  served by the default `uvicorn` setup. It is not deleted because it is a
  genuinely different artifact (offline-first, embedded data) that may be
  useful for distribution or air-gapped demos.
- If you later want a single canonical frontend, pick one:
  - Keep `index.html` and drop `bledi-map.html`; or
  - Merge the backend-backed geocoding/OSRM bits from `index.html` into
    `bledi-map.html` and serve that as canonical.

## HTML/JS safety notes (applied to `index.html`)

- Data interpolated into the DOM goes through `textContent`, `createElement`,
  or an `esc()` helper — no `innerHTML` with user/API data.
- Geocoding is routed through `/api/v1/geocode` (backend) instead of a direct
  browser call to Nominatim, so the browser does not send a `User-Agent`
  header to a third party.
- The `/api/v1/itinerary` Tunismapper proxy is disabled by default; the
  frontend degrades gracefully when it returns 410.
