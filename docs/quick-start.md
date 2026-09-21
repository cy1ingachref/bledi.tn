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
