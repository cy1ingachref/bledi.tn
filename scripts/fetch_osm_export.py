#!/usr/bin/env python3
"""Fetch a reproducible OSM public-transport export from Overpass.

Owner decision 1: rebuild routing data from open sources. This script is the
fetch half. It does NOT commit the raw export — the export is gitignored and
this script writes a small, committed manifest describing exactly what was
fetched so a rebuild can be reproduced.

Usage:
    OVERPASS_CONTACT=you@example.com python scripts/fetch_osm_export.py
        [--output data/osm_overpass/tunisia_pt.json]
        [--manifest data/osm_overpass/manifest.json]

Hardening (STEP 1):
- Overpass can return HTTP 200 with an error remark and a partial/empty payload:
  a remark matching error/timeout/out-of-memory is treated as a failure.
- Minimum stop-node and route-relation counts are required before anything is
  written. They are deliberately low (see MIN_* constants) — enough to catch a
  truncated/empty response without asserting a particular OSM coverage level.
- node["railway"] is narrowed to station-type values, not all railway nodes.
- The User-Agent contact comes from OVERPASS_CONTACT (required, clear failure).
- One retry with backoff on 429/504 (respecting Retry-After) per endpoint.
- The manifest is written only after a fully successful fetch and validation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / "data" / "osm_overpass" / "tunisia_pt.json"
DEFAULT_MANIFEST = REPO / "data" / "osm_overpass" / "manifest.json"

ENDPOINTS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
APP_NAME = "bledi.tn-open-data-cutover/1.0"
# Deliberately conservative floors: catch an empty/truncated response, not a
# claim about Tunisia's coverage (the real export has thousands of each).
MIN_STOP_NODES = 50
MIN_ROUTE_RELATIONS = 10
ERROR_REMARK_RE = re.compile(r"\b(error|timed?\s*out|timeout|out of memory|oom|runtime error)\b", re.I)
RETRYABLE_STATUS = {429, 504}

# ISO-code area selection + route_master + station-type railway nodes + way platforms.
QUERY = """[out:json][timeout:600];
area["ISO3166-1"="TN"][admin_level=2]->.a;
(
  node(area.a)["public_transport"];
  node(area.a)["highway"="bus_stop"];
  node(area.a)["railway"="station"];
  node(area.a)["railway"="halt"];
  node(area.a)["railway"="tram_stop"];
  node(area.a)["railway"="stop"];
  node(area.a)["railway"="platform"];
  node(area.a)["amenity"="bus_station"];
  node(area.a)["amenity"="ferry_terminal"];
  relation(area.a)["type"="route"];
  relation(area.a)["type"="route_master"];
);
out body;
>;
out skel qt;"""


class FetchError(Exception):
    """A network/HTTP failure from one endpoint."""


def user_agent_from_env() -> str:
    contact = os.environ.get("OVERPASS_CONTACT", "").strip()
    if not contact:
        raise RuntimeError(
            "OVERPASS_CONTACT is not set. Overpass requires a identifiable "
            "User-Agent; set it to a contact email, e.g. "
            "OVERPASS_CONTACT=maintainer@example.com"
        )
    return f"{APP_NAME} (OSM ODbL rebuild; contact: {contact})"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def element_counts(payload: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for el in payload.get("elements", []):
        kind = el.get("type", "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _is_stop_node(el: dict) -> bool:
    tags = el.get("tags") or {}
    return any(k in tags for k in ("public_transport", "highway", "railway", "amenity")) or tags.get("bus") == "yes"


def _is_route_relation(el: dict) -> bool:
    return (el.get("tags") or {}).get("type") == "route"


def validate_payload(payload: dict) -> dict[str, int]:
    """Reject error remarks and payloads below the minimum counts.

    Returns a dict with stop_nodes / route_relations counts (plus all element
    counts) for the manifest.
    """
    if not isinstance(payload, dict):
        raise ValueError("unexpected Overpass response shape")
    remark = payload.get("remark")
    if remark and ERROR_REMARK_RE.search(str(remark)):
        raise ValueError(f"Overpass returned an error remark: {remark!r}")
    if "elements" not in payload or not isinstance(payload["elements"], list):
        raise ValueError("unexpected Overpass response (no elements list)")
    counts = element_counts(payload)
    els = payload["elements"]
    stop_nodes = sum(1 for e in els if e.get("type") == "node" and _is_stop_node(e))
    route_relations = sum(1 for e in els if e.get("type") == "relation" and _is_route_relation(e))
    if stop_nodes < MIN_STOP_NODES:
        raise ValueError(f"too few stop nodes: {stop_nodes} (need >= {MIN_STOP_NODES})")
    if route_relations < MIN_ROUTE_RELATIONS:
        raise ValueError(f"too few route relations: {route_relations} (need >= {MIN_ROUTE_RELATIONS})")
    counts["stop_nodes"] = stop_nodes
    counts["route_relations"] = route_relations
    return counts


def is_retryable(status: int) -> bool:
    return status in RETRYABLE_STATUS


def retry_delay(response, attempt: int) -> float:
    """Respect Retry-After when present; otherwise exponential backoff."""
    headers = getattr(response, "headers", {}) or {}
    raw = headers.get("Retry-After")
    if raw:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
    return float(2 ** attempt)


def _fetch_once(endpoint: str, user_agent: str) -> bytes:
    body = urllib.parse.urlencode({"data": QUERY}).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=body,
        headers={"User-Agent": user_agent, "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=660) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        setattr(exc, "status", exc.code)
        raise FetchError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise FetchError(str(exc)) from exc


def fetch_payload(user_agent: str, *, fetchers=None):
    """Try each endpoint; on 429/504 do one retry with backoff, then move on."""
    last_error: Exception | None = None
    for endpoint in ENDPOINTS:
        fetcher = fetchers[ENDPOINTS.index(endpoint)] if fetchers else _fetch_once
        for attempt in range(2):
            try:
                raw = fetcher(endpoint, user_agent)
                payload = json.loads(raw.decode("utf-8"))
                counts = validate_payload(payload)  # may raise ValueError
                return raw, payload, counts, endpoint
            except ValueError as exc:
                # Bad/partial payload is not retryable on the same endpoint.
                last_error = exc
                print(f"  invalid payload from {endpoint}: {exc}", file=sys.stderr)
                break
            except FetchError as exc:
                last_error = exc
                status = getattr(exc, "status", None)
                if is_retryable(status) and attempt == 0:
                    delay = retry_delay(exc, attempt)
                    print(f"  {status} from {endpoint}; retrying in {delay:g}s", file=sys.stderr)
                    time.sleep(delay)
                    continue
                print(f"  failed at {endpoint}: {exc}", file=sys.stderr)
                break
    raise FetchError(f"all Overpass endpoints failed: {last_error}")


def make_manifest(payload: dict, raw: bytes, output: Path, *, counts: dict | None = None,
                  endpoint: str | None = None) -> dict:
    osm_base = (payload.get("osm3s") or {}).get("timestamp_osm_base", "")
    return {
        "query": QUERY,
        "endpoint_used": endpoint or "",
        "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "osm3s_timestamp_osm_base": osm_base,
        "element_counts": counts or element_counts(payload),
        "export_sha256": sha256_bytes(raw),
        "export_path": str(output.relative_to(REPO)) if output.is_relative_to(REPO) else str(output),
        "license": "ODbL — attribution required",
    }


def main(argv=None, *, fetchers=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = ap.parse_args(argv)

    try:
        user_agent = user_agent_from_env()  # required before any request
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        raw, payload, counts, endpoint = fetch_payload(user_agent, fetchers=fetchers)
    except FetchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    manifest = make_manifest(payload, raw, args.output, counts=counts, endpoint=endpoint)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(raw):,} bytes)")
    print(f"wrote {args.manifest}")
    print(f"elements: {counts}; OSM base: {manifest['osm3s_timestamp_osm_base']}")
    print("The raw export is gitignored; do not commit it. Publish it as a release asset if needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
