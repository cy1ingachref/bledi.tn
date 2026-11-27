# Data schemas consumed by the services

Derived by reading the source (not guessed). WP5 of the open-data cutover uses
these exact shapes to build the `open` profile under `data/open/`.

## Rust routing service (`services/routing`)

`Graph::load(data_dir)` (`src/graph.rs`) looks for, in order:
1. `transport_map_corrected.json`
2. `seed_all_tunisia_routes.CLEANED.corrected.json`

It parses either with `MapFile` (serde defaults, so all fields optional):

```text
MapFile {
  by_mode?: { <mode>: ModeBlock, ... },   // preferred form
  stations?: [RawStation, ...],           // flat fallback form
  lines?:    [RawLine, ...],              // flat fallback form
}
ModeBlock { stations?: [RawStation], lines?: [RawLine] }
RawStation { id: String, name?: String, lat?: f64, lon?: f64, mode?: String }
RawLine    { id: String, number?: String, name?: String, mode?: String, stations?: [String] }
```

Notes:
- Stations without numeric `lat`/`lon` are skipped. Missing `name` → `id`;
  missing `mode` → `"bus"`. Duplicate ids keep the first station.
- Lines are deduplicated by `id`; missing fields default to empty string / bus.
- Edges are built from consecutive `stations` pairs (haversine distance,
  per-mode speed, marginal fare) plus 900 m walk edges between nearby stations.
- The first file that yields at least one station wins; `Graph.source` records
  its filename and is returned by `/health` as `data_source`.

`src/main.rs` reads `BLEDI_DATA_DIR` (build ENV defaults to `/app/data`), binds
`PORT` (default 8081), and exposes `/health`, `/route` (GET+POST), `/lines`.
`/health` returns `{status, stations, lines, edges, io_backend, data_source}`.

## Python transit service (`services/transit`)

`SeedFileNetwork.load()` (`adapters/seed_files.py`) reads `SEED_FILE` from
`BLEDI_DATA_DIR`:

- `seed_all_tunisia_routes.tagged.json` — `{metadata, stations[], lines[]}`.
- optional `louage_corridors.json` (merged into stations/lines),
- optional louage/taxi hub seed.

`create_app()` also requires `GraphPathGeometry.load(road_graph, rail_graph)`
from `ROAD_GRAPH_PATH` / `RAIL_GRAPH_PATH` (default `BLEDI_DATA_DIR/road_graph.npz`
and `rail_graph.npz`), plus `NOMINATIM_CONTACT` in production. `/api/v1/health`
is the healthcheck path.

Station records consumed by the catalog use `id`, `name`, `name_ar`, `lat`,
`lon`, `mode`, `operator`, `lines_served`; lines use `id`, `name`, `number`,
`mode`, `operator`, and an ordered stop list (`stations` in the legacy seed).

## Docker build inputs

- `services/transit/Dockerfile`: `COPY data/seed_all_tunisia_routes.tagged.json`
  into `/app/data`; `ENV BLEDI_DATA_DIR=/app/data`.
- `services/routing/Dockerfile`: `COPY data/transport_map_corrected.json`
  into `/app/data`; `ENV BLEDI_DATA_DIR=/app/data PORT=8081 RUST_LOG=info`.

## Implication for the `open` profile

To be loadable without changing service code, `data/open/` must mirror these
names/shapes:
- `seed_all_tunisia_routes.tagged.json` (flat `{stations, lines}` as above),
- `transport_map_corrected.json` (flat or `by_mode` as above),
- optionally `seed_all_tunisia_routes.CLEANED.corrected.json`,
- plus the same graph/fare files the Python service expects.

The profile switch only changes which directory is mounted as `BLEDI_DATA_DIR`;
it must not change the file names or schemas.

## Profile switch (WP5)

`docker-compose.yml` passes `DATA_PROFILE` (default `legacy`) to the services as
informational configuration. To actually run the `open` profile once its data
exists:

1. Fetch the export (`scripts/fetch_osm_export.py`, needs `OVERPASS_CONTACT`),
   rebuild the seed (`scripts/rebuild_seed_from_osm.py`) and generate the
   profile files (`scripts/open_pipeline.py --out-dir data/open`).
2. In `.env`, set `DATA_PROFILE=open` and add a compose override that mounts
   `./data/open` at the services' `BLEDI_DATA_DIR` (`/app/data`), or set
   `BLEDI_DATA_DIR` to a mounted `/app/open-data`.
3. Run `python scripts/check_provenance.py --profile open` — this gate is
   enforcing for `open` (zero `unknown-third-party` records) and informational
   for `legacy`.

The default remains `legacy` until the owner signs off on cutover (WP7). There
is no real export on disk at authoring time, so `data/open/` is not committed.
