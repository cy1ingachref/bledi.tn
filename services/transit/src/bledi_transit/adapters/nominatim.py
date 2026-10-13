"""Place search through OpenStreetMap Nominatim, restricted to Tunisia."""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger("bledi.geocode")

USER_AGENT = "bledi.tn/0.2.0 (transport routing; contact: maintainer@bledi.tn)"
CACHE_MAX_ENTRIES = 1024


class NominatimGeocoder:
    # Nominatim's usage policy asks for an identifying User-Agent and no
    # repeated identical queries, hence the server-side cache.
    def __init__(self, base_url: str = "https://nominatim.openstreetmap.org", ttl_s: float = 3600.0) -> None:
        self.base_url = base_url
        self.ttl_s = ttl_s
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def search(self, query: str) -> list[dict[str, Any]] | None:
        key = query.strip().lower()
        hit = self._cache.get(key)
        if hit is not None and time.time() - hit[0] <= self.ttl_s:
            return hit[1]
        url = f"{self.base_url}/search?q={urllib.parse.quote(query)}&countrycodes=tn&limit=3&format=json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except Exception as exc:
            log.warning("Nominatim unreachable: %s", exc)
            return None
        if len(self._cache) >= CACHE_MAX_ENTRIES:
            self._cache.clear()
        self._cache[key] = (time.time(), data)
        return data
