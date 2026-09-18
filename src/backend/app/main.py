#!/usr/bin/env python3
"""
BLEDI.TN — Tunisia Transport & Places App
FastAPI Backend

Run: uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os

app = FastAPI(
    title="BLEDI.TN API",
    description="Tunisia Transport & Places — louage, bus, train, metro",
    version="0.1.0",
)

# CORS for Flutter web and mobile
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    version: str
    service: str


class StationResponse(BaseModel):
    id: str
    name_ar: str
    name_fr: Optional[str] = None
    name_en: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    governorate: Optional[str] = None
    station_type: Optional[str] = None


class LineResponse(BaseModel):
    id: str
    line_number: Optional[str] = None
    line_name: Optional[str] = None
    operator: Optional[str] = None
    mode: str
    description: Optional[str] = None
    frequency: Optional[str] = None
    stations: List[StationResponse] = []


class StopInfo(BaseModel):
    name_ar: str
    name_fr: Optional[str] = None
    name_en: Optional[str] = None
    order: int
    is_get_off: bool = False


class RouteOption(BaseModel):
    id: str
    mode: str
    mode_ar: str
    line_name: str
    line_number: Optional[str] = None
    origin_station: str
    destination_station: str
    origin_ar: str
    destination_ar: str
    walk_distance_m: Optional[int] = None
    walk_duration_min: Optional[int] = None
    ride_duration_min: Optional[int] = None
    fare_dt: Optional[int] = None
    stops: List[StopInfo] = []
    departures: List[str] = []
    frequency: Optional[str] = None


@app.get("/api/v1/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="0.1.0", service="bledi-tn-api")


@app.get("/api/v1/", tags=["System"])
async def root():
    return {
        "service": "BLEDI.TN API",
        "version": "0.1.0",
        "description": "Tunisia Transport & Places",
        "docs": "/docs",
        "endpoints": {
            "stations": "/api/v1/stations",
            "lines": "/api/v1/lines",
            "routes": "/api/v1/routes",
            "nearby": "/api/v1/nearby",
        }
    }


@app.get("/api/v1/stations", response_model=List[StationResponse], tags=["Stations"])
async def list_stations(
    q: Optional[str] = Query(None, description="Search query"),
    governorate: Optional[str] = Query(None),
    station_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List transport stations with optional filtering."""
    # TODO: Implement with actual DB query
    return []


@app.get("/api/v1/stations/{station_id}", response_model=StationResponse, tags=["Stations"])
async def get_station(station_id: str):
    """Get a single station by ID."""
    raise HTTPException(status_code=501, detail="Not yet implemented")


@app.get("/api/v1/lines", response_model=List[LineResponse], tags=["Lines"])
async def list_lines(
    mode: Optional[str] = Query(None, description="bus, louage, train, metro, taxi"),
    operator: Optional[str] = Query(None),
    origin: Optional[str] = Query(None),
    destination: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """List transport lines with optional filtering."""
    return []


@app.get("/api/v1/lines/{line_id}", response_model=LineResponse, tags=["Lines"])
async def get_line(line_id: str):
    """Get a single line with all its stops."""
    raise HTTPException(status_code=501, detail="Not yet implemented")


@app.get("/api/v1/routes", response_model=List[RouteOption], tags=["Routing"])
async def find_routes(
    from_lat: float = Query(..., description="Origin latitude"),
    from_lon: float = Query(..., description="Origin longitude"),
    to_lat: float = Query(..., description="Destination latitude"),
    to_lon: float = Query(..., description="Destination longitude"),
    max_walk_km: float = Query(2.0, description="Max walking distance in km"),
    mode: Optional[str] = Query(None, description="Preferred transport mode"),
    limit: int = Query(5, ge=1, le=20),
):
    """
    Find transport routes from origin to destination.
    
    Returns options sorted by total duration (walk + wait + ride).
    Each option includes all midway stops.
    """
    return []


@app.get("/api/v1/nearby", response_model=List[StationResponse], tags=["Stations"])
async def nearby_stations(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius_km: float = Query(2.0, description="Search radius in km"),
    limit: int = Query(10, ge=1, le=50),
):
    """Find stations near a location."""
    return []


# Database connection placeholder
# TODO: Add SQLAlchemy + GeoAlchemy2 setup with PostGIS
# TODO: Add seed data loading on startup
# TODO: Implement all endpoint logic with spatial queries


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
