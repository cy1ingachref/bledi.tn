#!/usr/bin/env python3
"""Pin down the remaining three targets and print the exact seed rows.

Croisement ghorfa and Ajim are resolved from _geolocated.json. Remaining:
  - Bir Mouzaina / Douane Bir Mouzaina: no official geolocated entry, but
    SORETRAK route 771 is named "Bir Mouzaina", which points at the Sfax region.
  - the Arabic rural-transport stop.

Also prints the exact seed rows for all five, so the before/after is explicit.

    python tool/pin_remaining_coords.py
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\cy1in\bledi.tn")
DUMP = Path(r"C:\Users\cy1in\Downloads\tunisia-transport-data")


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


print("=== 1. exact seed rows for the five targets ===")
seed = json.loads((ROOT / "data" / "seed_all_tunisia_routes.tagged.json").read_text(encoding="utf-8"))
KEYS = ["ghorfa", "mouzaina", "ajim", "النقل الريفي", "السيارات النقل"]
for s in seed["stations"]:
    n = norm(s.get("name", ""))
    if any(norm(k) in n for k in KEYS):
        print(f"  {s['id'][:52]:52s} name={str(s.get('name'))[:30]:30s} "
              f"lat={s.get('lat')} lon={s.get('lon')} "
              f"q={bool(s.get('quarantined'))} mode={s.get('mode')}")

print("\n=== 2. the soretras row that matched everything (what IS it?) ===")
for s in seed["stations"]:
    if s["id"] == "soretras__9ca0fb634d":
        print(json.dumps(s, ensure_ascii=False, indent=1)[:700])

print("\n=== 3. grep the whole dump for 'mouzaina' (csv/json) ===")
hits = 0
for p in DUMP.rglob("*"):
    if not p.is_file() or p.suffix.lower() not in (".csv", ".json"):
        continue
    try:
        if p.stat().st_size > 60_000_000:
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        continue
    if "mouzaina" not in txt.lower():
        continue
    for m in re.finditer(r".{0,90}[Mm]ouzaina.{0,90}", txt):
        line = " ".join(m.group(0).split())
        print(f"  {p.relative_to(DUMP)}")
        print(f"     {line[:170]}")
        hits += 1
        if hits >= 12:
            break
    if hits >= 12:
        break
if not hits:
    print("  (no textual match)")

print("\n=== 4. grep the dump for the Arabic rural-transport name ===")
AR = "النقل الريفي"
hits = 0
for p in DUMP.rglob("*"):
    if not p.is_file() or p.suffix.lower() not in (".csv", ".json"):
        continue
    try:
        if p.stat().st_size > 60_000_000:
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        continue
    if AR not in txt:
        continue
    for m in re.finditer(r".{0,80}" + AR + r".{0,80}", txt):
        print(f"  {p.relative_to(DUMP)}")
        print(f"     {' '.join(m.group(0).split())[:170]}")
        hits += 1
        if hits >= 8:
            break
    if hits >= 8:
        break
if not hits:
    print("  (no textual match in the dump)")

print("\n=== 5. Nominatim for the place names (1 req/sec) ===")
def nom(q, extra=""):
    url = ("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=3"
           f"&countrycodes=tn&q={urllib.parse.quote(q)}{extra}")
    req = urllib.request.Request(url, headers={"User-Agent": "bledi.tn-audit/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        return [{"error": f"{type(e).__name__}: {e}"}]

for q in ("Bir Mouzaina", "Bir Mouzaina Sfax", "Douane Bir Mouzaina"):
    print(f"\n  query: {q}")
    for r in nom(q):
        if "error" in r:
            print(f"    ERROR {r['error']}")
            continue
        print(f"    {r['lat']},{r['lon']}  {r.get('type','')}  {r['display_name'][:76]}")
    time.sleep(1.2)
