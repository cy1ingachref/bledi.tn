#!/usr/bin/env python3
"""Fetch a reproducible OSM public-transport export from Overpass.

Owner decision 1: rebuild routing data from open sources. This script is the
fetch half. It does NOT commit the raw export — the export is gitignored and
this script writes a small, committed manifest describing exactly what was
fetched so a rebuild can be reproduced.

Usage:
    python scripts/fetch_osm_export.py [--output data/osm_overpass/tunisia_pt.json]
                                       [--manifest data/osm_overpass/manifest.json]

Behaviour:
- One Overpass request per invocation; no cell splitting (see transport-data-
  sourcing skill: fine-grained queries get rate-limited).
- Area selected by ISO 3166-1 code (TN), not by the fragile name "Tunisie".
- Fetches route_master relations and recurses with `>;` so way platforms and
  route members are included.
- Tries the Kumi and main Overpass endpoints in order with a User-Agent.
- Records the query, fetch date, `osm3s.timestamp_osm_base`, element counts and
  the export's SHA-256 in the manifest. Manifest is written only after a
  successful fetch.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
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
USER_AGENT = "bledi.tn-open-data-cutover/1.0 (OSM ODbL rebuild; contact: repo owner)"

# ISO-code area selection + route_master + way platforms via `>;`.
QUERY = """[out:json][timeout:600];
area["ISO3166-1"="TN"][admin_level=2]->.a;
(
  node(area.a)["public_transport"];
  node(area.a)["highway"="bus_stop"];
  node(area.a)["railway"];
  node(area.a)["amenity"="bus_station"];
  node(area.a)["amenity"="ferry_terminal"];
  relation(area.a)["type"="route"];
  relation(area.a)["type"="route_master"];
);
out body;
>;
out skel qt;"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def element_counts(payload: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for el in payload.get("elements", []):
        kind = el.get("type", "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def make_manifest(payload: dict, raw: bytes, output: Path) -> dict:
    osm_base = (payload.get("osm3s") or {}).get("timestamp_osm_base", "")
    return {
        "query": QUERY,
        "endpoints_tried": list(ENDPOINTS),
        "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "osm3s_timestamp_osm_base": osm_base,
        "element_counts": element_counts(payload),
        "export_sha256": sha256_bytes(raw),
        "export_path": str(output.relative_to(REPO)) if output.is_relative_to(REPO) else str(output),
        "license": "ODbL — attribution required",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = ap.parse_args()

    last_error: Exception | None = None
    raw: bytes | None = None
    payload: dict | None = None
    for endpoint in ENDPOINTS:
        try:
            print(f"fetching from {endpoint} ...", file=sys.stderr)
            body = urllib.parse.urlencode({"data": QUERY}).encode("utf-8")
            req = urllib.request.Request(
                endpoint, data=body,
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=660) as resp:
                raw = resp.read()
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict) or "elements" not in payload:
                raise ValueError("unexpected Overpass response (no elements)")
            break
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            print(f"  failed: {exc}", file=sys.stderr)
    if payload is None or raw is None:
        print(f"ERROR: all Overpass endpoints failed: {last_error}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    manifest = make_manifest(payload, raw, args.output)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(raw):,} bytes)")
    print(f"wrote {args.manifest}")
    print(f"elements: {manifest['element_counts']}; OSM base: {manifest['osm3s_timestamp_osm_base']}")
    print("The raw export is gitignored; do not commit it. Publish it as a release asset if needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
