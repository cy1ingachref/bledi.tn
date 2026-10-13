#!/usr/bin/env python3
"""Inspect the seed's line structure, so station lines can be computed.

Tasks 5 and 6 need to know, for each station, which lines pass through it and
with which mode. This prints the shape of `lines` and how stations reference
them, plus the current line-number fields.

    python tool/inspect_seed_lines.py
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(r"C:\Users\cy1in\bledi.tn")
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"

d = json.loads(SEED.read_text(encoding="utf-8"))
print(f"top-level keys: {list(d)}")
st = d["stations"]
ln = d["lines"]
print(f"stations: {len(st)}   lines: {len(ln)}\n")

print("=== station keys (union) ===")
keys = collections.Counter()
for s in st:
    for k in s:
        keys[k] += 1
for k, v in keys.most_common():
    print(f"  {k:22s} {v}")

print("\n=== sample station ===")
for s in st:
    if s.get("lines_served"):
        print(json.dumps(s, ensure_ascii=False, indent=1)[:900])
        break
print("\n=== a station with no lines_served ===")
for s in st:
    if not s.get("lines_served"):
        print(json.dumps(s, ensure_ascii=False, indent=1)[:700])
        break

print("\n=== line keys (union) ===")
lkeys = collections.Counter()
for l in ln:
    for k in l:
        lkeys[k] += 1
for k, v in lkeys.most_common():
    print(f"  {k:22s} {v}")

print("\n=== sample line ===")
print(json.dumps(ln[0], ensure_ascii=False, indent=1)[:1200])

print("\n=== how many lines carry a stop list, and what field? ===")
with_stops = 0
for l in ln:
    for k in ("stops", "stop_ids", "stations", "trip_stops"):
        if l.get(k):
            with_stops += 1
            break
print(f"  lines with a stop list: {with_stops} / {len(ln)}")

print("\n=== line number / short name fields present ===")
for f in ("number", "short_name", "code", "ref", "line_number", "route_short_name", "name"):
    have = sum(1 for l in ln if l.get(f))
    if have:
        print(f"  {f:20s} {have} lines; e.g. {[l.get(f) for l in ln if l.get(f)][:6]}")

print("\n=== mode distribution over lines ===")
print(collections.Counter(l.get("mode") for l in ln).most_common())

print("\n=== louage stations in the seed ===")
lou = [s for s in st if s.get("mode") == "louaj" or "louage" in (s.get("id") or "").lower()]
print(f"  {len(lou)} louage-ish stations")
for s in lou[:20]:
    print(f"    {s['id'][:44]:44s} {str(s.get('name'))[:30]:30s} {s.get('lat')},{s.get('lon')} "
          f"lines={s.get('lines_served')}")

print("\n=== lines whose mode is louaj ===")
for l in ln:
    if l.get("mode") in ("louaj", "louage") or "louage" in (l.get("id") or "").lower():
        print("  " + json.dumps(l, ensure_ascii=False)[:340])
