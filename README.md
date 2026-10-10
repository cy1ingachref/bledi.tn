# BLEDI.TN — Tunisia Public Transport Routing

A Tunisia public-transport routing web app with geo-pinned memories, favorites, location sharing, and PWA offline support.

## Architecture

| Layer       | Tech                                                        |
|-------------|-------------------------------------------------------------|
| Frontend    | SvelteKit + TypeScript + Vite + PWA (service worker)        |
| Map         | Leaflet + OpenStreetMap tiles                               |
| Backend     | Rust (axum + sqlx) — in development; Python FastAPI — legacy |
| Database    | PostgreSQL + PostGIS (earthdistance extension)              |
| Auth        | JWT (bcrypt password hashing)                               |
| CI/CD       | GitHub Actions (fmt, clippy, build, test, security scan)    |
| Containers  | Docker + docker-compose                                      |

## Features

### Transport routing (Python FastAPI backend — working)
- Multi-modal Dijkstra over the transit graph (bus, metro, tram, train, RFR, taxi, walk)
- 232 lines and 1,711 stations across Tunisia
- Real road/rail geometry, multi-objective routing (fastest, fewest transfers, least walking)
- OSRM (driving) + Nominatim (geocoding) proxy with TTL caching
- Endpoints: `/api/v1/stations`, `/api/v1/lines`, `/api/v1/route/transit`, `/api/v1/geocode`, `/api/v1/itinerary`

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

# Run migrations (requires PostgreSQL + PostGIS)
export DATABASE_URL=postgres://postgres:postgres@localhost:5432/bledi
cd rust/bledi-server && sqlx migrate run

# Build and run
cargo run --release
```

### Docker (full stack)

```bash
docker-compose up --build
```

This starts PostgreSQL + PostGIS, the Rust backend on port 3000, and the frontend on port 5173.

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
- `GET /api/v1/route/plan`
- `GET /api/v1/route/transit`
- `GET /api/v1/geocode`
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
- `GET /api/v1/memories/nearby` (auth)
- `GET /api/v1/memories/{id}` (auth)
- `PUT /api/v1/memories/{id}` (auth)
- `DELETE /api/v1/memories/{id}` (auth)
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
- `DATABASE_URL` — PostgreSQL connection string (required)
- `RUST_LOG` — logging level (default `info`)

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
├── data/                      # Seed data (GTFS-like JSON)
├── tests/                     # Python backend tests
├── scripts/                   # Data processing scripts
├── Dockerfile                 # Multi-stage Rust build
├── docker-compose.yml         # Full stack orchestration
└── .github/workflows/ci.yml # CI pipeline
```

## CI pipeline

The GitHub Actions workflow runs on every push to `main`:

1. **Rust Build & Test** — `cargo fmt`, `cargo clippy`, `cargo build --release`, `cargo test`
2. **Frontend Build & Test** — `npm ci`, `npx tsc --noEmit`, `npm run build`
3. **Security Scan** — Semgrep, Gitleaks, Trivy

## Data sources and licensing status

Most of the routing data is derived from **Tunismapper**. The terms of that source have not been verified for redistribution. For that reason this repository does **not** yet claim a license for the dataset.

See `docs/provenance.md` for the full audit:
- Lines: 227 tunismapper + 4 transtu PDF + 1 tunismapper URL
- Stations: 1,315 tunismapper + 266 official-public (by mode) + 130 unknown
- The `/api/v1/itinerary` Tunismapper proxy is disabled by default

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
| Python FastAPI backend | Working | Running, tested, all endpoints functional |
| Rust axum backend | CI green | Compiles, clippy clean, migrations pass |
| SvelteKit frontend | Working | Builds, PWA service worker generated |
| Docker | Configured | docker-compose.yml with full stack |
| Deployment | Not deployed | No live server yet |

## TODO / known issues

- Media upload: memories accept a URL but there is no actual file upload to S3/R2/MinIO yet
- Google OAuth: only email/password auth exists
- Integration testing: no end-to-end tests between frontend and Rust backend
- i18n: no Arabic/French/English translation yet
- Deployment: nothing deployed to any server
- Rust backend: not yet connected to the frontend (frontend still calls Python backend)
