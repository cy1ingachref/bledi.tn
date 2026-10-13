from __future__ import annotations

from typing import Any, Protocol


class MapLayers(Protocol):
    """Prebuilt map overlays. Both raise AppError("unavailable") when not built."""

    def map_layer(self, name: str) -> dict[str, Any]: ...

    def louage_links(self) -> dict[str, Any]: ...


class Geocoder(Protocol):
    def search(self, query: str) -> list[dict[str, Any]] | None:
        """Raw place hits with lat, lon, display_name and type; None when unreachable."""
        ...
