#!/usr/bin/env python3
"""WP5: turn seed_open_source.json into the files each service needs.

Writes under data/open/ with the SAME file names/shapes the legacy profile uses
(see docs/data-schemas.md, read from the Rust/Python source):

  seed_all_tunisia_routes.tagged.json   (transit service)
  transport_map_corrected.json          (routing service)

This script does NOT switch any service to the open files. The DATA_PROFILE
switch is wired separately, and the default stays `legacy`.

Usage: python scripts/open_pipeline.py [--source data/seed_open_source.json]
                                       [--out-dir data/open]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO / "data" / "seed_open_source.json"
DEFAULT_OUT = REPO / "data" / "open"


def convert(seed: dict) -> tuple[dict, dict]:
    """Return (tagged seed, transport map) in the exact shapes services read."""
    raw_stations = seed.get("stations", [])
    raw_lines = seed.get("lines", [])
    meta = seed.get("metadata", {})

    stations = []
    for s in raw_stations:
        stations.append({
            "id": s["id"],
            "name": s.get("name") or s.get("name_fr") or s["id"],
            "name_ar": s.get("name_ar", ""),
            "name_fr": s.get("name_fr", ""),
            "name_en": s.get("name_en", ""),
            "lat": s.get("lat"), "lon": s.get("lon"),
            "mode": s.get("mode", "bus"),
            "operator": s.get("operator", ""),
            "source": s.get("source", "osm"),
            "license_status": s.get("license_status", "odbl"),
            "lines_served": s.get("lines_served", []),
        })

    lines = []
    for ln in raw_lines:
        stops = ln.get("stops") or []
        lines.append({
            "id": ln["id"],
            "name": ln.get("name") or ln["id"],
            "number": ln.get("number") or "",
            "mode": ln.get("mode", "bus"),
            "operator": ln.get("operator", ""),
            "stations": stops,           # Rust graph.rs reads `stations`
            "license_status": ln.get("license_status", "odbl"),
            "source": ln.get("source", "osm"),
        })

    tagged = {
        "metadata": {
            "source": meta.get("source", "OpenStreetMap (ODbL)"),
            "license": "ODbL — attribution required",
            "profile": "open",
            "osm3s_timestamp_osm_base": meta.get("osm3s_timestamp_osm_base"),
        },
        "stations": stations,
        "lines": lines,
    }
    # Flat form; Rust MapFile accepts {stations, lines} directly.
    transport_map = {
        "by_mode": {},
        "stations": stations,
        "lines": lines,
    }
    return tagged, transport_map


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    if not args.source.is_file():
        print(f"ERROR: open seed not found: {args.source}")
        return 2
    seed = json.loads(args.source.read_text(encoding="utf-8"))
    tagged, tmap = convert(seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "seed_all_tunisia_routes.tagged.json").write_text(
        json.dumps(tagged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / "transport_map_corrected.json").write_text(
        json.dumps(tmap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(tagged['stations'])} stations, {len(tagged['lines'])} lines to {args.out_dir}")
    print("The default profile remains legacy; nothing is switched by this script.")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
