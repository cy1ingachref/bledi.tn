# Rust routing port plan — bledi.tn transit backend

Inventory of the current Python routing backend, measured latency, the data-shape
contract, and a concrete Rust/axum + io_uring port plan.

Scope: read-only on the backend. No source was modified and the running server was
not restarted. All latency numbers below are real `curl` timings against the live
`http://127.0.0.1:8000` (or the startup log at `logs/backend-8000.log`).

---

## 0. Method and verification limits

**Read:** the full routing path (`main.py`, `adapters/seed_files.py`,
`adapters/graphs/{path_geometry,road_graph,rail_graph,search}.py`,
`adapters/http/{catalog,routing,deps,errors,schemas}.py`,
`application/routing/{planner,router,itinerary,graph,legs,transit}.py`,
`application/{catalog,network,ports}.py`, `domain/{geo,modes,tunables,fares,timetable,cities}.py`),
the graph builders (`tools/build_road_graph.py`, `build_rail_graph.py`,
`build_route_geometry.py`), `docs/architecture.md`, `docker-compose.yml`, and the
existing Rust workspace at `services/accounts`.

**Measured:** live HTTP timings (cold and warm), the startup log, and the exact
`.npy` headers inside both `.npz` files.

**Could not verify (flagged honestly):**

- No Python instrumentation was run in this session (executing scratch Python was
  declined). The Dijkstra-vs-geometry split in §2.3 is therefore inferred from code
  reading plus cold/warm endpoint timings, **not** from a profiler.
- Startup timing comes from the log of a previous process start; a fresh restart was
  out of scope.
- The walk-edge count is the code comment's "~12 700 pairs", not a measured count.
- The Rust speedup figures in §4.6 are estimates derived from the Python timings and
  the graph sizes; they are not benchmarked here.

---

## 1. Routing algorithm (behavioural spec)

### 1.1 Pipeline

```
GET /api/v1/route/plan   -> planner.route_plan (= plan()) -> Router.route() x N strategies
                          -> expand_path() -> _present()
GET /api/v1/route/transit-> Router.route() once (allowed_modes=None)
                          -> transit_itinerary() -> {best_fastest, legs, ...}
```

`Router.route_plan = plan` (assigned at class level in `router.py`).

### 1.2 Graph construction (startup, `Router.__init__`)

Nodes are **station ids** (strings). For every line, for every consecutive stop pair
`(a, b)`, two directed `Edge`s are added (`a→b` and `b→a`). Then walk edges and
louage/taxi transfer edges are added.

`line_edge()` — the cost of one ride edge:

```python
straight_m = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
entry = segments.get(f"{min(a_id, b_id)}|{max(a_id, b_id)}")
geom, real_m = [], straight_m
if entry and entry.get("geometry"):
    geom = oriented_geometry(entry, a_id, b_id)
    cand_m = polyline_length(geom)
    if cand_m >= 0.95 * straight_m:
        real_m = cand_m
    else:
        geom = []
if real_m <= 0:
    real_m = straight_m
return Edge(to_id=b_id, line=ln_id, mode=mode, wait_s=wait_s,
            distance_m=real_m, time_s=real_m / transit_speed_ms(mode),
            geometry=geom, straight_m=straight_m)
```

`add_walk_edges()` — grid-based, not O(n²):

```python
cell_deg = max(max_walk_edge_m, 100) / 111_000.0
span = 1 if max_walk_edge_m <= cell_deg * 2 else 2
...
if other <= sid: continue        # both cells see both stops
d = haversine_m(lat, lon, o_lat, o_lon)
if d > max_walk_edge_m: continue
# geometry from walk_geometry.json when >= 0.95 * d
```

Walk edges are bidirectional, `line="__walk__"`, `mode="walk"`, `wait_s=0`,
`time_s = wlen / WALK_SPEED_MS`.

`add_louage_taxi_transfers()` — **mutates the station dict** (adds `louage_*`
stations), then connects louage↔taxi stations within
`LOUAGE_TAXI_TRANSFER_RADIUS_M = 500.0` (walk-time cost) and same-name / <50 m
(zero cost), and connects still-isolated louage stations to the nearest main-seed
station within 500 m. Sentinel line `"__louage_taxi_transfer__"`, mode `"walk"`.

### 1.3 Cost model

Per edge, in the relaxation loop:

```python
is_walk = edge.mode == "walk"
arrived_line = None if is_walk else edge.line
segment_cost = edge.time_s
if not is_walk:
    if cur_line != edge.line:
        segment_cost += edge.wait_s          # boarding wait, once per line change
    if cur_line is not None and cur_line != edge.line:
        segment_cost += transfer_penalty     # not charged on the first boarding
```

`edge.time_s = distance_m / transit_speed_ms(mode)`, so the ride time follows the
real geometry when there is one — the cheapest path is also the physically fastest.

`wait_s` per line (computed once at startup):

```python
explicit_wait = ln.get("wait_s")
self.line_wait[ln_id] = (float(explicit_wait) if explicit_wait is not None
                         else min(expected_wait(ln.get("departures"), mode),
                                  BOARDING_WAIT_CAP))
```

`expected_wait` (`domain/timetable.py`): parse `HH:MM` → seconds; if fewer than 2
departures, return the per-mode default; sort; headways = consecutive diffs plus the
overnight gap (`86400 - last + first`) when `last - first > MAX_HEADWAY_SEC`;
**lower median** (`headways[(len-1)//2]`) × `WAIT_HEADWAY_FACTOR`.

### 1.4 Search (`Router.route`)

Multi-source Dijkstra over states `(station_id, line_arrived_on)`; `line=None` at the
start and after a walk.

Candidate sets:

```python
start_cap = MAX_START_WALK_METERS if max_walk_m is None else float(max_walk_m)
end_cap   = MAX_END_WALK_METERS   if max_walk_m is None else float(max_walk_m)
if allowed_modes is not None and (allowed_modes & BUS_MODES):
    start_cap = max(start_cap, MAX_START_WALK_METERS * 20)      # 40 000 m
start_candidates = self._nearest_stations(start_lat, start_lon, start_cap)
end_candidates   = self._nearest_stations(end_lat, end_lon, end_cap)
if allowed_modes is not None and (allowed_modes & BUS_MODES):
    if not any(has_bus_edge(sc['id']) for sc in start_candidates):
        start_cap = MAX_START_WALK_METERS * 500                  # 1 000 000 m
        start_candidates = self._nearest_stations(start_lat, start_lon, start_cap)
if not end_candidates and end_cap >= MAX_END_WALK_METERS:
    served = [s for s in self._nearest_stations(end_lat, end_lon, DROPOFF_SEARCH_METERS)
              if any(e.mode != "walk" for e in self.adj.get(s["id"], ()))]
    if served:
        end_candidates = served[:DROP_OFF_CANDIDATES]            # 1
```

`_nearest_stations` is a **full scan of all stations** (no spatial index) plus the
louage stations, sorted by haversine distance. This is called 1-3× per strategy.

Main loop (verbatim, abridged only where marked):

```python
while pq:
    cost, cur, _tie = heapq.heappop(pq)
    cur_line = _tie or None
    if cost >= best_cost: break          # early termination
    state = (cur, cur_line)
    if state in visited: continue
    visited.add(state)

    if cur in end_ids:
        ec = self.stations.get(cur)
        if ec and ec.get("lat") and ec.get("lon"):
            end_walk_m = haversine_m(ec["lat"], ec["lon"], end_lat, end_lon)
            if end_walk_m > MAX_END_WALK_METERS:
                end_walk_s = end_walk_m / TAXI_SPEED_MS
            else:
                end_walk_s = end_walk_m / WALK_SPEED_MS
            total_s = cost + end_walk_s
            if total_s < best_cost:
                path_stations, path_lines = self._reconstruct(prev, state)
                total_min, steps = expand_path(...)
                best = {"mode": "transit", "duration_min": total_min,
                        "steps": steps, "fare_dinars": None}
                best_cost = total_s

    for edge in self.adj.get(cur, ()):
        if (allowed_modes is not None and edge.mode != "walk"
                and edge.mode not in allowed_modes):
            continue
        is_walk = edge.mode == "walk"
        arrived_line = None if is_walk else edge.line
        segment_cost = edge.time_s
        if not is_walk:
            if cur_line != edge.line: segment_cost += edge.wait_s
            if cur_line is not None and cur_line != edge.line:
                segment_cost += transfer_penalty
        new_cost = cost + segment_cost
        new_state = (edge.to_id, arrived_line)
        if new_cost < dist.get(new_state, float("inf")):
            dist[new_state] = new_cost
            prev[new_state] = state
            heapq.heappush(pq, (new_cost, edge.to_id, arrived_line or ""))
```

Notes the port must preserve:

- The heap stores `""` for "no line"; `cur_line = _tie or None`. The tuple is
  `(cost, station_id_string, line_string)`, so **ties break on the station id
  string, then the line id string**.
- `if cost >= best_cost: break` is an early exit that depends on the order end
  candidates are settled.
- A direct walk answer is set first when `direct_m <= MAX_DIRECT_WALK_M` (1000) and
  walk is allowed; `best_cost = direct_walk_s`.
- A walk-only request returns immediately after that.
- After the search: a direct taxi alternative (only when transit exists) or a direct
  taxi answer, gated by `taxi_permitted`, `same_city_taxi` (`nearest_city`), and
  `TAXI_MIN_DISTANCE_M <= direct_m <= MAX_DIRECT_TAXI_M`. Taxi distance comes from
  the live road A* first, then `taxi_geometry.json`, then the straight line.
- `_reconstruct` has a cycle guard (`seen` set) — the recent fix.

### 1.5 Planner strategies (`plan()`)

`OBJECTIVES = ("fastest", "cheapest", "fewest_transfers")`; `max_itineraries`
clamped to `[1, 8]`, default 3. `user_allowed = resolve_allowed_modes(include,
exclude)` returns **raw seed modes** (excluding `train` also removes `rail`;
excluding `bus` also removes `rfr`), or `None` for no restriction.

```python
strategies = [
    ("fastest",          TRANSFER_PENALTY_SEC,          user_allowed),
    ("fewest_transfers", FEWEST_TRANSFERS_PENALTY_SEC,  user_allowed),
]
for name, subset in (
    ("bus_preferred",   {"bus", "rfr", "tram"}),
    ("rural_preferred", {"rural"}),
    ("rail_preferred",  {"train", "rail", "metro"}),
    ("metro_preferred", {"metro"}),
    ("train_only",      {"train", "rail"}),
    ("louage_only",     {"louage", "louaj"}),
    ("taxi_only",       {"taxi"}),
):
    inter = subset if user_allowed is None else (user_allowed & subset)
    if inter:
        strategies.append((name, TRANSFER_PENALTY_SEC, inter))
```

Each strategy calls `Router.route(...)`. Candidates are deduplicated by
`_itinerary_signature` = the ordered `(mode, line)` of ride legs (walks excluded;
falls back to `(type, "")` for pure walk/taxi). Sorting by objective:

```python
if objective == "cheapest":        sort(key=(fare_estimate, duration_s))
elif objective == "fewest_transfers": sort(key=(transfers, duration_s))
else:                              sort(key=(duration_s, transfers))
```

Then `_present()` builds the response. `include`/`exclude` is a **hard filter inside
edge expansion**, so an excluded mode can never appear in a leg.

### 1.6 Itinerary expansion (`expand_path`)

- Start walk: live foot A* → straight fallback; distance floor is the straight line.
- Middle walks: `resolve_walk_geometry` = live foot A* → cached polyline → foot
  bridge through nearby connected foot nodes → straight line.
- Rides: live rail A* for `train/metro/tram`; live road A* for
  `bus/louaj/taxi/rural` when no cached geometry. When live geometry is used the leg
  is **re-timed from the real distance** (`edge = None`).
- Adds a `transfer` step (`TRANSFER_PENALTY_SEC`) and the boarding wait to
  `duration_min`.
- Ends with an access/egress walk, or a **taxi hop** when
  `walk_m > MAX_END_WALK_METERS`, taxi is permitted, and the cities match.

### 1.7 Constants — `domain/tunables.py` (verbatim)

```python
WALK_SPEED_KMH = 4.5
WALK_SPEED_MS  = WALK_SPEED_KMH / 3.6

SPEED_BY_MODE = {
    "train": 60.0, "rail": 55.0, "metro": 30.0, "bus": 22.0,
    "rfr": 22.0, "tram": 22.0, "taxi": 45.0, "walk": WALK_SPEED_KMH,
}
TAXI_SPEED_KMH = SPEED_BY_MODE["taxi"]
TAXI_SPEED_MS  = TAXI_SPEED_KMH / 3.6

BOARDING_WAIT_CAP    = 20 * 60
WAIT_HEADWAY_FACTOR  = 0.5
DEFAULT_WAIT_BY_MODE = {"train": 600.0, "metro": 300.0, "bus": 600.0,
                        "rfr": 600.0, "taxi": 0.0, "walk": 0.0, "unknown": 600.0}
MAX_HEADWAY_SEC = 12 * 3600

TRANSFER_PENALTY_SEC          = 180.0
FEWEST_TRANSFERS_PENALTY_SEC  = 5400.0

MAX_START_WALK_METERS = 2000
MAX_END_WALK_METERS   = 2000
MAX_WALK_EDGE_METERS  = 900
DROPOFF_SEARCH_METERS = 100000
DROP_OFF_CANDIDATES   = 1
TAXI_MIN_DISTANCE_M   = 3000
MAX_DIRECT_TAXI_M     = 150_000
MAX_DIRECT_WALK_M     = 1000      # recently lowered from 6000
GEOMETRY_REQUIRED_M   = 300.0
```

`application/routing/graph.py`: `LOUAGE_TAXI_TRANSFER_RADIUS_M = 500.0`,
`LOUAGE_TAXI_SAME_LOCATION_M = 50.0`.

`domain/fares.py`:

```python
FARE_DINARS = {
    "bus": (0.500, 0.000), "tram": (0.500, 0.000), "metro": (0.600, 0.000),
    "train": (4.000, 0.090), "louaj": (1.000, 0.150), "taxi": (0.600, 0.520),
    "walk": (0.000, 0.000),
}
```

`domain/modes.py`: `BUS_MODES = {"bus","rfr","tram","rural"}`,
`RAIL_MODES = {"train","rail","metro"}`, `TAXI_MODES = {"taxi","louaj"}`;
`canonical_mode()` folds `rail`→`train`, `rfr`→`bus`, louage variants→`louaj`, and
unknown→`bus`.

---

## 2. Hot path and measured latency

### 2.1 Startup (from `logs/backend-8000.log`)

```
INFO:bledi.data:loaded seed: 7452 stations, 379 lines, 18 louage stops from seed_all_tunisia_routes.tagged.json
INFO:bledi.routing:road routing: graph road_graph.npz loaded in 2.9s (6308873 nodes, 13086148 edges; car 12827714, foot 13085238 directed edges)
INFO:bledi.routing:rail geometry: rail_graph.npz loaded in 0.0s (26179 nodes, 55352 edges)
INFO:     Application startup complete.
```

The road-graph load is 2.9 s of the ~3-4 s startup. Both `.npz` files are
Deflate-compressed (§3.2), so this is decompress + `astype` + `argsort` + CSR build.

### 2.2 Request latency (live server, `curl -w %{time_total}`)

"Cold" = first time this query's station/coordinate pairs are seen (memo miss).
"Warm" = repeat of the same query.

| query | cold | warm |
|---|---|---|
| short Tunis→Ariana (36.8003,10.1800 → 36.8622,10.1936) | **3.93 s** | 0.19 s |
| medium Tunis→Sousse (36.8003,10.1800 → 35.8256,10.6400) | **2.29 s** | 0.28 s |
| cross Tunis→Gabes (36.8003,10.1800 → 33.8815,10.0982) | **5.82 s** | 0.31 s |
| cross, `modes_include=train,rail` | 0.09 s * | — |
| medium, `modes_include=bus` (no itinerary found) | 0.20 s | 0.19 s |
| cross, `modes_include=taxi` | 0.03 s | 0.03 s |
| cross, fresh coords (36.7600,10.1300 → 33.8400,10.0600) | **3.18 s** | 0.55–0.62 s |
| plan cross, 10-call distribution | — | min 0.48 / med 0.52 / p90 0.57 / max 0.59 |
| plan medium, 10-call distribution | — | min 0.45 / med 0.48 / p90 0.53 / max 0.58 |
| `/route/transit` cross (1 strategy) | 0.32 s | med 0.10 s |
| `/stations/near` | — | 0.012 s |
| `/health` | — | 0.002 s |

\* contaminated: the same endpoints were searched by the preceding all-modes query, so
the rail geometry was already memoized.

Warm-up curve for one cross query (6 consecutive calls): `3.18, 0.61, 0.55, 0.59,
0.57, 0.62` s. Fresh coordinates that reuse already-seen station pairs: `0.90, 0.48,
0.50, 0.51` s.

### 2.3 Where the time goes

- **The Dijkstra is small.** 5 061 stop references across 379 lines → ~4 364
  undirected consecutive pairs → ~8 728 directed ride edges, plus ~12 700 undirected
  walk pairs (code comment) → ~25 000 directed walk edges, plus louage transfers. The
  state space `(station, line)` is ~10–15 k. Python completes one strategy in ~0.1 s
  (measured via `/route/transit` warm), so nine strategies ≈ 0.5 s — which is exactly
  the warm `/route/plan` number.
- **The cold path is dominated by live OSM A\*** (`paths.road` / `paths.rail`) for
  access/egress walks, taxi legs, and ride legs with no cached geometry. The memo
  caches (`_ROUTE_MEMO`, 512 entries; `_RAIL_MEMO`, 4096) are keyed by 5-dp
  coordinates, so a new query pays for its own access/egress walks every time; only
  station-pair geometry is reused across queries.
- **Consequence:** porting only the Dijkstra gives a ~10× win on the warm path
  (0.5 s → ~30–50 ms) but does nothing for the cold path. The cold path needs
  precomputed geometry or a ported A*.

---

## 3. Data-shape contract

### 3.1 Files

| file | size | schema | mmap? |
|---|---|---|---|
| `seed_all_tunisia_routes.tagged.json` | 5 006 072 B | `{metadata, stations[], lines[]}` | parse (JSON) |
| `route_geometry.json` | 648 055 B | `{metadata, segments:{"a\|b":{mode,source,geometry:[[lat,lon]]}}}` | parse |
| `walk_geometry.json` | 85 192 B | `{segments:{...}}` | parse |
| `taxi_geometry.json` | 393 171 B | `{segments:{"lat,lon\|lat,lon":{mode,source,geometry}}}` | parse |
| `road_graph.npz` | 152 840 072 B | 13 arrays (§3.2) | **no** — Deflate-compressed |
| `rail_graph.npz` | 641 716 B | 10 arrays (§3.2) | **no** — Deflate-compressed |
| `map_rail.geojson` | 2 850 354 B | FeatureCollection | parse / stream |
| `map_roads.geojson` | 27 936 092 B | FeatureCollection | parse / stream |
| `seed_routes_destination_tunis.json` | 20 340 B | `{metadata, stations[], routes[]}` | parse |
| `louage_links.json` | 12 909 B | `{links:[{from,to,from_name,to_name,destination_raw}]}` | parse |
| `louage_corridors.json` | **absent** | optional; `merge_corridors` is skipped | — |

Seed station:

```json
{"id":"sousse_bab_jdid","name":"Sousse Bab Jdid","name_en":"...","lat":35.823063,
 "lon":10.6415928,"source_stop_id":172,"mode":"train","operator":"SNCFT",
 "lines_served":[{"route_short_name":null,"route_color":"829EC0","direction":"..."}]}
```

Seed line:

```json
{"id":"train_1_sncft","number":"SNCFT","name":"Ligne SNCFT: ...","operator":"SNCFT",
 "mode":"train","type":"intercity","route_id":"1",
 "stations":["sousse_bab_jdid","sousse_mohamed_v", ...],
 "departures":["05:50","06:30", ...]}
```

`route_geometry.json` metadata: `{segments:1885, resolved:1776, missing:109,
simplify_tolerance_m:8.0}`. Segment keys are the **unordered** pair
`min(id)|max(id)`; the polyline is stored `min → max` and reversed on read
(`oriented_geometry`).

### 3.2 npz internals (exact, read from the `.npy` headers)

`road_graph.npz` — 6 308 873 nodes, 13 086 148 directed edges:

| key | dtype | shape | meaning |
|---|---|---|---|
| `lat`, `lon` | `<f8` | (6 308 873,) | node coordinates |
| `eu`, `ev` | `<i4` | (13 086 148,) | directed edge endpoints |
| `elen` | `<f8` | (13 086 148,) | metres along geometry |
| `eflags` | `\|u1` | (13 086 148,) | bit0 car, bit1 foot, bit2 bike |
| `espec` | `<u2` | (13 086 148, 3) | speed in m/s × 10 for (car, foot, bike) |
| `ename` | `<i4` | (13 086 148,) | index into `ename_raw` |
| `ename_raw` | object | (10 844, 3) | (name, name_fr, name_ar) |
| `quant` | `<i4` | (1,) | 6 (decimal places for node identity) |
| `comp_car`, `comp_foot`, `comp_bike` | `<i4` | (6 308 873,) | undirected component labels |

`rail_graph.npz` — 26 179 nodes, 55 352 directed edges:

| key | dtype | shape |
|---|---|---|
| `lat`, `lon` | `<f8` | (26 179,) |
| `eu`, `ev` | `<i4` | (55 352,) |
| `elen` | `<f8` | (55 352,) |
| `eflags` | `\|u1` | (55 352,) |
| `espec` | `<u2` | (55 352, 2) |
| `ename` | `<i4` | (55 352,) |
| `ename_raw` | object | (3, 2) |
| `comp` | `<i4` | (26 179,) |

The task brief listed `lat, lon, eu, ev, elen, ename, ename_raw, espec`; the files also
carry `eflags`, `quant` and the component labels, which the loader uses.

**Compression:** both are `np.savez_compressed`; every member is Deflate-compressed
(road: 530 598 376 B → 152 838 558 B, 71%; rail: 1 908 845 B → 641 716 B). They
**cannot be memory-mapped as-is**. A Rust port should either decompress once at
startup into a flat binary and mmap that, or add an uncompressed `.npy`/raw export to
the builders. The 2.9 s load is the decompress + `astype` + `argsort` + CSR cost; a
raw format should load in well under 0.5 s.

### 3.3 API compatibility contract

All `GET`, JSON. The Rust service must reproduce these paths, query parameters and
response bodies.

| path | params | response |
|---|---|---|
| `/api/v1/health` | — | `{status, version, service, seed_file, stations_count, lines_count}` |
| `/api/v1/stations` | — | GeoJSON FeatureCollection + `metadata{count,total,by_mode}` |
| `/api/v1/stations/near` | `lat, lon, limit=10` | `{near:[{id,name,lat,lon,dist_m,lines}], query}` |
| `/api/v1/stations/{id}` | — | `StationDetail` |
| `/api/v1/lines` | — | `{lines:[LineSummary], count}` |
| `/api/v1/lines/{id\|number}` | — | `LineDetail` |
| `/api/v1/route/plan` | `start_lat, start_lon, end_lat, end_lon, modes_include, modes_exclude, objective, max_transfers, max_walk_m, max_itineraries` | `{query, itineraries[], available_modes, message}` |
| `/api/v1/route/transit` | `start_lat, start_lon, end_lat, end_lon` | `{best_fastest, best_less_walk, alternatives, legs, source}` |
| `/api/v1/network` | `modes, bbox, simplify` | track segments |
| `/api/v1/map/rail`, `/api/v1/map/roads`, `/api/v1/map/overlays` | — | GeoJSON |
| `/api/v1/geocode` | `q, limit` | `{results, query, count}` |
| `/api/v1/search` | `q, limit, near_lat, near_lon` | `{results, ...}` |
| `/api/v1/cities` | — | `{cities:[...], count}` |
| `/api/v1/louage/links` | — | louage links |
| `/api/v1/encyclopedia` | — | guide |
| `/api/v1/stations/overpass-taxi-louage` | — | GeoJSON |

`/route/plan` itinerary fields: `id, label, rank_reason, mode, duration_min,
duration_s, transfers, fare_estimate_dinars, modes_used, legs, steps,
geometry_complete, gaps, searched_for`. `query` echoes `start, end, modes_include,
modes_exclude, objective, max_transfers, max_walk_m, max_itineraries`.

`/route/transit` `best_fastest` fields: `duration, duration_min, transfers,
has_walk_transfer, steps[], fare_dinars`; `steps[]` fields: `type, start, end,
color, stop_name, to_name, from_name, mode, line, geometry, has_geometry,
distance_m, time_seconds, from_id, to_id, straight_m, needs_geometry`.

Errors: `{"detail": ...}` with 400/404/503; unhandled → `{"error":"internal"}` (500).
Rate limit: 60 requests / 60 s per IP → 429 `{"error":"rate limit exceeded"}` +
`Retry-After: 60`.

---

## 4. Rust/axum + io_uring plan

### 4.1 Reality check on io_uring

- `tokio-uring` is **Linux-only**. This repo is developed on Windows (the accounts
  service builds with MSVC), so an io_uring path cannot be compiled or tested here.
  Windows has IoRing, a different API.
- The routing workload is **CPU-bound** (Dijkstra/A*), not I/O-bound. io_uring does
  not make Dijkstra faster. Its value here is (a) zero-copy loading of the graph
  files (mmap + `tokio-uring` reads) and (b) a faster HTTP server than epoll at high
  connection counts.
- **Recommendation:** build on `tokio` + `axum` (matching `services/accounts`), keep the
  graph in memory, and isolate io_uring file-loading behind a trait so a Windows dev
  build uses `tokio::fs` + `memmap2`. Do not make io_uring a hard dependency of the
  routing core.

### 4.2 Target architecture

Mirror the existing `services/accounts` workspace (tokio 1, axum 0.7, serde,
tower-http, layering domain → application → http → server). New workspace
`services/transit-rs`:

- `bledi-transit-domain` — modes, tunables, fares, timetable, geo (haversine, polyline
  length), stations. No I/O.
- `bledi-transit-application` — graph build, Dijkstra, planner, itinerary expansion,
  geometry port trait.
- `bledi-transit-graph` — npz/raw loader + A* (road/rail), CSR.
- `bledi-transit-http` — axum routers, extractors, error mapping, rate limit.
- `bledi-transit-server` — binary, config, wiring.

### 4.3 Data structures

- `Station { id: u32, lat: f64, lon: f64, name: Rc<str> }`, `Vec<Station>` +
  `HashMap<Rc<str>, u32>` for id lookup.
- `Line { id: u32, mode: Mode, wait_s: f32, stops: Vec<u32> }`.
- `Edge { to: u32, line: u32, mode: Mode, wait_s: f32, time_s: f32, dist_m: f32,
  straight_m: f32, geom: u32 }` (`geom` = offset into a geometry arena, `u32::MAX` =
  none).
- Adjacency as CSR: `Vec<u32> off`, `Vec<Edge> edges` (built once at startup,
  ~34 k edges → ~1.5 MB).
- Dijkstra state: dense `state_id = station * K + slot`, where `slot` indexes the
  lines serving the station (slot 0 = "no line"). Precompute `K` and the slot table
  at build time. `dist: Vec<f32>`, `prev: Vec<u32>` (~15 k entries each).
- Heap: `BinaryHeap<(OrderedFloat<f32>, u32, u32)>` (cost, station, line) or a custom
  radix heap. The tie-break must be decided explicitly (§4.5).
- Geometry arena: `Vec<[f32;2]>` with offsets, or `Vec<Vec<[f32;2]>>` per edge.

### 4.4 Port order (increments)

1. **Increment 1 — parity harness + Dijkstra.** Load the seed +
   `route_geometry.json` / `walk_geometry.json` / `taxi_geometry.json`, build the
   CSR, port `Router.route` for one strategy, and diff the JSON against the Python
   `/api/v1/route/plan` for a corpus of queries. No live A* yet: geometry comes from
   the caches (this already covers most legs). Success = structurally identical
   `itineraries` (or a documented, accepted diff).
2. **Increment 2 — planner.** Port `plan()` (9 strategies, dedup, ranking,
   `_present`). This is where most of the warm-path win lands.
3. **Increment 3 — axum API.** Port `/route/plan`, `/route/transit`, `/health`,
   `/stations*`, `/lines*`, `/network`, `/map/*`, `/cities`, `/search`, `/geocode`,
   `/louage/links`. Keep the Python service running and gate traffic by a header or
   percentage.
4. **Increment 4 — geometry.** Either port the road/rail A* to Rust (CSR + component
   labels + the same snap grid + the same `0.95` acceptance) or precompute geometry
   for all station pairs and cache access/egress walks on a grid. Keep the Python
   sidecar as a fallback for cache misses.
5. **Increment 5 — io_uring + raw graph format.** Add an uncompressed `.npy`/raw
   export to the builders, mmap it, and use `tokio-uring` for the load on Linux.
   Target startup < 0.5 s.

### 4.5 Risky parts / parity hazards

- **Float parity.** Python uses f64 haversine with `EARTH_RADIUS_M = 6371000.0` and
  `math.asin(sqrt(min(1, a)))`. Rust must use the same f64 formula and the same
  constant; a different earth radius or a fast-approximate distance changes costs and
  can change the chosen itinerary.
- **Heap tie-break.** Python pushes `(cost, station_id, line_str)`; equal-cost states
  are popped in string order of station id, then line id. Rust's `BinaryHeap` is not
  stable and compares only the tuple you give it. To match, push
  `(OrderedFloat(cost), station_id, line_id)` with the same ordering, or accept that
  equal-cost ties may resolve differently (and document it).
- **Early termination.** `if cost >= best_cost: break` stops the search at the first
  end-candidate settlement that reaches the current best. The result depends on the
  order end candidates are settled, which depends on the tie-break. This is the
  single biggest parity risk.
- **Geometry acceptance.** The `>= 0.95 * straight` checks, the `oriented_geometry`
  reversal (`from_id > to_id`), and the "shorter than straight ⇒ discard" rule must be
  reproduced exactly or legs get different distances and times.
- **Walk-edge construction.** The grid `span` rule and the `other <= sid` dedup decide
  which pairs get walk edges. A different grid changes reachability.
- **Side effects.** `add_louage_taxi_transfers` mutates the station dict (adds
  `louage_*` stations) while building the graph; the port must do the same before
  `_nearest_stations` sees them.
- **Mode aliasing.** `resolve_allowed_modes` returns raw seed modes; `canonical_mode`
  folds `rail`→`train` for labels/fares but the raw mode drives speed (`rail` 55 vs
  `train` 60). The port must keep both.
- **Wait model.** `expected_wait` uses the lower median and the overnight gap; a
  different median rule changes boarding waits.
- **Taxi rules.** Same-city check via `nearest_city` (60 km cap, 24 seats),
  `TAXI_MIN_DISTANCE_M`, `MAX_DIRECT_TAXI_M`, and the `alternatives` entry only when
  transit exists.
- **Fares.** `fare_for_itinerary` charges once per boarded line, grouping consecutive
  steps with the same `(line, mode)`.
- **Rate limiting.** 60/60 s per IP is in the Python middleware; the Rust service must
  implement it or the gateway must, or the limit silently disappears.
- **Caching.** The Python memo is an implementation detail, not part of the API. The
  Rust service should not depend on it for correctness, but its absence makes cold
  latency visible; budget for geometry precomputation.

### 4.6 Expected speedup (estimates, not benchmarked)

- **Warm `/route/plan`:** 0.5 s → **5–15 ms** (30–100×). One Python strategy is ~0.1 s;
  Rust should do the Dijkstra in <1 ms and the step-building/JSON in a few ms.
- **Cold `/route/plan`:** 1.5–6 s → **20–100 ms** if geometry is precomputed;
  **200–800 ms** with a ported Rust A* (the road graph is 6.3 M nodes / 13 M edges;
  the Python A* is capped at 12 M expansions and takes seconds for long pairs).
- **Startup:** 2.9 s → **0.2–0.5 s** with a raw/mmap'd graph format.
- **Memory:** the transit graph is a few MB; the road graph is ~530 MB uncompressed
  (mostly `elen` f8 and `espec` u2). Rust can drop `eflags`/`comp_bike` and use f32
  for `elen` to cut this to ~250 MB, or keep the exact dtypes for parity.

### 4.7 Verification plan

- **Golden-file diff:** run N queries against Python and Rust, compare the JSON
  structurally (ignoring key order). Start with the 5 measured queries plus edge
  cases (walk-only, taxi-only, no-route, `max_transfers`, `max_walk_m`, all
  objectives).
- **Parity tests for pure functions:** haversine, `expected_wait`, `canonical_mode`,
  `resolve_allowed_modes`, `fare_for_itinerary`, `_itinerary_signature`.
- **A/B latency:** same queries, same machine, report p50/p90.
- **Fallback:** keep the Python service and a feature flag so a bad Rust response can
  be rolled back.