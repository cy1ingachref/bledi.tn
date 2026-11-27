#!/usr/bin/env python3
"""Inspect the rail and highway exports before building map geometry.

    python tool/inspect_geometry_sources.py
"""

from __future__ import annotations
from pathlib import Path

import collections
import json

DUMP = (Path.home() / "Downloads" / "TunisiaTransport")

FILES = [
    DUMP / "02-rail-metro-tgm" / "rail-network-exports" / "export.geojson",
    DUMP / "02-rail-metro-tgm" / "rail-map-exports" / "export.geojson",
    DUMP / "02-rail-metro-tgm" / "rail-map-exports" / "metro and train" / "export.geojson",
    DUMP / "03-roads" / "highways" / "export .geojson",
]

for p in FILES:
    if not p.is_file():
        print(f"MISSING {p}")
        continue
    print("=" * 92)
    print(f"### {p.relative_to(DUMP)}  ({p.stat().st_size/1e6:.1f} MB)")
    try:
        d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        print(f"  parse error: {type(e).__name__}: {e}")
        continue
    feats = d.get("features", [])
    print(f"  features: {len(feats)}")
    if not feats:
        continue
    # What geometry types and what tags?
    geoms = collections.Counter()
    kinds = collections.Counter()
    refs = collections.Counter()
    for f in feats:
        g = f.get("geometry") or {}
        geoms[g.get("type")] += 1
        props = f.get("properties") or {}
        for key in ("railway", "highway", "route", "type", "service", "usage"):
            if props.get(key):
                kinds[f"{key}={props[key]}"] += 1
        if props.get("ref"):
            refs[str(props["ref"])] += 1
    print(f"  geometry types: {geoms.most_common()}")
    print(f"  top tags: {kinds.most_common(18)}")
    print(f"  refs (top 20): {refs.most_common(20)}")
    print(f"  sample properties: {json.dumps((feats[0].get('properties') or {}), ensure_ascii=False)[:300]}")
    # Total vertex count, to size the simplification job.
    n = 0
    for f in feats:
        g = f.get("geometry") or {}
        if g.get("type") == "LineString":
            n += len(g.get("coordinates") or [])
        elif g.get("type") == "MultiLineString":
            n += sum(len(c) for c in (g.get("coordinates") or []))
    print(f"  total vertices: {n:,}")
