#!/usr/bin/env python3
"""Pull the real coordinates of OSM bus stations found in the Overpass exports.

The rail-map export contains `bus_station` nodes whose name matches places we
need: "Gare routière de Zarzis", "محطة النقل الريفي المكنين", and the Ajim stop.
Those nodes carry geometry, so they give a real position even when TNRP's
coordinate is 32 km out to sea.

    python tool/osm_bus_station_coords.py
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(r"C:\Users\cy1in\bledi.tn")
sys.path.insert(0, str(ROOT / "tool"))
from audit_station_placement import WaterIndex  # noqa: E402

DUMP = Path(r"C:\Users\cy1in\Downloads\tunisia-transport-data")
EXPORT = DUMP / "02-rail-metro-tgm" / "rail-map-exports" / "export.json"

idx = WaterIndex(json.loads((ROOT / "data" / "water_polys.json").read_text(encoding="utf-8"))["elements"])


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ة", "ه").replace("ى", "ي").replace("أ", "ا")
    s = " ".join(s.split())
    return s


data = json.loads(EXPORT.read_text(encoding="utf-8", errors="replace"))
els = data.get("elements", [])
print(f"{EXPORT.name}: {len(els)} elements")

# Every bus station / bus stop with a name and a resolvable position.
rows = []
for el in els:
    tags = el.get("tags") or {}
    if not tags:
        continue
    kind = tags.get("amenity") or tags.get("highway") or tags.get("railway") or tags.get("public_transport")
    if kind not in ("bus_station", "bus_stop", "station", "stop_position", "halt", "train_station", "ferry_terminal"):
        continue
    nm = tags.get("name") or tags.get("name:fr") or tags.get("name:ar")
    if not nm:
        continue
    lat = el.get("lat")
    lon = el.get("lon")
    if lat is None and el.get("center"):
        lat, lon = el["center"].get("lat"), el["center"].get("lon")
    if lat is None and el.get("geometry"):
        g = el["geometry"]
        lat = sum(p["lat"] for p in g) / len(g)
        lon = sum(p["lon"] for p in g) / len(g)
    if lat is None:
        continue
    rows.append({"name": str(nm), "name_ar": tags.get("name:ar"), "kind": kind,
                 "lat": lat, "lon": lon, "id": el.get("id"), "tags": tags})

print(f"named stations/stops with a position: {len(rows)}")

print("\n" + "=" * 96)
print("stations relevant to the five problem places")
print("=" * 96)
KEYS = ["zarzis", "jerba", "ajim", "meknine", "maknin", "ريفي", "mouzaina", "ghorfa",
        "جربة", "جرجيس", "اجيم", "مكنين", "مرزين", "غرفة"]
for r in rows:
    blob = norm(" ".join(str(v) for v in (r["name"], r["name_ar"]) if v))
    if any(norm(k) in blob for k in KEYS):
        w = idx.contains(r["lat"], r["lon"])
        print(f"  {r['name'][:40]:40s} {r['lat']:9.5f},{r['lon']:10.5f}  {r['kind']:12s} "
              f"{'WATER' if w else 'land':5s} id={r['id']}")

print("\n" + "=" * 96)
print("ALL bus_stations (these are the interchanges worth connecting)")
print("=" * 96)
for r in rows:
    if r["kind"] in ("bus_station", "ferry_terminal", "train_station", "halt"):
        w = idx.contains(r["lat"], r["lon"])
        print(f"  {r['name'][:44]:44s} {r['lat']:9.5f},{r['lon']:10.5f}  {r['kind']:13s} "
              f"{'WATER' if w else 'land'}")

# Dump for reuse.
out = ROOT / "out" / "osm_bus_stations.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\nwrote {out}  ({len(rows)} stations)")
