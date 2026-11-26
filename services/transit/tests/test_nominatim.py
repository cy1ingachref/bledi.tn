"""H4 regression tests for the Nominatim adapter (no network calls)."""
from __future__ import annotations

import json
import time

import pytest

from bledi_transit.adapters import nominatim as mod


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._payload


@pytest.fixture
def no_sleep(monkeypatch):
    """Avoid real sleeps; record requested throttle delays."""
    delays = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: delays.append(s))
    return delays


def test_contact_from_env(monkeypatch):
    monkeypatch.setenv("NOMINATIM_CONTACT", "ops@example.org")
    assert mod.contact_from_env(production=True) == "ops@example.org"


def test_production_requires_contact(monkeypatch):
    monkeypatch.delenv("NOMINATIM_CONTACT", raising=False)
    with pytest.raises(RuntimeError):
        mod.contact_from_env(production=True)
    assert mod.contact_from_env(production=False) == mod.DEFAULT_CONTACT


def test_user_agent_uses_configured_contact(monkeypatch):
    seen = []

    def fake_urlopen(req, timeout):
        seen.append(req.get_header("User-agent"))
        return FakeResponse([{"lat": "36.8"}])

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    g = mod.NominatimGeocoder(contact="team@example.org", min_interval_s=0)
    assert g.search("Tunis") == [{"lat": "36.8"}]
    assert seen and "team@example.org" in seen[0]


def test_throttle_between_upstream_calls(monkeypatch, no_sleep):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, timeout))
        return FakeResponse([{"ok": True}])

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    g = mod.NominatimGeocoder(min_interval_s=1.0, timeout_s=5.0)
    g.search("a")
    g.search("b")  # different key -> a second upstream call -> throttle sleep
    assert len(calls) == 2
    assert no_sleep and no_sleep[0] > 0
    assert all(kw_timeout == 5.0 for _, kw_timeout in calls)


def test_lru_eviction_keeps_recent_entries(monkeypatch):
    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: FakeResponse([]))
    g = mod.NominatimGeocoder(min_interval_s=0, max_entries=2)
    g.search("a")
    g.search("b")
    g.search("a")  # refresh a as most-recent
    g.search("c")  # should evict b, not a
    assert "a" in g._cache and "c" in g._cache and "b" not in g._cache
    assert len(g._cache) == 2


def test_failure_is_cached_briefly(monkeypatch):
    calls = []

    def failing(*a, **k):
        calls.append(1)
        raise OSError("offline")

    monkeypatch.setattr(mod.urllib.request, "urlopen", failing)
    g = mod.NominatimGeocoder(min_interval_s=0, failure_ttl_s=30)
    assert g.search("tunis") is None
    assert g.search("tunis") is None
    assert len(calls) == 1  # the second call was served from the negative cache

    # An expired negative entry is retried.
    ts, _ = g._cache["tunis"]
    g._cache["tunis"] = (ts - 31, None)
    g.search("tunis")
    assert len(calls) == 2
