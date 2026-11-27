"""H1/PR5 regression tests: per-IP rate limiting and trust boundaries."""
from __future__ import annotations

import time
from collections import deque

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bledi_transit.adapters.http import rate_limit as rl
from bledi_transit.adapters.http.rate_limit import (
    client_key,
    install_rate_limit,
    prune_buckets,
)


class FakeClient:
    def __init__(self, host: str):
        self.host = host


class FakeRequest:
    def __init__(self, host: str, headers: dict[str, str] | None = None):
        self.client = FakeClient(host)
        self.headers = headers or {}


def test_xff_ignored_without_trust_proxy():
    req = FakeRequest("10.0.0.5", {"x-forwarded-for": "1.2.3.4"})
    assert client_key(req, trust_proxy=False) == "10.0.0.5"


def test_xff_first_entry_used_when_trusted():
    req = FakeRequest("10.0.0.5", {"x-forwarded-for": "1.2.3.4, 10.0.0.5"})
    assert client_key(req, trust_proxy=True) == "1.2.3.4"


def test_prune_deletes_idle_keys():
    buckets = {"a": deque([time.monotonic() - 100]), "b": deque([time.monotonic()])}
    prune_buckets(buckets, time.monotonic(), 60)
    assert "a" not in buckets
    assert "b" in buckets


def _limited_app(*, trust_proxy: bool, limit: int = 2, window: float = 60) -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/route/plan")
    def route_plan():
        return {"ok": True}

    @app.get("/api/v1/stations")
    def stations():
        return {"ok": True}

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    @app.get("/health")
    def root_health():
        return {"status": "ok"}

    install_rate_limit(app, limit=limit, window=window, trust_proxy=trust_proxy)
    return app


def _get(c: TestClient, path: str = "/api/v1/route/plan", xff: str | None = None) -> int:
    headers = {"X-Forwarded-For": xff} if xff is not None else None
    return c.get(path, headers=headers).status_code


def test_two_clients_have_independent_budgets():
    c = TestClient(_limited_app(trust_proxy=True))
    for ip in ("1.1.1.1", "2.2.2.2"):
        headers = {"X-Forwarded-For": ip}
        assert c.get("/api/v1/route/plan", headers=headers).status_code == 200
        assert c.get("/api/v1/route/plan", headers=headers).status_code == 200
        assert c.get("/api/v1/route/plan", headers=headers).status_code == 429
    assert c.get("/api/v1/route/plan", headers={"X-Forwarded-For": "3.3.3.3"}).status_code == 200


def test_health_endpoints_are_exempt():
    c = TestClient(_limited_app(trust_proxy=False))
    for _ in range(10):
        assert c.get("/api/v1/health").status_code == 200
        assert c.get("/health").status_code == 200


# --- PR5: same-socket-peer cases (the gateway setup) -----------------------

def test_trusted_proxy_separate_buckets():
    """Three requests from client A fill its bucket; A's 4th is 429.

    A single request from client B over the *same* socket peer gets 200: its
    own bucket. This is the exact bug scenario — without trust, both would
    share the gateway's socket peer and B would be 429 as well.
    """
    c = TestClient(_limited_app(trust_proxy=True, limit=3))
    for _ in range(3):
        assert _get(c, xff="203.0.113.9") == 200
    assert _get(c, xff="203.0.113.9") == 429
    assert _get(c, xff="203.0.113.10") == 200


def test_untrusted_proxy_ignores_xff():
    """With trust off, XFF is ignored and all clients share the socket peer."""
    c = TestClient(_limited_app(trust_proxy=False, limit=3))
    for _ in range(3):
        assert _get(c, xff="203.0.113.9") == 200
    assert _get(c, xff="203.0.113.10") == 429
    assert _get(c, xff="203.0.113.9") == 429


def test_only_first_xff_entry_used():
    """The gateway overwrites XFF; only the first entry is the bucket key."""
    c = TestClient(_limited_app(trust_proxy=True, limit=3))
    for _ in range(3):
        assert _get(c, xff="203.0.113.9, 198.51.100.7") == 200
    # Same first entry -> still blocked, even though the second entry differs.
    assert _get(c, xff="203.0.113.9, 192.0.2.44") == 429
    # Different first entry -> independent bucket.
    assert _get(c, xff="198.51.100.7, 203.0.113.9") == 200


def test_missing_xff_falls_back_to_peer():
    """Trusted proxy but no header: key on the socket peer, no crash."""
    c = TestClient(_limited_app(trust_proxy=True, limit=3))
    for _ in range(3):
        assert _get(c) == 200
    assert _get(c) == 429


def test_idle_keys_deleted_through_middleware(monkeypatch):
    """The middleware drops an expired bucket from its dict on the next request."""
    clock = {"now": 1_000.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: clock["now"])

    seen: dict = {}
    real_prune = rl.prune_buckets

    def spy_prune(buckets, now, window):
        seen["buckets"] = buckets
        real_prune(buckets, now, window)

    monkeypatch.setattr(rl, "prune_buckets", spy_prune)

    c = TestClient(_limited_app(trust_proxy=True, limit=3, window=60))
    assert _get(c, xff="203.0.113.9") == 200
    assert "203.0.113.9" in seen["buckets"]

    clock["now"] += 61.0
    assert _get(c, xff="203.0.113.10") == 200  # triggers prune of the idle key
    assert "203.0.113.9" not in seen["buckets"]
    assert "203.0.113.10" in seen["buckets"]


def test_install_rate_limit_logs_trust_proxy(caplog):
    """Startup logs the effective value so misconfiguration is visible."""
    import logging

    with caplog.at_level(logging.INFO, logger=rl.logger.name):
        _limited_app(trust_proxy=True)
    assert any(
        rec.message == "rate limit: trust_proxy=%s" and rec.args == (True,)
        or rec.getMessage() == "rate limit: trust_proxy=True"
        for rec in caplog.records
    )
