#!/usr/bin/env python3
"""Build the rail and road overlays the map draws behind the stations.

Sources (Downloads/tunisia-transport-data):
  02-rail-metro-tgm/rail-network-exports/export.geojson
      railway=rail (main lines) and railway=light_rail (Tunis metro).
      Disused/abandoned/yard/spur are excluded — they are not passenger routes.
  03-roads/highways/export .geojson
      motorway/trunk/primary, which is the intercity network a rider recognises.
      Secondary and tertiary are left out: 16k more ways that add visual noise
      without telling a rider anything about how to get between cities.

Highways arrive with 721,891 vertices. They are simplified (Douglas-Peucker,
~15 m) and rounded to 5 decimals, which is the difference between a 60 MB
overlay the browser cannot load and one it can.

    python tool/build_map_overlays.py
"""

from __future__ import annotations
from pathlib import Path

import json

ROOT = Path(__file__).resolve().parents[1]
DUMP = (Path.home() / "Downloads" / "TunisiaTransport")
RAIL_SRC = DUMP / "02-rail-metro-tgm" / "rail-network-exports" / "export.geojson"
ROAD_SRC = DUMP / "03-roads" / "highways" / "export .geojson"

RAIL_OUT = ROOT / "data" / "map_rail.geojson"
ROAD_OUT = ROOT / "data" / "map_roads.geojson"

# Passenger rail only.
RAIL_KEEP = {"rail", "light_rail", "subway", "tram"}
RAIL_DROP_SERVICE = {"yard", "spur", "siding", "crossover"}

# The intercity road network.
ROAD_KEEP = {"motorway", "trunk", "primary"}

TOLERANCE = 0.00015  # ~16 m; invisible at country zoom, kills most vertices


def dp(points: list[list[float]], tol: float) -> list[list[float]]:
    """Douglas-Peucker line simplification (iterative, no recursion limit)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        ax, ay = points[first]
        bx, by = points[last]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5
        best_i, best_d = -1, -1.0
        for i in range(first + 1, last):
            px, py = points[i]
            if norm == 0:
                d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            else:
                d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if d > best_d:
                best_i, best_d = i, d
        if best_d > tol:
            keep[best_i] = True
            stack.append((first, best_i))
            stack.append((best_i, last))
    return [p for p, k in zip(points, keep) if k]


def round_coords(coords, nd=5):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], nd), round(coords[1], nd)]
    return [round_coords(c, nd) for c in coords]


def build_rail() -> dict:
    src = json.loads(RAIL_SRC.read_text(encoding="utf-8", errors="replace"))
    feats = []
    stats = {"rail": 0, "light_rail": 0, "skipped": 0}
    for f in src.get("features", []):
        p = f.get("properties") or {}
        rw = p.get("railway")
        if rw not in RAIL_KEEP:
            stats["skipped"] += 1
            continue
        if (p.get("service") or "") in RAIL_DROP_SERVICE:
            stats["skipped"] += 1
            continue
        g = f.get("geometry") or {}
        if g.get("type") not in ("LineString", "MultiLineString"):
            stats["skipped"] += 1
            continue
        lines = ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"])
        for line in lines:
            if len(line) < 2:
                continue
            mode = "metro" if rw in ("light_rail", "subway", "tram") else "train"
            feats.append({
                "type": "Feature",
                "properties": {
                    "mode": mode,
                    "railway": rw,
                    "name": p.get("name:fr") or p.get("name") or "",
                    "ref": p.get("ref") or "",
                    "operator": p.get("operator:fr") or p.get("operator") or "",
                    "electrified": p.get("electrified") or "",
                },
                "geometry": {"type": "LineString",
                             "coordinates": [round_coords(c) for c in line]},
            })
            stats["light_rail" if mode == "metro" else "rail"] += 1
    out = {
        "type": "FeatureCollection",
        "metadata": {
            "source": "OpenStreetMap via Overpass (rail-network-exports/export.geojson)",
            "license": "ODbL",
            "note": ("Passenger rail and light rail. Disused, abandoned, yard, spur "
                     "and siding track is excluded. mode=metro for light_rail, "
                     "mode=train for rail."),
            "counts": stats,
        },
        "features": feats,
    }
    return out


def build_roads() -> dict:
    src = json.loads(ROAD_SRC.read_text(encoding="utf-8", errors="replace"))
    feats = []
    stats: dict[str, int] = {}
    v_before = v_after = 0
    for f in src.get("features", []):
        p = f.get("properties") or {}
        hw = p.get("highway")
        if hw not in ROAD_KEEP:
            continue
        g = f.get("geometry") or {}
        if g.get("type") != "LineString":
            continue
        line = g.get("coordinates") or []
        if len(line) < 2:
            continue
        v_before += len(line)
        simp = dp(line, TOLERANCE)
        if len(simp) < 2:
            simp = [line[0], line[-1]]
        v_after += len(simp)
        stats[hw] = stats.get(hw, 0) + 1
        feats.append({
            "type": "Feature",
            "properties": {
                "highway": hw,
                "ref": p.get("ref") or p.get("ref:fr") or "",
                "name": p.get("name:fr") or p.get("name") or "",
                "lanes": p.get("lanes") or "",
                "oneway": p.get("oneway") or "",
            },
            "geometry": {"type": "LineString",
                         "coordinates": [round_coords(c) for c in simp]},
        })
    out = {
        "type": "FeatureCollection",
        "metadata": {
            "source": "OpenStreetMap via Overpass (highways/export .geojson)",
            "license": "ODbL",
            "note": ("Intercity roads: motorway, trunk and primary only. Secondary "
                     "and tertiary are omitted as visual noise. Simplified with "
                     "Douglas-Peucker at 0.00015 deg (~16 m)."),
            "counts": stats,
            "vertices_before": v_before,
            "vertices_after": v_after,
            "tolerance_deg": TOLERANCE,
        },
        "features": feats,
    }
    return out


rail = build_rail()
RAIL_OUT.write_text(json.dumps(rail, ensure_ascii=False), encoding="utf-8")
print(f"rail  -> {RAIL_OUT.name}  {RAIL_OUT.stat().st_size/1e6:.2f} MB  "
      f"{len(rail['features'])} lines  {rail['metadata']['counts']}")

roads = build_roads()
ROAD_OUT.write_text(json.dumps(roads, ensure_ascii=False), encoding="utf-8")
m = roads["metadata"]
print(f"roads -> {ROAD_OUT.name}  {ROAD_OUT.stat().st_size/1e6:.2f} MB  "
      f"{len(roads['features'])} lines  {m['counts']}")
print(f"        vertices {m['vertices_before']:,} -> {m['vertices_after']:,} "
      f"({100*m['vertices_after']/max(1,m['vertices_before']):.1f}%)")
