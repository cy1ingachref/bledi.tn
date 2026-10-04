# Quick start

## Prerequisites

- Python 3.11+ with pip
- (Optional) Docker, for OSRM driving-route geometry

## Install

```bash
python -m pip install -r requirements.txt
```

## Run the API

```bash
uvicorn src.backend.app.main:app --host 127.0.0.1 --port 8000
```

The API serves `frontend/index.html` at `/` and the API itself under `/api/v1/*`.

## Optional: OSRM

OSRM provides driving/taxi road geometry. The API falls back gracefully if OSRM
is not available.

```bash
docker pull osrm/osrm-backend
docker run -t -v "${PWD}:/data -p 5000:5000 osrm/osrm-backend osrm-routed --algorithm mld /data/scripts/tunisia-latest.osrm
```

Set `OSRM_URL=http://localhost:5000/route/v1/driving` if the container uses a
different port.

## Open the frontend

- Via the API: `http://localhost:8000`
- Directly from disk: open `frontend/index.html` in a browser (it calls
  `http://localhost:8000/api/v1/*` — start the API first).

## First trip

1. Click **Repère le départ** / **Repère l'arrivée** on the map, or type a place
   name in the search boxes and click **Rechercher**.
2. Optionally pick a departure time.
3. Click **Itinéraire transport public** for transit, or **Calculer l'itinéraire
   (OSRM)** for driving/taxi.
4. Results appear in the panel; click an option to show it on the map.

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

`objective=cheapest` ranks on a documented heuristic in `routing.FARE_DINARS`
(base DT + DT per km), charged **once per boarded line** — an itinerary is
expanded per stop, so charging per leg over-quoted a bus+train trip ~5x. Never
returns `null`.

### Legacy endpoints

`/api/v1/route/transit`, `/api/v1/route/options` and `/api/v1/route/modes` still
work unchanged for existing clients. `/api/v1/route/plan` is the endpoint to use
for new work.

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `OSRM_URL` | `http://localhost:5000/route/v1/driving` | OSRM endpoint |
| `OSRM_TIMEOUT` | `10` | OSRM request timeout (seconds) |
| `ALLOWED_ORIGINS` | `http://127.0.0.1:8000,http://localhost:8000,http://localhost:5173` | CORS origins |
| `ENABLE_TUNISMAPPER_PROXY` | unset | Set to `1`/`true`/`yes` to re-enable the Tunismapper itinerary proxy (disabled by default, returns 410) |

## Tests

```bash
python -m pytest tests/ -v
```

## Data provenance and licensing

Most routing data is derived from Tunismapper. The terms of that source have not
been verified. See `docs/provenance.md` and `LICENSE.TODO`. No license is claimed
for the dataset yet.
