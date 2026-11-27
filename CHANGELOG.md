# Changelog

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
