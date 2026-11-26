# BLEDI.TN, Tunisia public transport routing

A routing web app for Tunisian buses, metro, trains, louages and taxis, with an
accounts service for geo-pinned memories, favorites and location sharing.

## Layout

- `apps/web-react`: React + Vite frontend with MapLibre, served on :8080. Its nginx image is also the gateway (see `apps/web-react/Dockerfile`).
- `apps/mobile`: Flutter client.
- `services/transit`: Python FastAPI reference implementation. Routing, stations, lines, map layers, geocoding.
- `services/routing`: Rust axum routing engine (preferred path).
- `services/accounts`: Rust axum on PostgreSQL. Users, memories, favorites,
  friendships, location shares.
- `data`: the seed network and geometry the transit service loads. See
  [data/SOURCES.md](data/SOURCES.md).
- `scripts`, `tool`: the data pipeline and station audit tools.

[docs/architecture.md](docs/architecture.md) explains how the parts fit and
the rules each service follows.

## Run it

```bash
cp .env.example .env    # then fill each value with: openssl rand -hex 32
docker compose up --build
```

Open `http://localhost:8080`. Only the web gateway is published; PostgreSQL and
both services stay on the compose network.

[docs/quick-start.md](docs/quick-start.md) covers running one part on its own
and the routing API.

### Accounts

```bash
cd services/accounts
export DATABASE_URL=postgres://accounts:<password>@localhost:5432/accounts
export JWT_SECRET="$(openssl rand -hex 32)"
cargo run -p bledi-server
```

Migrations run on startup. Plain PostgreSQL 16 works; no extension is needed and
the role does not need to be a superuser. Environment:

- `DATABASE_URL`: required.
- `JWT_SECRET`: required, at least 32 bytes. The server refuses to start without it.
- `ALLOWED_ORIGINS`: comma separated CORS origins, local origins by default. An
  invalid entry stops startup.
- `TRUST_PROXY_HEADERS`: `1` to key rate limits on `X-Forwarded-For`. Set it only
  behind a proxy that overwrites the header, as the web gateway does.
- `RUST_LOG`: log level, `info` by default.

## API

Everything is under `/api/v1` on the gateway. The accounts service owns
`auth/`, `users/`, `memories`, `favorites`, `friendships` and `location-shares`.
Every other path goes to transit.

Transit:

- `GET /health`
- `GET /stations`, `/stations/near`, `/stations/{id}`, `/cities`, `/search`
- `GET /lines`, `/lines/{id}`, `/network`
- `GET /map/rail`, `/map/roads`, `/map/overlays`, `/louage/links`
- `GET /route/plan`, `/route/transit`, `/geocode`

Accounts (all but register and login need a bearer token):

- `POST /auth/register`, `POST /auth/login`, `GET /users/me`
- `GET|POST /memories`, `GET /memories/nearby`, `GET|PUT|DELETE /memories/{id}`,
  `POST /memories/{id}/unlock`
- `GET /friendships`, `GET /friendships/requests`, `POST /friendships/request`,
  `POST /friendships/accept`, `DELETE /friendships/{user_id}`
- `GET|POST /favorites`, `DELETE /favorites/{id}`
- `GET|POST /location-shares`, `GET /location-shares/nearby`,
  `PUT|DELETE /location-shares/{id}`

Errors from accounts are `{"error": "<message>", "code": "<snake_case>"}`, and
`{"error": "internal"}` for a 5xx.

## Checks

```bash
(cd services/transit && lint-imports && pytest)
(cd services/accounts && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test)
(cd apps/web && npm run lint && npm run check && npm test && npm run build)
```

The accounts tests need a `DATABASE_URL` to a throwaway database.

CI runs on pull requests, each workflow only when the PR touches its paths:

- `transit.yml`: import contracts and pytest.
- `accounts.yml`: fmt, clippy and tests against PostgreSQL 16.
- `web.yml`: audit, lint, svelte-check, vitest, build, and the image build.
- `security.yml`: Gitleaks, Semgrep and Trivy on every PR.
- `e2e.yml`: on PRs labelled `e2e`, the accounts image smoke test and the whole
  compose stack checked through the gateway.

## Data and licensing

The routing data comes from more than one third-party source, and none of their
redistribution terms have been verified. This repository therefore claims no
license for the dataset; `LICENSE.TODO` records that and
[docs/provenance.md](docs/provenance.md) holds the audit.

- Tunismapper: 227 lines and most stations, terms unknown.
- Transtu PDF (Tebourba): 4 lines, official public.
- BizerteConnect API: 117 `bc_bus_*` lines with schedules but no stops, so they
  are not routable. Terms unknown.
- OpenStreetMap (ODbL, attribution required): the road and rail graphs and the
  geometry caches.
- Official public station lists: 266 stations.

`data/rail_graph.npz` is committed, because the test suite asserts that a long
rail leg is never a bare straight line. `data/road_graph.npz` (153 MB) is not;
build it with `services/transit/tools/build_road_graph.py`.

The data pipeline reads its inputs from `~/Downloads/...` by default. These
override it; [data/SOURCES.md](data/SOURCES.md) says what each one feeds:

- `BLEDI_TUNISIA_TRANSPORT`: the consolidated raw resource folder.
- `BLEDI_TRANSPORT_DUMP`, `BLEDI_OPERATOR_EXPORTS`: operator exports.
- `BLEDI_LOUAGE_CSV`: the louage network CSV.
- `BLEDI_ROADS_GPKG`, `BLEDI_RAILS_GEOJSON`: the OSM road and rail extracts.

## Known gaps

- The transit service does not verify accounts tokens yet. See
  [docs/auth-scheme.md](docs/auth-scheme.md).
- The web app has no account screens yet; it only uses transit.
- Memories take a media URL; there is no upload endpoint. See
  [docs/media-upload-design.md](docs/media-upload-design.md).
- Nothing is deployed.
