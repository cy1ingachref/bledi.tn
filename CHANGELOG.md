# Changelog

## Unreleased — open-data cutover WP5 (open profile, side by side)

### Added
- `docs/data-schemas.md`: exact file names/shapes read by the Rust and Python
  services, derived from `graph.rs`, `main.rs`, `seed_files.py` and the Dockerfiles.
- `scripts/open_pipeline.py`: converts `seed_open_source.json` into the mirrored
  `data/open/` files without switching any service.
- `scripts/check_provenance.py`: enforcing for `open` (zero `unknown-third-party`),
  informational for `legacy`; wired into `data-pipeline.yml`.
- `DATA_PROFILE` env (default `legacy`) passed to both services in compose.
- 6 tests in `services/transit/tests/test_open_pipeline.py`.

## Unreleased — open-data cutover WP4 (per-mode defaults + estimated flag)

### Added
- `services/transit/src/bledi_transit/domain/mode_defaults.py`: declarative
  per-mode headway/speed/fare defaults, every value marked `estimated: true`
  with its source; official-public lines override via explicit step markers.
- Itinerary API responses now carry `estimated`, surfaced as a small badge with
  localized text (FR/AR/EN) on route cards in the React UI.
- 5 tests in `services/transit/tests/test_mode_defaults.py`.

## Unreleased — open-data cutover WP3 (coverage report)

### Added
- `scripts/open_coverage_report.py`: reproducible legacy-vs-open station/line
  coverage report (configurable 150 m match, normalised names, same-mode
  station match, per-mode/governorate breakdowns, top-30 missing lines by stop
  proxy) writing `docs/reports/open-data-coverage.{md,json}`.
- 6 tests in `services/transit/tests/test_open_coverage_report.py`. The committed
  report was generated from a synthetic fixture and is explicitly marked as
  NOT a real coverage assessment (no Overpass export on disk).

## Unreleased — Overpass fetch hardening (open-data cutover STEP 1)

### Fixed
- `scripts/fetch_osm_export.py`: treat Overpass error/timeout/out-of-memory
  remarks as failures even on HTTP 200; require minimum stop-node/route-relation
  counts (50/10) before writing anything; narrow `node["railway"]` to station
  types; require `OVERPASS_CONTACT` for the User-Agent; one Retry-After-aware
  retry on 429/504 per endpoint; manifest written only on full success.
- Added 10 hardening tests in `services/transit/tests/test_osm_fetch_hardening.py`.

## Unreleased — open-data cutover WP2 (converter fixes + validator)

### Fixed / Added
- Rewrote `scripts/rebuild_seed_from_osm.py` per review findings 1–8: mode from
  standard OSM flags, stop_area duplicate merging with all OSM ids kept,
  complete `lines_served` via an index, route_master direction grouping,
  short-line dropping with counts, unnamed-stop flags, Tunisia bounds/type/duplicate
  sanity checks, and louage source metadata in the manifest.
- Added `scripts/verify_open_seed.py` (schema, unique ids, stop resolution,
  bounds, license allowlist `odbl`/`official-public`) and 15 new tests
  (8 converter + 7 validator) in `services/transit/tests/`.

## Unreleased — open-data cutover WP1 (reproducible fetch)

### Added
- `scripts/fetch_osm_export.py`: one-request Overpass fetch of Tunisia public
  transport by ISO code (with `route_master` and way recursion), retrying the
  Kumi and main endpoints, writing a gitignored export and a committed manifest
  (query, OSM base timestamp, element counts, SHA-256).
- `data/osm_overpass/manifest.json` template and `services/transit/tests/test_osm_fetch.py`
  (5 tests). No raw export is committed.

## Unreleased — cleanup M4 (retire legacy SvelteKit app)

### Changed
- `scripts/build_transport_catalog.py` now writes `data/derived/transport_catalog.json`
  (repo-relative `BASE`); moved the committed catalog there and repointed the
  CI type-checked `scripts/final-verify.py` at it.
- Archived the 17 one-off `data.ts`/repair scripts into `archive/scripts-oneoff/`.
- Moved `apps/web` to `archive/web-sveltekit/`; removed its `.gitignore` entries
  and updated `docs/architecture.md` and `docs/media-upload-design.md`.

## Unreleased — cleanup M2 (data audit and archive)

### Changed
- Added `scripts/audit_data_usage.py` (read-only reference report for every
  file under `data/`) and pasted its output in the PR.
- Deleted `data/stations_stops_bus_numbers.json` (12.9 MB, zero references).
- Archived the two obsolete seed snapshots into `archive/data-pipeline-history/`
  with a README, and documented the canonical seed chain in `data/SOURCES.md`.

## Unreleased — cleanup M6 (hard-coded paths)

### Changed
- Replaced hard-coded absolute Windows user paths in kept scripts and tools
  with repo-relative `Path(__file__).resolve().parents[1|2]` and
  `Path.home()/Downloads/...`; updated historical doc references too.
- Archived 17 one-off repair scripts (no CI references) into
  `archive/scripts-oneoff/` with a README.
- Added `scripts/check_no_local_paths.py` and wired it into `data-pipeline.yml`
  so a local path cannot return in tracked code/docs.

## Unreleased — cleanup M5 (root clutter)

### Changed
- Moved the historical phase/design reports from the repo root into
  `docs/reports/` (raw JSON snapshots into `docs/reports/data/`) and linked
  them from `docs/roadmap.md`. Updated `scripts/phase3a_trace.py` and
  `scripts/phase3c_verify.py` to write to the new locations.

## Unreleased — fixes handoff PR 4 (M1)

### Fixed
- Replaced wildcard `https:` in CSP `img-src`/`connect-src` with the exact
  Maptoolkit/Mapterhorn/Fonts hosts used by the dark style.
- Added `e2e/csp-smoke.mjs` and documented the allowlist in
  `docs/architecture.md`. `unsafe-inline` in `style-src` was tested and kept:
  the route UI uses inline style attributes.
- Extended browser verification with `e2e/csp-browser.mjs`: drives the map
  (load, zoom in/out, pan to Tunis/Sfax/Djerba), language switching FR/AR/EN,
  and a route draw/clear, asserting zero `securitypolicyviolation` events and
  console CSP errors. Wired into the opt-in `e2e` workflow as `csp-browser`.

## Unreleased — fixes handoff PR 5 (transit trust proxy)

### Fixed
- `docker-compose.yml`: `transit` now sets `TRUST_PROXY_HEADERS=1`, so its
  rate-limit backstop keys on the gateway-overwritten `X-Forwarded-For`
  instead of pooling every user behind the gateway container IP.
- `install_rate_limit` logs the effective `trust_proxy` value once at startup
  (`rate limit: trust_proxy=...`) so a misconfiguration is visible in logs.
- Docs clarified that `TRUST_PROXY_HEADERS` is not accounts-only.
- Added `services/transit/tests/test_compose_config.py` and expanded
  `test_rate_limit.py` with proxy trust, health-exemption and idle-key cases.
- Added `pyyaml` to the transit dev extras and regenerated the hashed dev
  lockfile so the compose-config guard also runs in CI.

## Unreleased — fixes handoff PR 3 (H4)

### Fixed
- Nominatim adapter: contact from `NOMINATIM_CONTACT` (fail startup in
  production when unset), lock-protected 1 s throttle, 5 s configurable
  timeout, LRU+TTL cache, and 30 s negative caching of failures.
- Removed unused `geocodePlaces()` from the React app so address search can
  never run as-you-type against the public Nominatim instance.
- Added `services/transit/tests/test_nominatim.py` (6 tests).

## Unreleased — fixes handoff PR 2 (H1)

### Fixed
- Transit rate limiter: per-IP buckets use `deque` with idle-key deletion
  instead of O(clients) list rebuilds; `X-Forwarded-For` is trusted only when
  `TRUST_PROXY_HEADERS=1`, taking the gateway-overwritten first entry.
- Health endpoints are exempt from both gateway and service rate limits.
- Gateway (`nginx.conf`) now rate-limits `/api/` at 10 r/s with burst 20,
  keyed on the real client IP, returning 429.
- Added `services/transit/tests/test_rate_limit.py` (5 tests).

## Unreleased — fixes handoff PR 1 (H2/L1/L2)

### Fixed
- `docker-compose.yml`: `transit-routing` is no longer published on host port
  8081 (`expose` only); `/routing/` still works through the web gateway.
- `services/transit/Dockerfile`: HEALTHCHECK now probes `/api/v1/health`,
  matching compose and the application.
- `docker-compose.yml`: removed `transit`'s `depends_on: db` (the transit
  service has no database dependency).
- Added `tests/test_infra_alignment.py` regression tests for all three.

## Unreleased — multi-objective routing, mode filters, station & line detail

Implements `ROUTING_FIX_INSTRUCTIONS.txt` (Parts A–F).

### Added

**`GET /api/v1/route/plan`** — the main routing endpoint. Multi-objective,
mode-filtered, returns up to 8 **distinct** labelled itineraries.

| Param | Default | Notes |
|---|---|---|
| `modes_include` | all | csv, e.g. `bus,metro,train` |
| `modes_exclude` | none | csv, e.g. `train,metro` — **hard filter** |
| `objective` | `fastest` | `fastest` \| `cheapest` \| `fewest_transfers` |
| `max_transfers` | unset | cap on line changes |
| `max_walk_m` | unset | caps access + egress walk |
| `max_itineraries` | `3` | 1..8, deduped |

**`GET /api/v1/stations/{id}`** — every line serving a stop, built from the
line→stops index (not the station's direction-oriented `lines_served`
fragments). 404 on unknown id.

**`GET /api/v1/lines/{id}`** — now returns ordered stops plus `geometry`,
`geometry_complete`, `geometry_segments[]` and `gaps[]`. A single straight line
across the country is never fabricated: missing track is reported per stop pair.

**Tests** — `tests/test_routing_objectives.py` (38 tests) and
`tests/test_api_endpoints.py` (23 tests), plus fixtures in `tests/fixtures/`.

### Changed

- **Mode taxonomy flattened.** `metro` was folded into `RAIL_MODES` with
  `train`, making "no metro, trains are fine" inexpressible. Modes are now flat
  and independently selectable: `bus`, `tram`, `metro`, `train`, `louaj`,
  `taxi`, `walk`. The legacy `FAMILIES` layer is retained for the older
  family-based endpoints.
- **Fare model documented** in `routing.FARE_DINARS` (base DT + DT/km), charged
  **once per boarded line**. It never returns `null`, so `cheapest` is always
  rankable.
- Steps now report the user-facing mode; speed/wait lookups still use the raw
  seed mode internally.

### Fixed

- **Fare was charged once per graph edge.** An itinerary expands one step per
  stop, so a 30-edge train ride was quoted at ~122 DT instead of ~7. A bus+train
  Tunis→Sousse trip now prices at 25.75 DT.
- **All three objectives returned the same single option.** Dedup keyed on
  every stop, so a journey never matched itself as "distinct". The planner now
  runs several *strategies* (unfiltered, high-transfer-penalty, bus-only,
  rail-only, metro-only, train-only) and merges distinct results — re-weighting
  one Dijkstra cannot produce a different journey when one option dominates
  every axis.
- **`modes_exclude` was ignored by the two unfiltered strategies**, so an
  excluded mode could still appear. Every strategy now derives from the user's
  filter.

### Known limitations

- Rail and long-distance bus **track geometry is still missing** from
  `data/route_geometry.json`; those legs report explicit `gaps[]` rather than a
  fabricated line. A metro+bus OD inside Tunis and Tunis→Sousse are the cases
  where multiple objectives are actually distinguishable — for purely
  intercity ODs, rail dominates and one option is genuinely correct.
- One 125 m walk in central Tunis still falls back to a two-point line: its
  endpoints land in two disconnected OSM foot fragments (pre-existing, from the
  road-routing work, unrelated to this ticket).
