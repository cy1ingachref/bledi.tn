"""H1 regression tests: per-IP rate limiting and trust boundaries."""
from __future__ import annotations

import time
from collections import deque

from fastapi import FastAPI
from fastapi.testclient import TestClient

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


def _limited_app(*, trust_proxy: bool) -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/route/plan")
    def route_plan():
        return {"ok": True}

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    install_rate_limit(app, limit=2, window=60, trust_proxy=trust_proxy)
    return app


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
