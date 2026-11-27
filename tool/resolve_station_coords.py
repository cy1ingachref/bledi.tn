#!/usr/bin/env python3
"""Resolve the 5 mis-placed stations against the official geolocated stops.

`_geolocated.json` is the clean 4,309-stop list (name + lat + lon + operator +
mode). `_official_stops.json` also contains 1,082 level crossings whose name is
EMPTY and whose coordinates are the placeholder (37.0, 7.0) — matching against
it produces garbage, which is why the first pass matched everything.

    python tool/resolve_station_coords.py
"""

from __future__ import annotations
from pathlib import Path

import json
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
DUMP = (Path.home() / "Downloads" / "TunisiaTransport")
GEO = DUMP / "01-bus-network" / "operator-exports" / "_geolocated.json"
NET = DUMP / "01-bus-network" / "operator-exports" / "_network.json"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        s = s.replace(a, b)
    s = re.sub(r"[^0-9a-z\u0600-\u06ff]+", " ", s)
    return " ".join(s.split())


TARGETS = [
    "croisement ghorfa",
    "douane bir mouzaina",
    "bir mouzaina",
    "ajim",
    "محطة خاصة السيارات النقل الريفي",
]

geo = json.loads(GEO.read_text(encoding="utf-8"))
print(f"_geolocated.json: {len(geo)} stops\n")

# Index by normalised name, ignoring the empty-name placeholder rows.
by_name: dict[str, list[dict]] = {}
for g in geo:
    nm = norm(g.get("name", ""))
    if not nm:
        continue
    by_name.setdefault(nm, []).append(g)

print("=== official geolocated matches for each target ===")
for t in TARGETS:
    tn = norm(t)
    print(f"\n  {t}")
    # exact, then token-subset, then substring
    exact = by_name.get(tn, [])
    loose = []
    if not exact:
        tt = set(tn.split())
        for nm, rows in by_name.items():
            s = set(nm.split())
            if tt and (tt <= s or s <= tt) and len(tt & s) >= 2:
                loose += rows
            elif len(tn) >= 6 and (tn in nm or nm in tn):
                loose += rows
    hits = exact or loose
    if not hits:
        print("    (no official match)")
        continue
    for h in hits[:10]:
        print(f"    {h['name'][:32]:32s} {h['lat']:.5f},{h['lon']:.5f}  "
              f"{h.get('operator','')}/{h.get('mode','')}")
        ak = h.get("also_known_as")
        if ak:
            print(f"      also known as: {', '.join(str(x) for x in ak)[:70]}")

# What do the WRONG coordinates look like nearby? Name any other stop that sits
# at the bad point, which is how a duplicate got created.
print("\n=== stops within 3 km of the BAD coordinate 37.16, 9.72 (Lake Ichkeul) ===")
import math

def hav(a1, o1, a2, o2):
    R = 6371000.0
    p1, p2 = math.radians(a1), math.radians(a2)
    x = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(o2 - o1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(x))

for g in geo:
    d = hav(37.16, 9.72, g["lat"], g["lon"])
    if d < 3000:
        print(f"    {g['name'][:36]:36s} {g['lat']:.5f},{g['lon']:.5f}  {d:6.0f} m  {g.get('mode','')}")

print("\n=== routes whose name mentions these places (for line numbers) ===")
net = json.loads(NET.read_text(encoding="utf-8"))
for t in TARGETS[:4]:
    tn = norm(t)
    key = tn.split()[0]
    print(f"\n  {t}")
    n = 0
    for r in net.get("routes", []):
        blob = norm(f"{r.get('origin','')} {r.get('destination','')} {r.get('route_long_name','')}")
        if key in blob:
            print(f"    {r.get('operator','')}/{r.get('mode','')} "
                  f"line={r.get('route_short_name') or r.get('route_id')} "
                  f"{str(r.get('origin'))[:22]} -> {str(r.get('destination'))[:22]} "
                  f"({r.get('trip_count')} trips, {r.get('stop_count')} stops)")
            n += 1
            if n >= 8:
                break
    if not n:
        print("    (no route mentions it)")
