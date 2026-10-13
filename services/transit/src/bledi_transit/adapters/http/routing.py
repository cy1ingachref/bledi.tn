from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from bledi_transit.adapters.http.deps import CatalogDep, GeocoderDep, RouterDep
from bledi_transit.application.errors import AppError
from bledi_transit.application.routing.transit import transit_itinerary

router = APIRouter(prefix="/api/v1")


def _split(raw: str | None) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()] if raw else []


@router.get("/route/plan", tags=["Routing"])
def route_plan(
    planner: RouterDep,
    start_lat: float = Query(..., description="Start latitude"),
    start_lon: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lon: float = Query(..., description="End longitude"),
    modes_include: str | None = Query(None, description="Comma-separated modes to allow, e.g. bus,metro,walk"),
    modes_exclude: str | None = Query(None, description="Comma-separated modes to forbid, e.g. train,metro"),
    objective: str = Query("fastest", description="fastest | cheapest | fewest_transfers"),
    max_transfers: int | None = Query(None, ge=0, description="Cap on line changes"),
    max_walk_m: float | None = Query(None, gt=0, description="Cap access+egress walk (m)"),
    max_itineraries: int = Query(3, ge=1, le=8),
) -> dict[str, Any]:
    """Distinct, labelled itineraries for a mode filter and an objective.

    Excluded modes are filtered inside the search, so they never appear in a leg.
    """
    try:
        return planner.route_plan(
            start_lat,
            start_lon,
            end_lat,
            end_lon,
            include=_split(modes_include),
            exclude=_split(modes_exclude),
            objective=objective,
            max_transfers=max_transfers,
            max_walk_m=max_walk_m,
            max_itineraries=max_itineraries,
        )
    except ValueError as exc:
        raise AppError("invalid_request", str(exc)) from exc


@router.get("/route/transit", tags=["Routing"])
def route_transit(
    planner: RouterDep,
    catalog: CatalogDep,
    start_lat: float = Query(..., description="Start latitude"),
    start_lon: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lon: float = Query(..., description="End longitude"),
) -> dict[str, Any]:
    """The fastest itinerary in the best_fastest / legs envelope."""
    return transit_itinerary(
        planner.route(start_lat, start_lon, end_lat, end_lon),
        catalog.network.segment_geometry,
    )


@router.get("/geocode", tags=["Stations"])
def geocode(
    geocoder: GeocoderDep,
    q: str = Query(..., description="Place name to search in Tunisia"),
    limit: int = Query(3, description="Max results"),
) -> Any:
    """Place search through Nominatim, cached server side."""
    data = geocoder.search(q)
    if not data:
        return JSONResponse({"error": "Geocoding service unreachable", "source": "nominatim"}, status_code=503)
    results = [
        {
            "lon": float(d["lon"]),
            "lat": float(d["lat"]),
            "display_name": d.get("display_name", ""),
            "type": d.get("type", ""),
        }
        for d in data[:limit]
    ]
    return {"query": q, "results": results, "count": len(results)}
