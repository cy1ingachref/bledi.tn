#!/usr/bin/env python3
"""Search the tunismapper source dumps for the places with no good coordinate.

`tunismapper_all_routes_stops.json` (22 MB) and `tunismapper_line_stops.json`
(21 MB) are the raw scraped source behind the seed. If a place has real
coordinates anywhere, it is most likely here.

    python tool/search_tunismapper.py
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
SRC = DUMP / "06-docs-tools" / "TunisiaTransport-repo" / "scripts"

idx = WaterIndex(json.loads((ROOT / "data" / "water_polys.json").read_text(encoding="utf-8"))["elements"])


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        s = s.replace(a, b)
    s = re.sub(r"[^0-9a-z\u0600-\u06ff]+", " ", s)
    return " ".join(s.split())


LAT = ("lat", "latitude", "y", "gps_lat")
LON = ("lon", "lng", "long", "longitude", "x", "gps_lon")
NAME = ("name", "nom", "station", "libelle", "arret", "stop_name", "name_fr", "designation")


def pick(o, keys):
    for k in o:
        if str(k).strip().lower() in keys:
            return o[k]
    return None


TARGETS = ["mouzaina", "مرزين", "douane bir", "محطة خاصة السيارات النقل الريفي",
           "نقل الريفي", "ريفي", "ghorfa", "غرفة", "ajim", "اجيم"]

for fn in ("tunismapper_all_routes_stops.json", "tunismapper_line_stops.json",
           "tunismapper_station_details.json", "tunismapper_station_sweep.json"):
    p = SRC / fn
    if not p.is_file():
        continue
    print("=" * 92)
    print(f"### {fn}  ({p.stat().st_size/1e6:.1f} MB)")
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        print(f"    parse error: {type(e).__name__}: {e}")
        continue

    hits: list[tuple] = []

    def walk(o, depth=0):
        if depth > 8:
            return
        if isinstance(o, dict):
            nm = pick(o, NAME)
            if nm:
                n = norm(str(nm))
                for t in TARGETS:
                    if norm(t) and norm(t) in n:
                        la, lo = pick(o, LAT), pick(o, LON)
                        hits.append((str(nm), la, lo))
                        break
            for v in o.values():
                walk(v, depth + 1)
        elif isinstance(o, list):
            for v in o:
                walk(v, depth + 1)

    walk(data)
    print(f"    name-matching entries: {len(hits)}")
    for nm, la, lo in hits[:14]:
        verdict = ""
        try:
            verdict = "WATER" if idx.contains(float(la), float(lo)) else "land"
        except (TypeError, ValueError):
            verdict = "no coords"
        print(f"      {nm[:46]:46s} {str(la)[:12]:>12s},{str(lo)[:12]:>12s}  {verdict}")

    # Also raw-text scan for the Arabic rural string with any numbers nearby.
    txt = p.read_text(encoding="utf-8", errors="replace")
    for key in ("النقل الريفي", "مرزين", "mouzaina"):
        ms = list(re.finditer(re.escape(key), txt, re.I))
        if ms:
            print(f"    raw occurrences of {key!r}: {len(ms)}")
            for m in ms[:3]:
                seg = " ".join(txt[max(0, m.start() - 160):m.end() + 160].split())
                print(f"      ...{seg[:200]}...")
