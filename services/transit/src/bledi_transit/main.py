"""Composition root: configuration, wiring and the FastAPI app.

Run: uvicorn --factory bledi_transit.main:create_app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import time
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from bledi_transit.adapters.graphs.path_geometry import GraphPathGeometry
from bledi_transit.adapters.http import catalog as catalog_routes
from bledi_transit.adapters.http import routing as routing_routes
from bledi_transit.adapters.http.deps import Services
from bledi_transit.adapters.http.errors import install_error_handlers
from bledi_transit.adapters.nominatim import NominatimGeocoder
from bledi_transit.adapters.seed_files import SeedFileNetwork
from bledi_transit.application.catalog import Catalog
from bledi_transit.application.network import Network
from bledi_transit.application.routing.router import Router

REPO_DATA_DIR = Path(__file__).resolve().parents[4] / "data"

# Rate limiting config
RATE_LIMIT_REQUESTS = 60  # requests per window
RATE_LIMIT_WINDOW = 60    # seconds

# 8080 is the Flutter web dev server, 5173 the Vite dev server.
DEFAULT_ORIGINS = (
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://localhost:5173",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
)


@dataclass(frozen=True)
class Config:
    data_dir: Path
    road_graph: Path
    rail_graph: Path
    allowed_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> Config:
        data_dir = Path(os.environ.get("BLEDI_DATA_DIR") or REPO_DATA_DIR)
        if not data_dir.is_dir():
            raise RuntimeError(f"BLEDI_DATA_DIR {data_dir} is not a directory")
        raw = os.environ.get("ALLOWED_ORIGINS", ",".join(DEFAULT_ORIGINS))
        allowed = tuple(o.strip() for o in raw.split(",") if o.strip())
        if not allowed:
            raise RuntimeError("ALLOWED_ORIGINS must not be empty")
        return cls(
            data_dir=data_dir,
            road_graph=Path(os.environ.get("ROAD_GRAPH_PATH") or data_dir / "road_graph.npz"),
            rail_graph=Path(os.environ.get("RAIL_GRAPH_PATH") or data_dir / "rail_graph.npz"),
            allowed_origins=allowed,
        )


def build_router(config: Config, data: SeedFileNetwork, network: Network, **options: Any) -> Router:
    return Router(
        network.station_by_id,
        network.lines,
        segments=network.segments,
        walk_segments=data.walk_segments(),
        taxi_segments=data.taxi_segments(),
        paths=GraphPathGeometry.load(config.road_graph, config.rail_graph),
        louage_stations=network.louage_stations,
        **options,
    )


def build_services(config: Config) -> Services:
    data = SeedFileNetwork(config.data_dir)
    network = data.load()
    return Services(
        catalog=Catalog(network, data),
        router=build_router(config, data, network),
        geocoder=NominatimGeocoder(),
    )


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.from_env()
    logging.basicConfig(level=logging.INFO)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = build_services(config)
        yield

    app = FastAPI(
        title="bledi.tn",
        description="Tunisia public transport routing API",
        version="0.2.0",
        lifespan=lifespan,
    )
    # Rate limiting middleware
    _rate_limit_buckets: dict[str, list[float]] = defaultdict(list)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        # Prune expired entries across all clients so one IP cannot grow the dict without bound.
        for ip, times in list(_rate_limit_buckets.items()):
            _rate_limit_buckets[ip] = [t for t in times if now - t < RATE_LIMIT_WINDOW]
        if len(_rate_limit_buckets[client_ip]) >= RATE_LIMIT_REQUESTS:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                {"error": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(RATE_LIMIT_WINDOW)},
            )
        _rate_limit_buckets[client_ip].append(now)
        return await call_next(request)

    # Never wildcard origins together with credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_methods=["GET"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    install_error_handlers(app)
    app.include_router(catalog_routes.router)
    app.include_router(routing_routes.router)
    return app


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
