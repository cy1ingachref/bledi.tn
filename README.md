# BLEDI.TN — Tunisia Public Transport Routing

A Tunisia public-transport routing web app with geo-pinned memories, favorites, location sharing, and PWA offline support.

## Architecture

| Layer       | Tech                                                        |
|-------------|-------------------------------------------------------------|
| Frontend    | SvelteKit + TypeScript + Vite + PWA (service worker)        |
| Mobile app  | Flutter (`src/mobile/`) — legacy, superseded by the web UI  |
| Map         | Leaflet + OpenStreetMap tiles                               |
| Routing     | Python FastAPI (`src/backend/app/`) — owns all routing      |
| Social      | Rust axum + sqlx (`rust/`) — auth, memories, favorites, shares |
| Database    | PostgreSQL + PostGIS (earthdistance extension)              |
| Auth        | JWT (bcrypt password hashing)                               |
| CI/CD       | GitHub Actions (Rust + Python + frontend + security scan)   |
| Containers  | Docker + docker-compose                                      |

## Backend split (read this before changing either backend)

There are two backends, and the split is deliberate. Do not "consolidate" them
without reading this first.

| Concern | Owner | Why |
|---|---|---|
| Transit routing (Dijkstra, graphs, OSRM, geocoding) | **Python** (`src/backend/app/`) | Holds the real routing engine, the transit graph, and the geometry caches. This is the product. |
| Auth, memories, favorites, location shares | **Rust** (`rust/`) | Newer code, axum + sqlx. |

**Known gap:** the two backends do not yet share an auth scheme. The Rust
server issues JWTs that the Python server does not validate, and the Flutter /
web clients talk to the Python backend for routing. Before either backend is
deployed, one of these must happen:

1. **Shared JWT** — the Python side validates the same `JWT_SECRET` and claims
   the Rust side issues (or a gateway sits in front and terminates auth), or
2. **Port routing to Rust** — a large job, but the Python test suite and the
   seed fixtures make it feasible.

Until then, treat the Rust server as a standalone service. Its `stations` and
`lines` tables are **empty** (CI smoke-tests them as empty) — all station and
line data lives in the Python backend's seed files.

The Flutter app (`src/mobile/`) needs a single base URL and a single contract;
it currently points at the Python backend. Do not point it at both.

## Features

### Transport routing (Python FastAPI backend — working)
- Multi-modal Dijkstra over the transit graph (bus, metro, tram, train, RFR, taxi, louage, walk)
- **379 lines and 7,452 stations** across Tunisia (loaded from `data/seed_all_tunisia_routes.tagged.json`)
  - The untagged `data/seed_all_tunisia_routes.json` holds the original 232-line /
    1,711-station Tunismapper subset. The tagged file is the runtime dataset; the
    backend prefers it whenever it is present.
  - Of the 379 lines, 117 are `bc_bus_*` BizerteConnect lines that carry no stops
    and no coordinates (that source publishes no stops endpoint) and are therefore
    **not routable**. See `data/SOURCES.md`.
- Real road/rail geometry via the OSRM proxy and the locally built road graph
- Multi-objective routing (fastest, fewest transfers, least walking)
- OSRM (driving) + Nominatim (geocoding) proxy with TTL caching
- Endpoints: `/api/v1/stations`, `/api/v1/lines`, `/api/v1/route/transit`, `/api/v1/geocode`, `/api/v1/itinerary`

### Map layers (frontend — working)
- **Physical rail base layer** — every passenger rail and light-rail alignment in Tunisia, drawn under the per-route network in a dedicated Leaflet pane (`zIndex: 370`, `pointer-events: none`). Styled quieter than routes: mainlines in mode colour at 0.72 opacity, metro at 0.6.
- **Physical road base layer** — motorway, trunk and primary roads only, in a muted grey (`zIndex: 360`). Motorways carry the most weight (1.9 px), primary the least (1.1 px, 0.3 opacity). Secondary/territorial roads omitted as visual noise.
- Built by `tool/build_map_overlays.py` from official Overpass exports. Served as GeoJSON with coordinates converted from `[lon, lat]` to `[lat, lon]` so the client has one convention.
- A missing overlay returns HTTP 503 with the build command in the detail, not an empty layer — so the map never claims "Tunisia has no railways".

### Louage connections (frontend + backend — working)
- Each national louage station's destinations resolved against the station list, shown in the station inspector as focusable buttons that centre the map and open the destination's inspector.
- Unresolved destinations (names that match no station record) are listed in `data/louage_links.json` rather than dropped or guessed.

### Geo-pinned memories (Rust backend — in development)
- Capture photo/video and pin to a location
- Visibility controls: public / friends / private
- Radius-based unlock (configurable 50–1000m)
- Nearby memories discovery via PostGIS earthdistance

### Favorites (Rust backend — in development)
- Save stations, lines, and places
- User dashboard

### Location sharing (Rust backend — in development)
- Share live location with friends
- Expiry and accuracy support
- Nearby friends discovery

### Accounts (Rust backend — in development)
- Email/password registration and login
- JWT authentication (7-day expiry)
- Protected routes

### PWA / offline (frontend — working)
- Service worker with auto-update
- OSM tile caching (CacheFirst)
- Transit data caching (StaleWhileRevalidate)
- Installable on mobile and desktop

## Run it

### Python FastAPI backend (legacy, working)

```bash
# Install deps
python -m pip install -r requirements.txt

# Start the API
uvicorn src.backend.app.main:app --host 127.0.0.1 --port 8000

# Open the frontend
open http://localhost:8000
```

### Rust backend (in development)

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Required. The server REFUSES TO START without a >=32 byte JWT_SECRET.
export JWT_SECRET="$(openssl rand -hex 32)"

# Required. There is no default connection string.
export DATABASE_URL="postgres://USER:PASSWORD@localhost:5432/bledi"

# Run migrations (requires PostgreSQL + PostGIS)
cd rust/bledi-server && sqlx migrate run

# Build and run
cargo run --release
```

### Docker (full stack)

Docker Compose reads its credentials from the environment and has **no
defaults** — it fails fast rather than starting with a known password. Create a
`.env` next to `docker-compose.yml`:

```bash
# .env  — never commit this file
POSTGRES_USER=bledi
POSTGRES_PASSWORD=<a real password>
POSTGRES_DB=bledi
JWT_SECRET=<openssl rand -hex 32>
```

```bash
docker compose up --build
```

This starts PostgreSQL + PostGIS, the Rust backend on port 3000, and the
frontend on port 5173. Postgres is **not** published to the host — it is only
reachable from the compose network. The backend container runs as an
unprivileged user.

### Frontend (standalone)

```bash
cd frontend
npm install
npm run build
npm run preview
```

## API endpoints

### Python FastAPI (port 8000)
- `GET /api/v1/health`
- `GET /api/v1/stations`
- `GET /api/v1/stations/near`
- `GET /api/v1/stations/{id}`
- `GET /api/v1/lines`
- `GET /api/v1/lines/{id}`
- `GET /api/v1/network`
- `GET /api/v1/map/rail` — physical rail alignments (GeoJSON)
- `GET /api/v1/map/roads` — physical road alignments (GeoJSON)
- `GET /api/v1/map/overlays` — both in one response
- `GET /api/v1/louage/links` — resolved louage station connections
- `GET /api/v1/cities`
- `GET /api/v1/route/plan`
- `GET /api/v1/route/transit`
- `GET /api/v1/route/options`
- `GET /api/v1/route/modes`
- `GET /api/v1/geocode`
- `GET /api/v1/search`
- `GET /api/v1/itinerary` (Tunismapper proxy — disabled by default)

### Rust axum (port 3000)
- `GET /api/v1/health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/users/me`
- `GET /api/v1/stations`
- `GET /api/v1/stations/near`
- `GET /api/v1/stations/{id}`
- `GET /api/v1/lines`
- `GET /api/v1/lines/{id}`
- `GET /api/v1/memories` (auth)
- `POST /api/v1/memories` (auth)
- `GET /api/v1/memories/nearby` (auth — metadata only, no `media_url`)
- `GET /api/v1/memories/{id}` (auth — visibility enforced)
- `POST /api/v1/memories/{id}/unlock` (auth — position checked against `unlock_radius_m`, returns the media)
- `PUT /api/v1/memories/{id}` (auth)
- `DELETE /api/v1/memories/{id}` (auth)
- `GET /api/v1/friendships` (auth)
- `GET /api/v1/friendships/requests` (auth)
- `POST /api/v1/friendships/request` (auth)
- `POST /api/v1/friendships/accept` (auth)
- `DELETE /api/v1/friendships/{user_id}` (auth)
- `GET /api/v1/favorites` (auth)
- `POST /api/v1/favorites` (auth)
- `DELETE /api/v1/favorites/{id}` (auth)
- `GET /api/v1/location-shares` (auth)
- `POST /api/v1/location-shares` (auth)
- `GET /api/v1/location-shares/nearby` (auth)
- `PUT /api/v1/location-shares/{id}` (auth)
- `DELETE /api/v1/location-shares/{id}` (auth)

## Environment variables

### Python backend
- `OSRM_URL` — OSRM endpoint (default `http://localhost:5000/route/v1/driving`)
- `OSRM_TIMEOUT` — OSRM request timeout in seconds (default 10)
- `ALLOWED_ORIGINS` — comma-separated CORS origins (default localhost only)
- `ENABLE_TUNISMAPPER_PROXY` — set to `1`/`true`/`yes` to re-enable the Tunismapper itinerary proxy

### Rust backend
- `DATABASE_URL` — PostgreSQL connection string (**required**, no default)
- `JWT_SECRET` — HMAC secret for signing tokens (**required**, >= 32 bytes, no
  default; the server refuses to start without it)
- `ALLOWED_ORIGINS` — comma-separated CORS origins (default localhost only)
- `RUST_LOG` — logging level (default `info`)

### Data-build tools
These override the `~/Downloads/...` defaults used by the data pipeline scripts.
See `data/SOURCES.md` for what each one feeds.

- `BLEDI_TUNISIA_TRANSPORT` — consolidated raw-resource folder
- `BLEDI_TRANSPORT_DUMP` — operator export dump
- `BLEDI_OPERATOR_EXPORTS` — per-operator exports folder
- `BLEDI_LOUAGE_CSV` — louage network CSV
- `BLEDI_ROADS_GPKG` — HotOSM roads GeoPackage (road graph + geometry)
- `BLEDI_RAILS_GEOJSON` — OSM rail export (rail graph)
- `BLEDI_MAPS_DIR`, `BLEDI_BIZERTE_WORKBOOK` — legacy Flutter import tooling

## Project structure

```
bledi.tn/
├── src/backend/app/          # Python FastAPI backend (legacy, working)
│   ├── main.py                #   API entry point
│   ├── routing.py             #   Dijkstra router
│   ├── road_routing.py        #   OSRM road geometry
│   └── rail_geometry.py       #   OSM rail geometry
├── rust/                      # Rust backend (in development, CI green)
│   ├── Cargo.toml             #   Workspace manifest
│   ├── bledi-core/            #   Shared types and models
│   └── bledi-server/          #   axum HTTP server
│       ├── src/
│       │   ├── main.rs        #   Server entry point
│       │   ├── auth.rs        #   JWT auth middleware
│       │   ├── handlers.rs    #   Route handlers
│       │   └── state.rs       #   App state (DB pool)
│       └── migrations/        #   SQL migrations
├── frontend/                  # SvelteKit frontend (working)
│   ├── src/
│   │   ├── app.html           #   HTML shell
│   │   ├── app.ts             #   PWA registration
│   │   ├── lib/
│   │   │   ├── router.ts      #   API client (Python backend)
│   │   │   ├── types.ts       #   TypeScript types
│   │   │   └── stores/
│   │   │       ├── auth.js    #   Auth store (JWT)
│   │   │       └── location.js #  Geolocation store
│   │   └── routes/
│   │       ├── +page.svelte   #   Home
│   │       ├── auth/          #   Login/register
│   │       ├── memories/      #   Geo-pinned memories
│   │       ├── favorites/     #   Saved places
│   │       └── share/         #   Location sharing
│   └── vite.config.ts         #   Vite + PWA config
├── src/mobile/                # Flutter mobile app (legacy, not main frontend)
├── data/                      # Seed data (GTFS-like JSON)
│   ├── seed_all_tunisia_routes.tagged.json  # runtime dataset
│   ├── map_rail.geojson      # physical rail alignments
│   ├── map_roads.geojson     # physical road alignments
│   ├── louage_links.json     # resolved louage connections
│   ├── station_corrections.json
│   └── station_lines.json
├── tests/                     # Python backend tests (151 tests)
├── tool/                      # Data pipeline & verification scripts
│   ├── build_map_overlays.py # builds rail/road GeoJSON from Overpass exports
│   ├── build_station_index.py # resolves louage links + station index
│   ├── apply_station_corrections.py
│   ├── resolve_station_coords.py
│   ├── resolve_tnrp.py       # TNRP registry lookups
│   ├── inspect_geometry_sources.py
│   ├── inspect_seed_lines.py
│   ├── verify_live_backend.py
│   └── ...                   # 30+ scripts total
├── scripts/                   # Data processing scripts
├── Dockerfile                 # Multi-stage Rust build
├── docker-compose.yml         # Full stack orchestration
└── .github/workflows/         # CI pipeline
```

## CI pipeline

Each workflow runs on pull requests and pushes to `main` that touch its paths:

- `backend.yml`: `cargo fmt`, `cargo clippy` and `cargo test` against PostGIS, then builds the Docker image and runs `rust/docker/smoke-test.sh` against it
- `python.yml`: `pytest tests/` with the hashed `requirements.lock.txt`
- `frontend.yml`: `npm audit`, `npm run check` (svelte-check), `npm run build`
- `security.yml`: Semgrep, Gitleaks and Trivy on every change, and weekly

## Data sources and licensing status

The routing data is derived from **more than one** third-party source and none of
their redistribution terms have been verified. This repository therefore does
**not** claim a license for the dataset. `LICENSE.TODO` records that, and
`docs/provenance.md` holds the full audit.

| Source | What came from it | Status |
|---|---|---|
| Tunismapper (tunismapper.com) | 227 lines, most stations | unknown-third-party |
| Transtu PDF (Tebourba.pdf) | 4 lines | official-public |
| Tunismapper URL (route_id=885) | 1 line | unknown-third-party |
| BizerteConnect API | 117 `bc_bus_*` lines + schedules, `data/bizerteconnect_network.json` | unknown-third-party, **not routable** |
| OpenStreetMap (ODbL) | road/rail graphs, geometry caches | ODbL — attribution required |
| Official public station lists | 266 stations | official-public |

Raw upstream scrapes (`scripts/tunismapper_all_routes_stops.json`,
`scripts/tunismapper_station_details.json`, `src/mobile/tool/osm_nodes_cache.json`)
are **not committed** — they are large, regenerable inputs to the committed
converters.

`data/rail_graph.npz` (641 KB) **is** committed, because the test suite
asserts that a long rail leg is never returned as a bare straight line, which
cannot hold without rail geometry. `data/road_graph.npz` (153 MB) is not —
build it with `src/backend/tool/build_road_graph.py`.

The `/api/v1/itinerary` Tunismapper proxy is disabled by default.

`LICENSE.TODO` records that the license is undecided. No MIT or other license is claimed for the dataset.

## Tests

### Python backend
```bash
python -m pytest tests/ -v
```

### Rust backend
```bash
cargo test -- --nocapture
```

### Frontend
```bash
npm run build
```

## Development status

| Component | Status | Notes |
|-----------|--------|-------|
| Python FastAPI backend | Working | Owns all routing. Running, tested (151 tests) |
| Rust axum backend | Working | Compiles, clippy clean, migrations pass. Auth/memories/favorites/shares only; `stations`/`lines` tables empty |
| SvelteKit frontend | Working | Builds, PWA service worker generated. Talks to the Python backend. Rail/road base layers + louage connections in the station inspector |
| Flutter app (`src/mobile/`) | Legacy | Superseded by the web UI |
| Docker | Configured | Compose requires a `.env`; no default credentials |
| Deployment | Not deployed | No live server yet |

## TODO / known issues

- **Two backends, no shared auth.** See "Backend split" above. This must be
  resolved before deployment.
- Media upload: memories accept a URL but there is no actual file upload to
  S3/R2/MinIO yet, and no upload endpoint. The `media_url` a client submits is
  validated as an http(s) URL, but until uploads are first-party the frontend
  should not render an arbitrary remote URL.
- 117 `bc_bus_*` BizerteConnect lines carry no stops and cannot be routed.
- Google OAuth: only email/password auth exists
- Integration testing: no end-to-end tests between frontend and Rust backend
- i18n: French, English, and Arabic translations for UI strings (station inspector, map controls, auth pages)
- Deployment: nothing deployed to any server
- Rust backend: not yet connected to the frontend (frontend still calls Python backend)
