#!/usr/bin/env python3
"""Resolve the 5 mis-placed stations against the official TNRP registry.

The TNRP registry (2.58 MB, semicolon-delimited) is the authoritative national
bus-stop list. Columns:
  Societe;Agence;Nom de la station;Proprietaire;lon;lat;...;Type TNRP;
  Commune;Delegation;Gouvernorat;Code-Station

It carries BOTH the coordinate and the administrative location, so where the
two disagree the commune tells us which one is wrong.

    python tool/resolve_tnrp.py
"""

from __future__ import annotations
from pathlib import Path

import csv
import json
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
DUMP = (Path.home() / "Downloads" / "TunisiaTransport")
TNRP = DUMP / "01-bus-network" / "operator-exports" / "a6787314-3207-40a6-bbc4-534b84571371_a58870d0-6f61-4e8e-acda-6aa94a9b0acc.csv"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        s = s.replace(a, b)
    s = re.sub(r"[^0-9a-z\u0600-\u06ff]+", " ", s)
    return " ".join(s.split())


rows = list(csv.DictReader(TNRP.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
print(f"TNRP registry: {len(rows)} rows")
print(f"columns: {list(rows[0].keys())}\n")

QUERIES = {
    "Bir Mouzaina": ["mouzaina", "مرزينة", "مرزينه"],
    "Douane Bir Mouzaina": ["mouzaina", "douane"],
    "Ajim": ["ajim", "اجيم"],
    "Croisement ghorfa": ["ghorfa", "غرفة"],
    "Arabic rural (Zarzis)": ["محطة خاصة السيارات النقل الريفي"],
}

print("=" * 78)
for label, keys in QUERIES.items():
    print(f"\n### {label}   (keys: {keys})")
    found = 0
    for r in rows:
        blob = norm(" ".join(str(v) for v in r.values() if v))
        if any(norm(k) in blob for k in keys):
            print(f"  Nom      : {r.get('Nom de la station')}")
            print(f"  Agence   : {r.get('Agence')}")
            print(f"  Societe  : {r.get('Societe')}   Type: {r.get('Type de la station')}")
            print(f"  Commune  : {r.get('Commune')}  /  {r.get('Delegation')}  /  {r.get('Gouvernorat')}")
            print(f"  coord    : lon={r.get('lon')} lat={r.get('lat')}")
            print(f"  code     : {r.get('Code-Station')}")
            print("  " + "-" * 60)
            found += 1
            if found >= 6:
                break
    if not found:
        print("  (no TNRP match)")

# Every TNRP row whose coordinate is in the sea, to see how common that is.
print("\n" + "=" * 78)
print("TNRP rows with an IMPLAUSIBLE coordinate (lat<30 or >37.6, lon<7 or >12):")
bad = 0
for r in rows:
    try:
        la, lo = float(r.get("lat") or "nan"), float(r.get("lon") or "nan")
    except ValueError:
        continue
    if not (30.0 <= la <= 37.6 and 7.0 <= lo <= 12.0):
        bad += 1
        if bad <= 12:
            print(f"  {str(r.get('Nom de la station'))[:40]:40s} lon={r.get('lon'):>14s} lat={r.get('lat'):>14s} "
                  f"commune={str(r.get('Commune'))[:24]}")
print(f"  total implausible: {bad} of {len(rows)}")
