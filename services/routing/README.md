# Bledi Routing Service (Phase 3B)

Fast Rust routing service: **axum 0.7 + tokio**, `tokio-uring` (io_uring) on
Linux with a `tokio::fs` fallback on Windows/macOS. Standalone crate — it does
**not** touch `services/accounts` or `services/transit`.

## What it does

Ports the Python oracle (`services/transit/.../routing/planner.py` + `router.py`)
to Rust:

- `src/graph.rs` — loads stations/lines from `data/transport_map_corrected.json`
  (fallback: `seed_all_tunisia_routes.CLEANED.corrected.json`), builds a simple
  grid index (no `rtree` dep), edges = consecutive stations per line in **both
  directions**, plus walk edges ≤900 m between nearby stations. Weights:
  `time = haversine / mode_speed`, `fare = base + per_km·km` (mirrors
  `domain/fares.py` + `domain/tunables.py` speeds).
- `src/router.rs` — Dijkstra/A* over `(station, line-arrived-on)` states
  (so a cheap arrival on a dead-end line can't shadow a better one), with
  boarding wait + transfer penalty. Objectives: `fastest`, `cheapest`
  (fare-weighted), `fewest_transfers`, and mode preference via
  `mode`/`modes`/`allowed_modes` filters.
- `src/io.rs` — `#[cfg(target_os = "linux")]` tokio-uring file reads;
  `tokio::fs` everywhere else. **io_uring is Linux-only**, so the crate is
  gated to compile on Windows via the fallback (documented limitation: on
  Windows file IO is not io_uring-backed, but routing behaviour is identical).
- `src/main.rs` — HTTP API.

Data note: graph is built from `transport_map_corrected.json` (379 lines:
bus 310, louage 30, train 29, metro 7, rail 3 per `data/tables/index.json`).
Phase 3A snapped tables (`data/tables/*.json`), if present later, are not
required — the map file already carries per-line station arrays.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | `{status, stations, lines, edges, io_backend, data_source}` |
| GET | `/route?from=&to=&objective=` | Route between stations/coordinates |
| POST | `/route` | Same as GET, JSON body |
| GET | `/lines` | All lines `{id, number, name, mode, stations}` |

`from`/`to` accept: a station id (`sousse_bab_jdid`), `"lat,lon"`, or the
`from_lat`/`from_lon`/`to_lat`/`to_lon` numeric params.
`objective` ∈ `fastest` (default), `cheapest`, `fewest_transfers`.
Mode preference: `?mode=train` or `?modes=bus,train` (GET) /
`"allowed_modes": ["train"]` (POST).

```bash
curl 'localhost:8081/route?from=sousse_bab_jdid&to=mahdia&objective=fastest'
curl -X POST localhost:8081/route -H 'content-type: application/json' \
  -d '{"from_lat":36.8,"from_lon":10.18,"to_lat":36.74,"to_lon":10.16,"objective":"cheapest"}'
```

## Run

```bash
cd services/routing
cargo check   # must pass on Windows too (io_uring is cfg-gated)
cargo run     # PORT=8081 (default), BLEDI_DATA_DIR=../../data (default auto-detect)
```

## Docker / k8s plan (not yet applied)

- `Dockerfile`: `rust:1-bookworm` builder → `cargo build --release` →
  `debian:bookworm-slim` runtime, copy binary + `data/*.json` (or mount a
  ConfigMap/PVC at `BLEDI_DATA_DIR`).
- k8s: `Deployment` (replicas 2, `PORT=8081`), `Service` port 8081,
  `livenessProbe`/`readinessProbe` on `GET /health`, HPA on CPU.
  Data files are baked into the image so pods start without a data dependency.
