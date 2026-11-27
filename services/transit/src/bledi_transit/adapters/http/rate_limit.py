"""Per-IP rate limiting for the transit API.

The web gateway is the first line of defence (nginx `limit_req` keyed on the
real client address). This middleware is a backstop for direct access and for
deployments without the gateway.

Security notes (H1 in bledi-fixes-handoff.md):
- `X-Forwarded-For` is client-controlled. It is used ONLY when
  `TRUST_PROXY_HEADERS=1`, and even then only the first entry is taken — the
  gateway overwrites that header, so a client cannot pick its own bucket.
- Idle buckets are deleted, not left in the dict forever.
- Health endpoints are exempt so container healthchecks never consume budget.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

RATE_LIMIT_REQUESTS = 60  # requests per window
RATE_LIMIT_WINDOW = 60  # seconds
HEALTH_PATHS = frozenset({"/health", "/api/v1/health"})


def trust_proxy_headers() -> bool:
    """Only trust XFF when explicitly enabled (mirrors the accounts service)."""
    value = os.environ.get("TRUST_PROXY_HEADERS", "")
    return value == "1" or value.lower() == "true"


def client_key(request: Request, trust_proxy: bool | None = None) -> str:
    """Return the bucket key for a request.

    Without a trusted proxy, the socket peer is the only safe identity. Behind
    nginx (TRUST_PROXY_HEADERS=1), the first XFF entry is the real client,
    because the gateway overwrites the header rather than appending to it.
    """
    if trust_proxy is None:
        trust_proxy = trust_proxy_headers()
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def prune_buckets(buckets: dict[str, deque[float]], now: float, window: float) -> None:
    """Drop expired timestamps and delete keys with no remaining budget use."""
    for key in list(buckets):
        bucket = buckets[key]
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        if not bucket:
            del buckets[key]


def install_rate_limit(app: FastAPI, *, limit: int = RATE_LIMIT_REQUESTS,
                       window: float = RATE_LIMIT_WINDOW,
                       trust_proxy: bool | None = None) -> None:
    """Install the per-IP backstop middleware on an app."""
    if trust_proxy is None:
        trust_proxy = trust_proxy_headers()
    # Log once so a misconfiguration (everyone pooled behind the gateway) is
    # visible in `docker compose logs transit`.
    logger.info("rate limit: trust_proxy=%s", trust_proxy)
    buckets: dict[str, deque[float]] = defaultdict(deque)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.url.path in HEALTH_PATHS:
            return await call_next(request)
        key = client_key(request, trust_proxy)
        now = time.monotonic()
        prune_buckets(buckets, now, window)
        bucket = buckets[key]
        if len(bucket) >= limit:
            return JSONResponse(
                {"error": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(int(window))},
            )
        bucket.append(now)
        return await call_next(request)
