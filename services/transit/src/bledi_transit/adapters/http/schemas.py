from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.2.0"
    service: str = "bledi.tn"
    seed_file: str
    stations_count: int
    lines_count: int


class StationGeoJSON(BaseModel):
    type: str = "Feature"
    geometry: dict[str, Any]
    properties: dict[str, Any]


class StationsMeta(BaseModel):
    count: int
    total: int
    by_mode: dict[str, int] = Field(default_factory=dict)


class StationsResponse(BaseModel):
    type: str = "FeatureCollection"
    features: list[StationGeoJSON]
    metadata: StationsMeta


class CitySummary(BaseModel):
    name: str
    lat: float
    lon: float
    station_count: int
    by_mode: dict[str, int] = Field(default_factory=dict)


class CityListResponse(BaseModel):
    cities: list[CitySummary]
    count: int


class NearStation(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    dist_m: float
    lines: list[Any] = Field(default_factory=list)


class NearResponse(BaseModel):
    near: list[NearStation]
    query: dict[str, float]


class StationLineInfo(BaseModel):
    line_id: str
    number: str | None = None
    name: str | None = None
    mode: str
    mode_label: str
    operator: str | None = None
    color: str | None = None
    direction: str | None = None
    stops_count: int = 0
    stop_index: int | None = None
    role: str = "through"  # origin | terminus | through


class StationDetail(BaseModel):
    id: str
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    city: str | None = None
    modes: list[str]
    lines: list[StationLineInfo]
    count: int
    # False when no line's stop array lists this stop: its mode is then only
    # the operator's tag, and the client phrases the empty list accordingly.
    lines_known: bool = False


class LineSummary(BaseModel):
    id: str
    number: str | None = None
    short_name: str | None = None
    long_name: str | None = None
    mode: str = "bus"
    color: str | None = None
    route_id: str | None = None
    stops_count: int = 0


class LinesResponse(BaseModel):
    lines: list[LineSummary]
    count: int


class StopInfo(BaseModel):
    stop_id: str | None = None
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    order: int | None = None
    schedule: list[str] | None = None
    lines: list[Any] | None = None


class LineDetail(BaseModel):
    line: dict[str, Any]
    stops: list[StopInfo]
    count: int
    mode: str | None = None
    mode_label: str | None = None
    geometry: dict[str, Any] | None = None  # GeoJSON LineString, [[lon, lat]]
    geometry_complete: bool = False
    geometry_segments: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
