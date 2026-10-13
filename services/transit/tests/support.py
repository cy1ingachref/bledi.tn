"""One app per test session: the seed, geometry caches and graphs load once."""
from __future__ import annotations

from functools import cache
from typing import Any

from fastapi.testclient import TestClient

from bledi_transit.adapters.http.deps import Services
from bledi_transit.adapters.seed_files import SeedFileNetwork
from bledi_transit.application.routing.router import Router
from bledi_transit.application.routing.transit import router_to_option
from bledi_transit.main import Config, build_router, create_app


@cache
def client() -> TestClient:
    c = TestClient(create_app(Config.from_env()))
    c.__enter__()  # runs the lifespan
    return c


def services() -> Services:
    return client().app.state.services


def fresh_router(**options: Any) -> Router:
    """A router on the real data with one build option changed."""
    config = Config.from_env()
    data = SeedFileNetwork(config.data_dir)
    return build_router(config, data, data.load(), **options)


def to_option(router_out: dict[str, Any]) -> dict[str, Any]:
    return router_to_option(router_out, services().catalog.network.segment_geometry)
