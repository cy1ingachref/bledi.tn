#!/usr/bin/env python3
"""Decide the correct coordinate for each of the 5 stations, with evidence.

Gathers every candidate from every source, then tests each against the water
index (validated 12/12 against ground truth). A candidate that lands in the sea
cannot be right. For a candidate that passes, the TNRP commune field says
whether the position is consistent with where the stop claims to be.

    python tool/decide_coords.py
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(r"C:\Users\cy1in\bledi.tn")
sys.path.insert(0, str(ROOT / "tool"))
from audit_station_placement import WaterIndex  # noqa: E402

DUMP = Path(r"C:\Users\cy1in\Downloads\tunisia-transport-data")
OE = DUMP / "01-bus-network" / "operator-exports"
TNRP = OE / "a6787314-3207-40a6-bbc4-534b84571371_a58870d0-6f61-4e8e-acda-6aa94a9b0acc.csv"


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
print("water index loaded\n")

tnrp = list(csv.DictReader(TNRP.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
geo = json.loads((OE / "_geolocated.json").read_text(encoding="utf-8"))
seed = json.loads((ROOT / "data" / "seed_all_tunisia_routes.tagged.json").read_text(encoding="utf-8"))["stations"]

# A robust reference point for a commune: median of TNRP rows in that commune.
def commune_ref(commune: str):
    pts = []
    for r in tnrp:
        if norm(r.get("Commune", "")) == norm(commune):
            try:
                pts.append((float(r["lat"]), float(r["lon"])))
            except (ValueError, KeyError):
                continue
    if not pts:
        return None, 0
    lats = sorted(p[0] for p in pts)
    lons = sorted(p[1] for p in pts)
    return (lats[len(lats) // 2], lons[len(lons) // 2]), len(pts)


def judge(label: str, lat: float, lon: float, commune: str | None = None) -> None:
    w = idx.contains(lat, lon)
    verdict = "IN WATER" if w else "on land"
    extra = ""
    if commune:
        ref, n = commune_ref(commune)
        if ref:
            d = hav(lat, lon, ref[0], ref[1]) / 1000
            extra = f"  | {commune} median is {d:6.1f} km away (n={n})"
            if not w and d > 40:
                verdict = "on land but FAR from its commune"
    print(f"    {label[:44]:44s} {lat:9.5f},{lon:10.5f}  {verdict}{extra}")


TARGETS = {
    "Ajim": ["ajim", "اجيم"],
    "Bir Mouzaina": ["mouzaina"],
    "Douane Bir Mouzaina": ["mouzaina", "douane bir"],
    "Croisement ghorfa": ["croisement ghorfa", "ghorfa"],
    "محطة خاصة السيارات النقل الريفي": ["محطة خاصة السيارات النقل الريفي"],
}

for label, keys in TARGETS.items():
    print("=" * 92)
    print(f"### {label}")
    print("  -- TNRP registry --")
    n = 0
    for r in tnrp:
        blob = norm(" ".join(str(v) for v in r.values() if v))
        if any(norm(k) in blob for k in keys):
            try:
                la, lo = float(r["lat"]), float(r["lon"])
            except (ValueError, KeyError):
                continue
            judge(f"{r.get('Nom de la station')} [{r.get('Societe')}]", la, lo, r.get("Commune"))
            n += 1
            if n >= 5:
                break
    if not n:
        print("    (none)")

    print("  -- _geolocated.json --")
    n = 0
    for g in geo:
        if any(norm(k) in norm(g.get("name", "")) for k in keys):
            judge(f"{g['name']} [{g.get('operator')}]", g["lat"], g["lon"])
            n += 1
            if n >= 5:
                break
    if not n:
        print("    (none)")

    print("  -- current seed rows --")
    n = 0
    for s in seed:
        if any(norm(k) in norm(s.get("name", "")) for k in keys):
            if s.get("lat") and s.get("lon"):
                judge(f"{s['name']} [{s['id'][:26]}]", s["lat"], s["lon"])
            else:
                print(f"    {s['name'][:44]:44s} NO COORDINATES  id={s['id'][:40]}")
            n += 1
            if n >= 6:
                break

# Where does SORETRAK operate? Its region tells us where Bir Mouzaina is.
print("\n" + "=" * 92)
print("### SORETRAK operating region (to locate Bir Mouzaina)")
so = [s for s in seed if (s.get("operator") or "").upper().startswith("SORETRAK")
      or "soretrk" in (s.get("id") or "").lower()]
print(f"  SORETRAK seed stops: {len(so)}")
pts = [(s["lat"], s["lon"]) for s in so if s.get("lat") and s.get("lon")]
if pts:
    lats = sorted(p[0] for p in pts)
    lons = sorted(p[1] for p in pts)
    print(f"  median position: {lats[len(lats)//2]:.4f}, {lons[len(lons)//2]:.4f}")
    print(f"  lat range: {lats[0]:.3f}..{lats[-1]:.3f}   lon range: {lons[0]:.3f}..{lons[-1]:.3f}")
    for s in so[:6]:
        if s.get("lat"):
            print(f"    {s['name'][:36]:36s} {s['lat']:.4f},{s['lon']:.4f}")

# And the route named Bir Mouzaina, in full.
print("\n### the SORETRAK route named 'Bir Mouzaina'")
net = json.loads((OE / "_network.json").read_text(encoding="utf-8"))
for r in net.get("routes", []):
    blob = norm(f"{r.get('origin','')} {r.get('destination','')} {r.get('route_long_name','')}")
    if "mouzaina" in blob:
        print("  " + json.dumps(r, ensure_ascii=False)[:400])
