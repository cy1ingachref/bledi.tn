#!/usr/bin/env python3
"""Audit saved /route/plan responses for the defects that make a route look wrong.

    python services/transit/tools/audit_response.py real/route-*.json
    python services/transit/tools/audit_response.py --water data/water_polys.json real/*.json

Flags, per itinerary leg:
  WALK        a walking leg over 2.2 km, or a walk whose path is >1.8x its straight line
  CHORD       one straight segment over 8 km on a road leg (a collapsed polyline)
  SPEED       an implied speed outside the plausible band for the mode
  NO-GEOM     a leg over 300 m with no polyline
  WATER       more than 0.8 km of the leg inside sea / lake (needs --water and shapely;
              rail causeways and bridges show up here too, so read the mode)
  JUMP        the next leg starts more than 150 m from where this one ended
Exit status is 1 when any flag is raised, so it can gate CI.
"""
from __future__ import annotations

import argparse
import json
import math
import sys

BAND_KMH = {"walk": (3.0, 6.0), "metro": (15, 45), "tram": (10, 40), "train": (35, 110),
            "bus": (10, 90), "louaj": (90, 120), "taxi": (25, 110)}


def hav(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(min(1.0, h)))


def load_water(path):
    try:
        from shapely.geometry import Point, Polygon
        from shapely.ops import unary_union
        from shapely.prepared import prep
    except ImportError:
        print("shapely not installed: skipping the water check", file=sys.stderr)
        return None
    land, lakes = [], []
    for el in json.load(open(path, encoding="utf-8"))["elements"]:
        name = el.get("tags", {}).get("name", "")
        g = el.get("geometry") or []
        if len(g) < 4:
            continue
        poly = Polygon([(p["lon"], p["lat"]) for p in g]).buffer(0)
        (land if name.startswith(("GSHHG L1", "GSHHG L3")) else lakes if name.startswith("GSHHG L2") else []).append(poly)
    L, K = prep(unary_union(land)), (prep(unary_union(lakes)) if lakes else None)
    return lambda lat, lon: (not L.contains(Point(lon, lat))) or bool(K and K.contains(Point(lon, lat)))


def water_m(geom, is_water, step=60.0):
    tot = 0.0
    for a, b in zip(geom, geom[1:]):
        d = hav(a, b)
        n = max(1, int(d // step))
        for i in range(n):
            t = i / n
            if is_water(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t):
                tot += d / n
    return tot


def audit(path, is_water):
    data = json.load(open(path, encoding="utf-8"))
    flags = 0
    print(f"== {path}")
    for it in data.get("itineraries", []):
        legs = it.get("legs") or it.get("steps") or []
        issues = []
        for i, l in enumerate(legs):
            mode = l.get("mode") or l.get("type")
            g = l.get("geometry") or []
            dist = float(l.get("distance_m") or 0)
            where = f"leg{i} {mode} {l.get('from_name') or ''}->{l.get('to_name') or ''}"
            if l.get("type") == "walk":
                straight = l.get("straight_m") or (hav([l["from"]["lat"], l["from"]["lon"]], [l["to"]["lat"], l["to"]["lon"]]) if l.get("from") and l.get("to") else 0)
                if dist > 2200 or (straight and dist > 1.8 * straight + 400):
                    issues.append(f"WALK    {where}: {dist / 1000:.1f} km (straight {straight / 1000:.1f} km)")
            if len(g) >= 2:
                chord = max(hav(a, b) for a, b in zip(g, g[1:]))
                if chord > 8000 and mode in ("taxi", "louaj", "bus", "walk"):
                    issues.append(f"CHORD   {where}: {chord / 1000:.1f} km straight segment in {len(g)} points")
                if is_water:
                    w = water_m(g, is_water)
                    if w > 800:
                        issues.append(f"WATER   {where}: {w / 1000:.2f} km in water")
            elif dist >= 300 and mode in ("ride", "metro", "train", "bus", "louaj", "taxi", "walk"):
                issues.append(f"NO-GEOM {where}: {dist:.0f} m without a polyline")
            t = float(l.get("time_seconds") or 0) - float(l.get("wait_min") or 0) * 60
            band = BAND_KMH.get(mode)
            if band and dist > 2000 and t > 0:
                kmh = dist / 1000 / (t / 3600)
                if not band[0] <= kmh <= band[1]:
                    issues.append(f"SPEED   {where}: {kmh:.0f} km/h (expected {band[0]}-{band[1]})")
            if i + 1 < len(legs):
                nxt = legs[i + 1].get("geometry") or []
                if g and nxt and hav(g[-1], nxt[0]) > 150:
                    issues.append(f"JUMP    {where}: next leg starts {hav(g[-1], nxt[0]):.0f} m away")
        flags += len(issues)
        print(f"  {it.get('id')} {it.get('label')}  [{len(issues)} issue(s)]")
        for s in issues:
            print("     ", s)
    return flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--water", help="data/water_polys.json")
    a = ap.parse_args()
    is_water = load_water(a.water) if a.water else None
    sys.exit(1 if sum(audit(f, is_water) for f in a.files) else 0)


if __name__ == "__main__":
    main()
