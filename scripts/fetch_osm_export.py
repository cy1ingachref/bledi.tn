#!/usr/bin/env python3
"""Fetch a reproducible OSM public-transport export from Overpass.

The Overpass query lives in scripts/overpass_query.ql (single source of truth),
read by both the live fetch and the manifest.

Usage:
    OVERPASS_CONTACT=you@example.com python scripts/fetch_osm_export.py
        [--output data/osm_overpass/tunisia_pt.json]
        [--manifest data/osm_overpass/manifest.json]
        [--query-file scripts/overpass_query.ql]

Import an export produced manually in Overpass Turbo (no network):
    python scripts/fetch_osm_export.py --from-file PATH [--query-file PATH]

Both paths validate with the SAME checks (error remark, osm3s timestamp,
minimum stop nodes and route relations). A manifest is written ONLY after a
successful fetch/import — never otherwise. The raw export is gitignored and
must not be committed.

Hardening:
- HTTP 200 with an error remark and a partial/empty payload is a failure.
- Minimum stop-node / route-relation counts catch truncated responses.
- One retry with backoff on 429/502/503/504 (respecting Retry-After), then the
  next endpoint. OVERPASS_ENDPOINTS (comma-separated) overrides/extends the
  default endpoint list.
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
DEFAULT_QUERY_FILE = REPO / "scripts" / "overpass_query.ql"

DEFAULT_ENDPOINTS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
APP_NAME = "bledi.tn-open-data-cutover/1.0"
MIN_STOP_NODES = 50
MIN_ROUTE_RELATIONS = 10
ERROR_REMARK_RE = re.compile(r"\b(error|timed?\s*out|timeout|out of memory|oom|runtime error)\b", re.I)
RETRYABLE_STATUS = {429, 502, 503, 504}


class FetchError(Exception):
    """A network/HTTP failure from one endpoint."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def load_query(query_file: Path) -> str:
    """Read the Overpass QL from the single source-of-truth file."""
    text = query_file.read_text(encoding="utf-8").strip()
    if not text or "[out:" not in text:
        raise ValueError(f"{query_file} does not look like an Overpass query")
    return text


def endpoints_from_env() -> tuple[str, ...]:
    """OVERPASS_ENDPOINTS overrides the defaults when set, else defaults."""
    raw = os.environ.get("OVERPASS_ENDPOINTS", "").strip()
    if not raw:
        return DEFAULT_ENDPOINTS
    parts = tuple(p.strip() for p in raw.split(",") if p.strip())
    if not parts or any(not p.startswith(("http://", "https://")) for p in parts):
        raise ValueError("OVERPASS_ENDPOINTS must be comma-separated http(s) URLs")
    return parts


def user_agent_from_env() -> str:
    contact = os.environ.get("OVERPASS_CONTACT", "").strip()
    if not contact:
        raise RuntimeError(
            "OVERPASS_CONTACT is not set. Set it to a contact email, e.g. "
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
    """Reject error remarks, missing timestamp, and payloads below the floors.

    Returns counts (including stop_nodes / route_relations) for the manifest.
    Accepts either Overpass JSON (`elements` + `osm3s`) or an Overpass Turbo
    GeoJSON export (`features` + `timestamp`, with @relations on properties).
    """
    if not isinstance(payload, dict):
        raise ValueError("unexpected Overpass response shape")
    remark = payload.get("remark")
    if remark and ERROR_REMARK_RE.search(str(remark)):
        raise ValueError(f"Overpass returned an error remark: {remark!r}")

    if isinstance(payload.get("elements"), list):
        counts = element_counts(payload)
        if not (payload.get("osm3s") or {}).get("timestamp_osm_base"):
            raise ValueError("missing osm3s.timestamp_osm_base")
        els = payload["elements"]
        stop_nodes = sum(1 for e in els if e.get("type") == "node" and _is_stop_node(e))
        route_relations = sum(1 for e in els if e.get("type") == "relation" and _is_route_relation(e))
        counts["node"] = sum(1 for e in els if e.get("type") == "node")
        counts["relation"] = sum(1 for e in els if e.get("type") == "relation")
    elif isinstance(payload.get("features"), list):
        # Overpass Turbo GeoJSON: tags are flat on properties and member
        # relations are listed as @relations [{rel, reltags}]; no osm3s block.
        if not payload.get("timestamp"):
            raise ValueError("missing timestamp (GeoJSON export)")
        counts = {"node": 0, "relation": 0}
        stop_nodes = 0
        route_ids: set[int] = set()
        for f in payload["features"]:
            props = f.get("properties") or {}
            if any(k in props for k in ("public_transport", "highway", "railway", "amenity")) or props.get("bus") == "yes":
                stop_nodes += 1
            counts["node"] += 1
            for r in props.get("@relations") or []:
                if (r.get("reltags") or {}).get("type") == "route":
                    route_ids.add(r.get("rel"))
        route_relations = len(route_ids)
        counts["relation"] = route_relations
    else:
        raise ValueError("unexpected Overpass response (no elements or features list)")

    if stop_nodes < MIN_STOP_NODES:
        raise ValueError(f"too few stop nodes: {stop_nodes} (need >= {MIN_STOP_NODES})")
    if route_relations < MIN_ROUTE_RELATIONS:
        raise ValueError(f"too few route relations: {route_relations} (need >= {MIN_ROUTE_RELATIONS})")
    counts["stop_nodes"] = stop_nodes
    counts["route_relations"] = route_relations
    return counts


def osm_base_timestamp(payload: dict) -> str:
    osm3s = payload.get("osm3s") or {}
    return str(osm3s.get("timestamp_osm_base") or payload.get("timestamp") or "")


def is_retryable(status: int | None) -> bool:
    return status in RETRYABLE_STATUS


def retry_delay(response, attempt: int) -> float:
    headers = getattr(response, "headers", {}) or {}
    raw = headers.get("Retry-After")
    if raw:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
    return float(2 ** attempt)


def _fetch_once(endpoint: str, user_agent: str, query: str) -> bytes:
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=body,
        headers={"User-Agent": user_agent, "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=660) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code}", status=exc.code) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise FetchError(str(exc)) from exc


def fetch_payload(user_agent: str, *, query: str, endpoints=None, fetchers=None):
    """Try each endpoint; on a retryable status do one retry, then move on."""
    eps = tuple(endpoints) if endpoints else endpoints_from_env()
    last_error: Exception | None = None
    for i, endpoint in enumerate(eps):
        fetcher = fetchers[i] if fetchers else _fetch_once
        for attempt in range(2):
            try:
                raw = fetcher(endpoint, user_agent, query) if fetchers else _fetch_once(endpoint, user_agent, query)
                payload = json.loads(raw.decode("utf-8"))
                counts = validate_payload(payload)
                return raw, payload, counts, endpoint
            except ValueError as exc:
                last_error = exc
                print(f"  invalid payload from {endpoint}: {exc}", file=sys.stderr)
                break
            except FetchError as exc:
                last_error = exc
                if is_retryable(exc.status) and attempt == 0:
                    delay = retry_delay(exc, attempt)
                    print(f"  {exc.status} from {endpoint}; retrying in {delay:g}s", file=sys.stderr)
                    time.sleep(delay)
                    continue
                print(f"  failed at {endpoint}: {exc}", file=sys.stderr)
                break
    raise FetchError(f"all Overpass endpoints failed: {last_error}")


def make_manifest(payload: dict, raw: bytes, output: Path, *, counts: dict,
                  query: str, endpoint: str, source: str = "overpass-api") -> dict:
    return {
        "source": source,
        "query": query,
        "endpoint_used": endpoint,
        "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "osm3s_timestamp_osm_base": osm_base_timestamp(payload),
        "element_counts": counts,
        "export_sha256": sha256_bytes(raw),
        "export_path": str(output.relative_to(REPO)) if output.is_relative_to(REPO) else str(output),
        "license": "ODbL — attribution required",
    }


def main(argv=None, *, fetchers=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    ap.add_argument("--from-file", type=Path, default=None,
                    help="validate an existing export and write the manifest (no network)")
    args = ap.parse_args(argv)

    try:
        query = load_query(args.query_file)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.from_file is not None:
        try:
            raw = args.from_file.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
            counts = validate_payload(payload)  # SAME checks as live fetch
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            print(f"ERROR: {args.from_file} failed validation: {exc}", file=sys.stderr)
            return 2  # no manifest written
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
        manifest = make_manifest(payload, raw, args.output, counts=counts,
                                 query=query, endpoint="", source="manual overpass-turbo")
        args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"validated {args.from_file} ({len(raw):,} bytes)")
        print(f"wrote {args.output} and {args.manifest}")
        print(f"elements: {counts}; OSM base: {manifest['osm3s_timestamp_osm_base']}")
        print("The raw export is gitignored; do not commit it.")
        return 0

    try:
        user_agent = user_agent_from_env()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    try:
        raw, payload, counts, endpoint = fetch_payload(user_agent, query=query, fetchers=fetchers)
    except (FetchError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    manifest = make_manifest(payload, raw, args.output, counts=counts, query=query, endpoint=endpoint)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(raw):,} bytes) and {args.manifest}")
    print(f"elements: {counts}; OSM base: {manifest['osm3s_timestamp_osm_base']}")
    print("The raw export is gitignored; do not commit it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
