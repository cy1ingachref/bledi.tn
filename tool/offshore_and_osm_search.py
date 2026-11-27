#!/usr/bin/env python3
"""Measure how far offshore each suspect coordinate is, and search the OSM
Overpass exports for the places that have no good coordinate yet.

Part 1: for every candidate, report water/land and the distance to the nearest
land vertex, so "in the sea" becomes "N km offshore" — an objective statement
rather than a binary.

Part 2: grep the Overpass exports (rail + highways) for the target names. Those
exports carry Arabic names (e.g. محطة النقل الريفي المكنين), so they may hold
the real position for the stops TNRP got wrong.

    python tool/offshore_and_osm_search.py
"""

from __future__ import annotations
from pathlib import Path

import json
import math
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tool"))
from audit_station_placement import WaterIndex  # noqa: E402

DUMP = (Path.home() / "Downloads" / "TunisiaTransport")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        s = s.replace(a, b)
    s = re.sub(r"[^0-9a-z\u0600-\u06ff]+", " ", s)
    return " ".join(s.split())


def hav(a1, o1, a2, o2):
    R = 6371000.0
    p1, p2 = math.radians(a1), math.radians(a2)
    x = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(o2 - o1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(x))


idx = WaterIndex(json.loads((ROOT / "data" / "water_polys.json").read_text(encoding="utf-8"))["elements"])

# Flatten land ring vertices once, for a nearest-coast distance.
land_pts: list[tuple[float, float]] = []
for _name, ring, _bb in idx.land_rings:
    land_pts.extend(ring)
print(f"land vertices for distance: {len(land_pts)}")


def nearest_land_km(lat: float, lon: float) -> float:
    best = math.inf
    for lo, la in land_pts:
        # Cheap equirectangular pre-filter before the trig.
        if abs(la - lat) > 0.6 or abs(lo - lon) > 0.7:
            continue
        d = (la - lat) ** 2 + (lo - lon) ** 2
        if d < best:
            best = d
    if best == math.inf:
        return math.inf
    # Find the true nearest among the coarse winners by rescanning tightly.
    cand = [(lo, la) for lo, la in land_pts if abs(la - lat) <= 0.6 and abs(lo - lon) <= 0.7]
    if not cand:
        return math.inf
    return min(hav(lat, lon, la, lo) for lo, la in cand) / 1000


SUSPECTS = [
    ("Croisement ghorfa (TNRP/SRT_NABEUL)", 37.0033074, 10.7337504, "Haouaria, Nabeul"),
    ("Croisement ghorfa (seed curated)", 37.0033074, 10.7337504, "Haouaria, Nabeul"),
    ("GHORFA (SRT Jendouba)", 36.8052640557, 8.9052841254, "Beja/Ain Draham"),
    ("Elghorfa (SRT_NABEUL)", 36.9897778, 10.9519771, "Haouaria, Nabeul"),
    ("Ajim WRONG (curated)", 37.162, 9.735, "none"),
    ("Bir Mouzaina WRONG (curated)", 37.16, 9.72, "none"),
    ("Douane Bir Mouzaina WRONG (curated)", 37.155, 9.705, "none"),
    ("Arabic rural TNRP (Zarzis)", 33.501516, 11.54331, "Zarzis, Medenine"),
    ("Ajim CORRECT (SNTRI/TNRP)", 33.72490, 10.74830, "Ajim, Medenine"),
    ("Zarzis town centre (reference)", 33.5044, 11.1122, "Zarzis"),
    ("El Haouaria (reference)", 37.0500, 10.9900, "Haouaria"),
]

print("\n" + "=" * 96)
print(f"{'label':40s} {'lat':>9s} {'lon':>10s}  {'verdict':10s} {'offshore':>10s}  claims")
print("=" * 96)
for label, lat, lon, claims in SUSPECTS:
    w = idx.contains(lat, lon)
    d = nearest_land_km(lat, lon)
    verdict = "WATER" if w else "land"
    off = f"{d:8.2f} km" if w else "-"
    print(f"{label[:40]:40s} {lat:9.4f} {lon:10.4f}  {verdict:10s} {off:>10s}  {claims}")

# ── Part 2: search the Overpass exports for the names ──────────────────────
print("\n" + "=" * 96)
print("Overpass export search")
print("=" * 96)

SEARCH = {
    "mouzaina": "Bir Mouzaina",
    "ghorfa": "Ghorfa",
    "ajim": "Ajim",
    "jerba": "Jerba",
    "zarzis": "Zarzis",
    "ريفي": "rural transport (Arabic)",
    "مرزين": "Mouzaina (Arabic)",
    "غرفة": "Ghorfa (Arabic)",
    "اجيم": "Ajim (Arabic)",
}

EXPORTS = [
    DUMP / "02-rail-metro-tgm" / "rail-map-exports" / "export.json",
    DUMP / "02-rail-metro-tgm" / "rail-network-exports" / "export.json",
    DUMP / "03-roads" / "highways" / "export.json",
]

for p in EXPORTS:
    if not p.is_file():
        continue
    print(f"\n--- {p.relative_to(DUMP)}  ({p.stat().st_size/1e6:.1f} MB)")
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        print(f"    could not parse: {type(e).__name__}")
        continue
    els = data.get("elements", data if isinstance(data, list) else [])
    print(f"    elements: {len(els)}")
    for key, label in SEARCH.items():
        found = []
        for el in els:
            tags = el.get("tags") or {}
            blob = norm(" ".join(str(v) for v in tags.values() if v))
            if norm(key) and norm(key) in blob:
                nm = tags.get("name") or tags.get("name:ar") or tags.get("ref") or "?"
                lat = el.get("lat") or (el.get("center") or {}).get("lat")
                lon = el.get("lon") or (el.get("center") or {}).get("lon")
                if lat is None and el.get("geometry"):
                    lat = el["geometry"][0]["lat"]
                    lon = el["geometry"][0]["lon"]
                found.append((str(nm), lat, lon, tags.get("highway") or tags.get("railway") or tags.get("amenity") or ""))
        if found:
            print(f"    [{label}] {len(found)} hit(s)")
            for nm, lat, lon, kind in found[:5]:
                print(f"       {nm[:40]:40s} {str(lat)[:10]:>10s},{str(lon)[:10]:>10s}  {kind}")
