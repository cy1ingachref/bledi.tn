"""Place search through OpenStreetMap Nominatim, restricted to Tunisia.

Hardened per H4 in bledi-fixes-handoff.md:
- contact is read from NOMINATIM_CONTACT (required in production);
- a lock-protected minimum interval of 1 s is kept between upstream calls
  (Nominatim's public policy allows about 1 request/second);
- the timeout is configurable (default 5 s, down from 15) so a slow upstream
  cannot pin a sync worker thread for long;
- the cache is an LRU with TTL, not a `.clear()` cliff at 1,024 entries;
- failures are negatively cached briefly to avoid hammering an outage.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Any

log = logging.getLogger("bledi.geocode")

CACHE_MAX_ENTRIES = 1024
DEFAULT_MIN_INTERVAL_S = 1.0
DEFAULT_TIMEOUT_S = 5.0
DEFAULT_FAILURE_TTL_S = 30.0
DEFAULT_CONTACT = "maintainer@bledi.tn"  # development fallback only


def contact_from_env(*, production: bool | None = None) -> str:
    """Return the configured contact; fail startup in production when absent."""
    value = os.environ.get("NOMINATIM_CONTACT", "").strip()
    if value:
        return value
    if production is None:
        production = os.environ.get("BLEDI_ENV", "").lower() in {"prod", "production"}
    if production:
        raise RuntimeError("NOMINATIM_CONTACT must be set in production")
    return DEFAULT_CONTACT


class NominatimGeocoder:
    def __init__(
        self,
        base_url: str = "https://nominatim.openstreetmap.org",
        ttl_s: float = 3600.0,
        *,
        contact: str | None = None,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        failure_ttl_s: float = DEFAULT_FAILURE_TTL_S,
        max_entries: int = CACHE_MAX_ENTRIES,
    ) -> None:
        self.base_url = base_url
        self.ttl_s = ttl_s
        self.contact = contact or contact_from_env()
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self.failure_ttl_s = failure_ttl_s
        self.max_entries = max_entries
        self._cache: OrderedDict[str, tuple[float, list[dict[str, Any]] | None]] = OrderedDict()
        self._lock = threading.Lock()
        self._last_call = 0.0

    def _cache_get(self, key: str) -> tuple[bool, list[dict[str, Any]] | None]:
        with self._lock:
            hit = self._cache.get(key)
            if hit is None:
                return False, None
            ts, value = hit
            ttl = self.ttl_s if value is not None else self.failure_ttl_s
            if time.monotonic() - ts > ttl:
                del self._cache[key]
                return False, None
            self._cache.move_to_end(key)
            return True, value

    def _cache_put(self, key: str, value: list[dict[str, Any]] | None) -> None:
        with self._lock:
            self._cache[key] = (time.monotonic(), value)
            self._cache.move_to_end(key)
            while len(self._cache) > self.max_entries:
                self._cache.popitem(last=False)

    def _throttle(self) -> None:
        with self._lock:
            wait = self.min_interval_s - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def search(self, query: str) -> list[dict[str, Any]] | None:
        key = query.strip().lower()
        cached, value = self._cache_get(key)
        if cached:
            return value  # may be a short-lived negative cache entry

        self._throttle()
        url = f"{self.base_url}/search?q={urllib.parse.quote(query)}&countrycodes=tn&limit=3&format=json"
        user_agent = f"bledi.tn/0.2.0 (transport routing; contact: {self.contact})"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": user_agent})
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode())
        except Exception as exc:
            log.warning("Nominatim unreachable: %s", exc)
            self._cache_put(key, None)
            return None
        self._cache_put(key, data)
        return data
