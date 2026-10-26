# Quick start

## Run everything

```bash
cp .env.example .env    # then fill each value with: openssl rand -hex 32
docker compose up --build
```

Open `http://localhost:8080`. The web gateway serves the app and sends
`/api/v1/*` to the right service (see [architecture](architecture.md)).

## Work on one part

Transit, on `:8000`:

```bash
pip install -e 'services/transit[dev]'
uvicorn --factory bledi_transit.main:create_app --port 8000
```

Web, on `:8080`. The dev server proxies the accounts paths to `:3000` and every
other `/api` path to `:8000`:

```bash
cd apps/web && npm ci && npm run dev
```

Tests:

```bash
cd apps/web && npm test
```

Accounts needs PostgreSQL; see the [README](../README.md#accounts).

## Routing: modes, objectives, stations and lines

### `GET /api/v1/route/plan` — the main routing endpoint

Multi-objective, mode-filtered routing. Returns up to `max_itineraries`
**distinct, labelled** itineraries.

| Param | Type | Default | Notes |
|---|---|---|---|
| `start_lat`, `start_lon`, `end_lat`, `end_lon` | float | required | Origin and destination |
| `modes_include` | csv | *(all)* | e.g. `bus,metro,train` |
| `modes_exclude` | csv | *(none)* | e.g. `train,metro` |
| `objective` | enum | `fastest` | `fastest` \| `cheapest` \| `fewest_transfers` |
| `max_transfers` | int | unset | Hard cap on line changes |
| `max_walk_m` | float | unset | Caps the access + egress walk |
| `max_itineraries` | int 1..8 | `3` | Distinct options returned |

**Modes** are flat and independently selectable — `metro` is *not* folded into
`train`, so "no metro but trains are fine" is expressible:

`bus`, `tram`, `metro`, `train` (incl. seed `rail`), `louaj`, `taxi`, `walk`

`modes_exclude` is applied **inside Dijkstra edge expansion**, so an excluded
mode can never appear in a leg. An unknown mode name returns **400** with the
list of valid modes.

```bash
# Fastest overall
curl "http://127.0.0.1:8000/api/v1/route/plan?start_lat=36.7961&start_lon=10.18055&end_lat=36.75978&end_lon=10.19059"

# No metro at all (hard filter)
curl "http://127.0.0.1:8000/api/v1/route/plan?start_lat=36.7961&start_lon=10.18055&end_lat=36.75978&end_lon=10.19059&modes_exclude=metro"

# Fewest transfers
curl "http://127.0.0.1:8000/api/v1/route/plan?start_lat=36.7961&start_lon=10.18055&end_lat=36.75978&end_lon=10.19059&objective=fewest_transfers"

# Cheapest (metro here is slower but cheaper, so it wins)
curl "http://127.0.0.1:8000/api/v1/route/plan?start_lat=36.7961&start_lon=10.18055&end_lat=36.75978&end_lon=10.19059&objective=cheapest"

# Bus-only intercity, cap transfers
curl "http://127.0.0.1:8000/api/v1/route/plan?start_lat=36.8065&start_lon=10.1815&end_lat=35.8256&end_lon=10.6360&modes_include=bus&max_transfers=1"
```

Response shape:

```json
{
  "query":      { "start": {...}, "end": {...}, "modes_include": [], "modes_exclude": ["metro"], "objective": "cheapest" },
  "itineraries": [
    {
      "id": "opt_1",
      "label": "Metro · 32 min · direct",
      "rank_reason": "le moins cher · 0.60 DT · 32 min",
      "duration_min": 32.2,
      "transfers": 0,
      "fare_estimate_dinars": 0.6,
      "modes_used": ["metro"],
      "legs": [ ... ],
      "geometry_complete": false,
      "gaps": [ { "type": "ride", "line": "rail_19_a", "distance_m": 1575, "reason": "no_cached_geometry" } ]
    }
  ],
  "available_modes": ["bus","tram","metro","train","louaj","taxi","walk"],
  "message": null
}
```

`geometry_complete: false` + a populated `gaps[]` means the client must draw
those legs **dashed**. A straight line is never presented as a vehicle path.

### `GET /api/v1/stations/{id}` — what passes here

Built from the line→stops index (not the station's own `lines_served`
fragments, which are direction-oriented and lack stable ids).

```bash
curl "http://127.0.0.1:8000/api/v1/stations/place_barcelone_sud"
```

```json
{
  "id": "place_barcelone_sud", "name": "PLACE BARCELONE SUD",
  "lat": 36.7961, "lon": 10.18055,
  "modes": ["metro"],
  "lines": [
    { "line_id": "metro_50_1", "number": "1", "name": "...", "mode": "metro",
      "mode_label": "Metro", "operator": "Transtu", "color": null,
      "direction": "PLACE BARCELONE SUD - BEN AROUS", "stops_count": 11 }
  ],
  "count": 2
}
```

Unknown id → **404**. Lines are sorted by mode (`bus, tram, metro, train,
louaj, taxi`), then number, then name.

### `GET /api/v1/lines/{id}` — full path with honest geometry

```bash
curl "http://127.0.0.1:8000/api/v1/lines/train_23_sncft"
```

Adds to the existing response: `mode`, `mode_label`, `geometry`,
`geometry_complete`, `geometry_segments[]` and `gaps[]`.

When track is missing for some stop pairs, `geometry` is **`null`** and each
missing pair is listed in `gaps[]` with its `gap_m`. A single straight line from
first stop to last is **never** fabricated:

```json
{
  "count": 18,
  "geometry_complete": false,
  "geometry": null,
  "gaps": [
    { "from_name": "Bouficha", "to_name": "Enfida", "gap_m": 20124, "reason": "no_cached_geometry" }
  ]
}
```

### Fare model

`objective=cheapest` ranks on a documented heuristic in `domain/fares.py`
(base DT + DT per km), charged **once per boarded line** — an itinerary is
expanded per stop, so charging per leg over-quoted a bus+train trip ~5x. Never
returns `null`.

### `GET /api/v1/route/transit`

The fastest itinerary, in the `best_fastest` / `legs` envelope the mobile app reads.
`/api/v1/route/plan` is the endpoint to use for new work.

## Transit environment variables

- `BLEDI_DATA_DIR`: the seed and geometry files, `data/` in the repo by default.
- `ROAD_GRAPH_PATH`, `RAIL_GRAPH_PATH`: the routing graphs, `road_graph.npz` and
  `rail_graph.npz` in the data directory by default. Without the road graph,
  road legs fall back to the geometry caches or straight lines.
- `ALLOWED_ORIGINS`: comma separated CORS origins, the local dev and gateway
  origins by default.

## Tests

```bash
cd services/transit && lint-imports && pytest
```

## Data provenance and licensing

Most routing data is derived from Tunismapper. The terms of that source have not
been verified. See `docs/provenance.md` and `LICENSE.TODO`. No license is claimed
for the dataset yet.
