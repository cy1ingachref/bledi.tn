from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from bledi_transit.adapters.http.deps import CatalogDep
from bledi_transit.adapters.http.schemas import (
    CityListResponse,
    HealthResponse,
    LineDetail,
    LinesResponse,
    NearResponse,
    StationDetail,
    StationsResponse,
)
from bledi_transit.application.errors import AppError

router = APIRouter(prefix="/api/v1")


@router.get("/health", tags=["System"])
def health(catalog: CatalogDep) -> HealthResponse:
    net = catalog.network
    return HealthResponse(seed_file=net.seed_name, stations_count=len(net.stations), lines_count=len(net.lines))


@router.get("/", tags=["System"])
def root() -> dict[str, Any]:
    return {
        "service": "bledi.tn",
        "version": "0.2.0",
        "description": "Tunisia public transport routing",
        "docs": "/docs",
        "endpoints": {
            "stations": "/api/v1/stations",
            "stations/near": "/api/v1/stations/near",
            "lines": "/api/v1/lines",
            "lines-by-number": "/api/v1/lines/{line_number}",
            "geocode": "/api/v1/geocode",
        },
    }


@router.get("/stations/overpass-taxi-louage", tags=["Stations"])
def overpass_taxi_louage() -> Any:
    """Taxi/louage/bus stations from local Overpass export."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[6] / "data" / "osm_overpass" / "taxi_louage_stations.json"
    if not p.exists():
        return {"type": "FeatureCollection", "features": []}
    obj = json.loads(p.read_text(encoding="utf-8"))
    features = []
    for s in obj.get("stations", []):
        if s.get("lat") is None or s.get("lon") is None:
            continue
        props = {
            "id": s.get("id"),
            "name": s.get("name") or s.get("name_ar") or s.get("name_fr") or s.get("name_en") or "",
            "mode": "taxi_louage",
            "operator": "",
            "type": "station",
            "louage_route_type": s.get("louage_route_type") or "local",
        }
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/stations", response_model=StationsResponse, tags=["Stations"])
def stations(catalog: CatalogDep) -> Any:
    """All stops as GeoJSON, with the canonical mode and the nearest governorate."""
    return catalog.stations()


@router.get("/network", tags=["Network"])
def network(
    catalog: CatalogDep,
    modes: str | None = Query(None, description="Comma-separated modes to include (default: all track modes)"),
    bbox: str | None = Query(
        None, description="min_lon,min_lat,max_lon,max_lat — only return segments overlapping it"
    ),
    simplify: float = Query(
        0.0, ge=0.0, le=0.01, description="Douglas-Peucker tolerance in degrees (0 = no simplification)"
    ),
) -> Any:
    """Physical track per stop pair; a pair without track comes back with `has_geometry: false`."""
    track = catalog.track(modes, bbox, simplify)
    if track is None:
        return JSONResponse(
            {
                "error": "network geometry not built",
                "detail": "route_geometry.json is missing; run services/transit/tools/build_route_geometry.py",
                "segments": [],
            },
            status_code=503,
        )
    return track


@router.get("/map/rail", tags=["Network"])
def map_rail(catalog: CatalogDep) -> dict[str, Any]:
    """Passenger rail and light-rail alignments, `properties.mode` train or metro."""
    return catalog.map_layer("rail", "rail")


@router.get("/map/roads", tags=["Network"])
def map_roads(catalog: CatalogDep) -> dict[str, Any]:
    """Motorway, trunk and primary roads, with `properties.ref` the road number."""
    return catalog.map_layer("roads", "road")


@router.get("/map/overlays", tags=["Network"])
def map_overlays(catalog: CatalogDep) -> dict[str, Any]:
    """Rail and roads together; a layer that is not built carries `error` so the other still draws."""
    out: dict[str, Any] = {}
    for name, kind in (("rail", "rail"), ("roads", "road")):
        try:
            out[name] = catalog.map_layer(name, kind)
        except AppError as exc:
            out[name] = {"features": [], "error": exc.detail}
    return out


@router.get("/louage/links", tags=["Louage"])
def louage_links(catalog: CatalogDep) -> dict[str, Any]:
    """Places each national louage station serves; `unresolved` lists unmatched destinations."""
    return catalog.louage_links()


@router.get("/cities", response_model=CityListResponse, tags=["Stations"])
def cities(catalog: CatalogDep) -> Any:
    """Governorates with per-mode stop counts, largest first."""
    return catalog.cities()


@router.get("/stations/near", response_model=NearResponse, tags=["Stations"])
def stations_near(
    catalog: CatalogDep,
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    limit: int = Query(10, description="Max results"),
) -> Any:
    return catalog.near(lat, lon, limit)


@router.get("/stations/{station_id}", response_model=StationDetail, tags=["Stations"])
def station(catalog: CatalogDep, station_id: str) -> Any:
    """Every line calling at this stop, from the lines' own stop arrays."""
    return catalog.station(station_id)


@router.get("/lines", response_model=LinesResponse, tags=["Lines"])
def lines(catalog: CatalogDep) -> Any:
    return catalog.lines()


@router.get("/lines/{line_identifier}", response_model=LineDetail, tags=["Lines"])
def line(catalog: CatalogDep, line_identifier: str) -> Any:
    """A line by id, or by number (numbers are not unique, the first match wins)."""
    return catalog.line(line_identifier)


# NOTE: /geocode lives in routing.py (Nominatim + 503-on-outage). A second
# /geocode here shadowed it because catalog routes register first, so the
# geocoder outage branch was unreachable. Do not re-add a duplicate route.


@router.get("/search", tags=["Stations"])
def search(
    catalog: CatalogDep,
    q: str = Query(..., min_length=2, description="Free-text place or stop name"),
    limit: int = Query(8, ge=1, le=25, description="Max results"),
    near_lat: float | None = Query(None, description="Bias results toward this latitude"),
    near_lon: float | None = Query(None, description="Bias results toward this longitude"),
) -> dict[str, Any]:
    """Stops, louage hubs and governorates by name; `kind` is `stop` or `city`."""
    return catalog.search(q, limit, near_lat, near_lon)


@router.get("/encyclopedia", tags=["Guide"])
def encyclopedia() -> dict[str, Any]:
    """Rider-facing transport guide + other-modes encyclopedia.

    Sourced from the downloaded reference guides (louage_tunisia.json and
    tunisia_transport_other_modes.json) as data/transport_encyclopedia.json.
    Provides rider-facing reference: what each mode is, how it runs, fares,
    operating hours, key stations, connections and tips.
    """
    import json
    from pathlib import Path

    p = (
        Path(__file__).resolve().parents[6] / "data" / "transport_encyclopedia.json"
    )
    if not p.exists():
        return {"error": "encyclopedia not generated", "generated_by": "scripts/build_encyclopedia.py"}
    return json.loads(p.read_text(encoding="utf-8"))
