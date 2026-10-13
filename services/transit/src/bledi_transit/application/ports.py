from __future__ import annotations

from typing import Any, Protocol


class MapLayers(Protocol):
    """Prebuilt map overlays. Both raise AppError("unavailable") when not built."""

    def map_layer(self, name: str) -> dict[str, Any]: ...

    def louage_links(self) -> dict[str, Any]: ...


Polyline = list[list[float]]


class PathGeometry(Protocol):
    """Live paths on the physical networks.

    road and rail return (polyline, metres along it), or None when the network
    cannot serve the pair. A straight line is never an answer.
    """

    def road(self, a_lat: float, a_lon: float, b_lat: float, b_lon: float, mode: str) -> tuple[Polyline, float] | None: ...

    def rail(self, a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> tuple[Polyline, float] | None: ...

    def foot_bridges(self, a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> list[Polyline]:
        """Walks routed through foot nodes near each end, for endpoints in disconnected foot components."""
        ...


class Geocoder(Protocol):
    def search(self, query: str) -> list[dict[str, Any]] | None:
        """Raw place hits with lat, lon, display_name and type; None when unreachable."""
        ...
