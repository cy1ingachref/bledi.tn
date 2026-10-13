#!/usr/bin/env python3
"""Dump TNRP rows for the communes that matter, to place the suspect stops.

Zarzis (the Arabic rural station), Haouaria (Croisement ghorfa) and Ajim are the
communes named by the registry. Seeing every other stop in those communes gives
local context — and may reveal the actual station the bad coordinate was meant
to be.

    python tool/tnrp_commune_context.py
"""

from __future__ import annotations

import csv
import json
import math
import sys
import unicodedata
from pathlib import Path

ROOT = Path(r"C:\Users\cy1in\bledi.tn")
sys.path.insert(0, str(ROOT / "tool"))
from audit_station_placement import WaterIndex  # noqa: E402

DUMP = Path(r"C:\Users\cy1in\Downloads\tunisia-transport-data")
TNRP = (DUMP / "01-bus-network" / "operator-exports"
        / "a6787314-3207-40a6-bbc4-534b84571371_a58870d0-6f61-4e8e-acda-6aa94a9b0acc.csv")

idx = WaterIndex(json.loads((ROOT / "data" / "water_polys.json").read_text(encoding="utf-8"))["elements"])


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        s = s.replace(a, b)
    return " ".join(s.split())


rows = list(csv.DictReader(TNRP.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))

COMMUNES = ["جرجيس", "zarzis", "haouaria", "houaria", "ajim", "اجيم", "medenine"]

print("=" * 100)
for c in COMMUNES:
    sel = [r for r in rows if norm(c) in norm(r.get("Commune", "")) or norm(c) in norm(r.get("Delegation", ""))]
    if not sel:
        continue
    good = 0
    print(f"\n### commune/delegation matching {c!r}: {len(sel)} rows")
    for r in sel[:40]:
        try:
            la, lo = float(r["lat"]), float(r["lon"])
            w = idx.contains(la, lo)
        except (ValueError, KeyError):
            w, la, lo = None, None, None
        flag = "  <-- WATER" if w else ""
        if w is False:
            good += 1
        print(f"  {str(r.get('Nom de la station'))[:38]:38s} {str(la)[:10]:>10s},{str(lo)[:11]:>11s} "
              f"{str(r.get('Type de la station'))[:14]:14s} {str(r.get('Societe'))[:14]:14s}"
              f"{str(r.get('Agence'))[:18]:18s}{flag}")
    print(f"  on land: {good}/{len(sel)}")

# Specifically: every Zarzis row, to find the rural transport station.
print("\n" + "=" * 100)
print("### every row whose Commune contains 'جرجيس' or Delegation is 'Zarzis'")
zs = [r for r in rows if "جرجيس" in str(r.get("Commune", "")) or norm(r.get("Delegation", "")) == "zarzis"]
print(f"  {len(zs)} rows")
for r in zs:
    try:
        la, lo = float(r["lat"]), float(r["lon"])
        w = "WATER" if idx.contains(la, lo) else "land"
    except (ValueError, KeyError):
        w, la, lo = "nocoord", "", ""
    print(f"  {str(r.get('Nom de la station'))[:40]:40s} {str(la)[:11]:>11s},{str(lo)[:11]:>11s} {w:6s} "
          f"{str(r.get('Type TNRP'))[:16]:16s} {str(r.get('Code-Station')):12s} {str(r.get('Agence'))[:24]}")

# And the raw line as stored, for the exact row we must fix.
print("\n" + "=" * 100)
print("### raw registry line for the Zarzis rural station")
for r in rows:
    if "محطة خاصة السيارات النقل الريفي" in str(r.get("Nom de la station", "")):
        print("  " + ";".join(f"{k}={v}" for k, v in r.items()))
