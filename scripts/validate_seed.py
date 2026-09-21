#!/usr/bin/env python3
"""Data validator for bledi.tn seed — flags bad hops, orphan stations, mode issues."""
import json
import math
import sys
from collections import Counter
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
seed_path = repo / "data/seed_all_tunisia_routes.json"

R = 6371000.0

def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

seed = json.loads(seed_path.read_text())
stations = seed["stations"]
lines = seed["lines"]

# Build station lookup
sidx = {}
for s in stations:
    sidx[s["id"]] = s

print("=" * 60)
print("BLEDI.TN — Data Validator")
print("=" * 60)
print(f"Stations: {len(stations)}  |  Lines: {len(lines)}")
print()

# ── 1. Bad hops (>5km between consecutive stops) ──────────────────────
print("--- Bad hops (>5km between consecutive stops) ---")
bad_hops = []
urban_bad = []
for line in lines:
    sts = line.get("stations", [])
    for i in range(len(sts)-1):
        s1 = sidx.get(sts[i])
        s2 = sidx.get(sts[i+1])
        if not s1 or not s2:
            continue
        if not s1.get("lat") or not s2.get("lat"):
            continue
        d = haversine(s1["lat"], s1["lon"], s2["lat"], s2["lon"])
        if d > 5000:
            entry = (line.get("number","?"), round(d/1000, 1), s1["name"][:30], s2["name"][:30])
            bad_hops.append(entry)
            # Flag urban bad hops (<200km — likely wrong geocode, not long-distance train)
            if d < 200000:
                urban_bad.append(entry)

print(f"Total hops >5km: {len(bad_hops)}")
print(f"  of which likely wrong geocode (<200km): {len(urban_bad)}")
print()
print("Worst 10 hops:")
for num, d, n1, n2 in sorted(bad_hops, key=lambda x: -x[1])[:10]:
    flag = " ⚠ URBAN" if d < 200 else ""
    print(f"  {num:8s} {d:7.1f}km  {n1} -> {n2}{flag}")
print()

# ── 2. Orphan stations (no lines_served) ──────────────────────────────
print("--- Orphan stations (no lines_served) ---")
orphan = [s for s in stations if not s.get("lines_served") or len(s.get("lines_served",[])) == 0]
print(f"Stations with no lines: {len(orphan)}")
for s in orphan[:10]:
    print(f"  {s['id']:8s} {s['name'][:40]} lat={s['lat']} lon={s['lon']}")
if len(orphan) > 10:
    print(f"  ... and {len(orphan)-10} more")
print()

# ── 3. Mode coverage ──────────────────────────────────────────────────
print("--- Mode coverage ---")
mode_counts = Counter()
for l in lines:
    mode = l.get("mode", "unknown")
    if not mode:
        mode = "unknown"
    mode_counts[mode] += 1
print(f"Lines by mode: {dict(mode_counts)}")
unknown_mode = [l for l in lines if not l.get("mode")]
print(f"Lines with no mode field: {len(unknown_mode)}")
if unknown_mode:
    print("  Examples:")
    for l in unknown_mode[:5]:
        print(f"    {l.get('number','?'):8s} route_id={l.get('route_id','?')}")
print()

# ── 4. Stations with no GPS ───────────────────────────────────────────
print("--- Stations without GPS ---")
no_gps = [s for s in stations if not s.get("lat") or not s.get("lon") or s["lat"] == 0 or s["lon"] == 0]
print(f"Stations with no/zero GPS: {len(no_gps)}")
for s in no_gps[:10]:
    print(f"  {s['id']:8s} {s['name'][:40]}")
if len(no_gps) > 10:
    print(f"  ... and {len(no_gps)-10} more")
print()

# ── 5. Lines with no stops ────────────────────────────────────────────
print("--- Lines with no station data ---")
empty_lines = [l for l in lines if not l.get("stations") or len(l.get("stations",[])) == 0]
print(f"Lines with no stations listed: {len(empty_lines)}")
for l in empty_lines[:10]:
    print(f"  {l.get('number','?'):8s} {l.get('long_name','?')[:40]} route_id={l.get('route_id','?')}")
if len(empty_lines) > 10:
    print(f"  ... and {len(empty_lines)-10} more")
print()

# ── 6. Regional coverage summary ──────────────────────────────────────
print("--- Regional coverage ---")
regions = {
    "Tunis/Greater Tunis": ["tunis", "micronase", "el menzah", "aria", "la marse", "rades", "nerja", "bouartimi", "charguia", "manouba", "tebourba", "sidi des", "ben arous", "cou방지법", "cite", "gabes"],
    "Bizerte": ["bizerte", "pon", "ras jedir", "kj", "jupyter"],
    "Sfax": ["sfax", "comptoir"],
    "Kairouan": ["kairouan"],
    "Gabes": ["gabes"],
    "Tozeur": ["tozeur"],
    "Medenine": ["medenine"],
    "Tataouine": ["tataouine"],
    "Djerba": ["djerba", "houmt"],
    "Sousse": ["sousse"],
    "Monastir": ["monastir"],
    "Mahdia": ["mahdia"],
    "Ariana": ["ariana"],
    "Mannouba": ["mannouba", "manouba"],
    "Ben Arous": ["ben arous"],
    "Nabeul": ["nabeul"],
    "Zaghouan": ["zaghouan"],
    "Jendouba": ["jendouba"],
    "Beja": ["beja"],
    "Le Kef": ["kef"],
    "Siliana": ["siliana"],
    "Kasserine": ["kasserine"],
    "Sidi Bouzid": ["sidi bou"],
    "Gafsa": ["gafsa"],
    "Metlaoui": ["metlaoui"],
}

for region, keywords in regions.items():
    count = sum(1 for s in stations if any(kw in (s.get("name","") or "").lower() for kw in keywords))
    print(f"  {region:22s}: {count:3d} stations")

print()
print("=" * 60)
print("Summary:")
print(f"  Bad hops >5km:         {len(bad_hops):5d}  ({len(urban_bad)} likely wrong geocode)")
print(f"  Orphan stations:       {len(orphan):5d}")
print(f"  Lines no mode:         {len(unknown_mode):5d}")
print(f"  Stations no GPS:       {len(no_gps):5d}")
print(f"  Lines no stops:        {len(empty_lines):5d}")
print("=" * 60)
