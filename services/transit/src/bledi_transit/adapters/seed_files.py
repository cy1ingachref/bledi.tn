"""The network, geometry caches and map layers, read from the data directory."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from bledi_transit.application.network import Network, Segments

log = logging.getLogger("bledi.data")

SEED_FILE = "seed_all_tunisia_routes.tagged.json"
LOUAGE_SEED_FILE = "seed_routes_destination_tunis.json"
ROUTE_GEOMETRY_FILE = "route_geometry.json"
WALK_GEOMETRY_FILE = "walk_geometry.json"
TAXI_GEOMETRY_FILE = "taxi_geometry.json"
MAP_LAYER_FILES = {"rail": "map_rail.geojson", "roads": "map_roads.geojson"}
LOUAGE_LINKS_FILE = "louage_links.json"


@lru_cache(maxsize=None)
def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


class SeedFileNetwork:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def load(self) -> Network:
        seed_path = self.data_dir / SEED_FILE
        seed = _read_json(seed_path)
        louage = self._optional(LOUAGE_SEED_FILE) or {}
        network = Network(
            stations=seed.get("stations", []),
            lines=seed.get("lines", []),
            seed_name=seed_path.name,
            louage_stations=louage.get("stations", []),
            louage_routes=louage.get("routes", []),
            segments=self.route_segments(),
        )
        log.info(
            "loaded seed: %d stations, %d lines, %d louage stops from %s",
            len(network.stations), len(network.lines), len(network.louage_stations), seed_path.name,
        )
        return network

    def route_segments(self) -> Segments:
        segs = self._segments(ROUTE_GEOMETRY_FILE)
        if not segs:
            log.warning(
                "no route geometry in %s; transit legs fall back to straight lines. "
                "Build it with: python services/transit/tools/build_route_geometry.py",
                self.data_dir,
            )
        return segs

    def walk_segments(self) -> Segments:
        return self._segments(WALK_GEOMETRY_FILE)

    def taxi_segments(self) -> Segments:
        return self._segments(TAXI_GEOMETRY_FILE)

    def has_route_segments(self) -> bool:
        return (self.data_dir / ROUTE_GEOMETRY_FILE).exists()

    def map_layer(self, name: str) -> dict[str, Any] | None:
        return self._optional(MAP_LAYER_FILES[name])

    def map_layer_file(self, name: str) -> str:
        return MAP_LAYER_FILES[name]

    def louage_links(self) -> dict[str, Any] | None:
        return self._optional(LOUAGE_LINKS_FILE)

    def _segments(self, name: str) -> Segments:
        data = self._optional(name)
        return data.get("segments", {}) if data else {}

    def _optional(self, name: str) -> Any | None:
        path = self.data_dir / name
        return _read_json(path) if path.exists() else None
