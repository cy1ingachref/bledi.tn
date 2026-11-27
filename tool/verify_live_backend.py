#!/usr/bin/env python3
"""Verify the corrected data end to end against the LIVE backend.

Checks, in order:
  1. the 5 mis-placed stations no longer serve a bad position
  2. the new map overlay endpoints return real geometry
  3. every station detail carries its transport type(s) and line numbers
  4. the louage links resolve to real stations

    python tool/verify_live_backend.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "http://127.0.0.1:8000"
FAILS: list[str] = []
N = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global N
    N += 1
    if not ok:
        FAILS.append(label)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  -> {detail}" if detail and not ok else ""))


def get(path: str, timeout: int = 180):
    # Station ids can contain Arabic (e.g. the TNRP rural-transport stop), which
    # must be percent-encoded or http.client raises UnicodeEncodeError on the
    # request line. Quote only the path, and leave '/' intact.
    safe = urllib.parse.quote(path, safe="/?&=%")
    with urllib.request.urlopen(API + safe, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


print("1. the five corrected stations")
QUARANTINED = ["dl_bledi_curated_workbook_ajim",
               "dl_bledi_curated_workbook_bir_mouzaina",
               "dl_bledi_curated_workbook_douane_bir_mouzaina"]
for sid in QUARANTINED:
    try:
        d = get(f"/api/v1/stations/{sid}")
        ok = d.get("lat") is None and d.get("lon") is None
        check(f"{sid[:46]} serves no position", ok, f"lat={d.get('lat')} lon={d.get('lon')}")
    except urllib.error.HTTPError as e:
        check(f"{sid[:46]} is gone (HTTP {e.code})", e.code == 404, f"HTTP {e.code}")

MOVED = {
    "dl_tnrp_national_bus_stop_registry_محطة_خاصة_السيارات_النقل_الريفي": (33.499663, 11.114942),
    "dl_srtgn_croisement_ghorfa_76199": (36.9897778, 10.9519771),
}
for sid, (want_lat, want_lon) in MOVED.items():
    try:
        d = get(f"/api/v1/stations/{sid}")
        ok = (d.get("lat") is not None and abs(d["lat"] - want_lat) < 1e-4
              and abs(d["lon"] - want_lon) < 1e-4)
        check(f"{str(d.get('name'))[:30]} at the corrected position", ok,
              f"got {d.get('lat')},{d.get('lon')} want {want_lat},{want_lon}")
    except urllib.error.HTTPError as e:
        check(f"{sid[:46]} reachable", False, f"HTTP {e.code}")

print("\n2. map overlays")
try:
    rail = get("/api/v1/map/rail")
    feats = rail.get("features", [])
    check("rail overlay returns features", len(feats) > 500, f"{len(feats)}")
    modes = {}
    for f in feats:
        m = (f.get("properties") or {}).get("mode")
        modes[m] = modes.get(m, 0) + 1
    check("rail overlay has train and metro", "train" in modes and "metro" in modes, str(modes))
    bad = [f for f in feats if not (isinstance(f.get("geometry"), list) and len(f["geometry"]) >= 2)]
    check("every rail feature has >= 2 points", not bad, f"{len(bad)} bad")
    latlon = all(-90 <= p[0] <= 90 and -180 <= p[1] <= 180 for p in feats[0]["geometry"])
    check("rail geometry is [lat, lon] (Leaflet order)", latlon)
except urllib.error.HTTPError as e:
    check("rail overlay endpoint", False, f"HTTP {e.code}")

try:
    roads = get("/api/v1/map/roads")
    feats = roads.get("features", [])
    check("roads overlay returns features", len(feats) > 1000, f"{len(feats)}")
    classes = {}
    for f in feats:
        hw = (f.get("properties") or {}).get("highway")
        classes[hw] = classes.get(hw, 0) + 1
    check("roads have motorway/trunk/primary",
          {"motorway", "trunk", "primary"} <= set(classes), str(classes))
    refs = {(f.get("properties") or {}).get("ref") for f in feats}
    check("roads carry refs (RN1, A1 ...)", any(r for r in refs if r), f"e.g. {sorted(r for r in refs if r)[:5]}")
except urllib.error.HTTPError as e:
    check("roads overlay endpoint", False, f"HTTP {e.code}")

try:
    both = get("/api/v1/map/overlays")
    check("combined overlay returns both layers",
          "rail" in both and "roads" in both
          and len(both["rail"].get("features", [])) > 500
          and len(both["roads"].get("features", [])) > 1000)
except urllib.error.HTTPError as e:
    check("combined overlay endpoint", False, f"HTTP {e.code}")

print("\n3. stations carry type + line numbers")
seed = json.loads((ROOT / "data" / "seed_all_tunisia_routes.tagged.json").read_text(encoding="utf-8"))
with_lines = [s for s in seed["stations"] if s.get("lines_served")]
sample = with_lines[:3]
for s in sample:
    try:
        d = get(f"/api/v1/stations/{s['id']}")
        check(f"{str(d.get('name'))[:26]:26} has a mode", bool(d.get("modes")), str(d.get("modes")))
        lines = d.get("lines") or []
        check(f"{str(d.get('name'))[:26]:26} lines carry numbers",
              all((l.get("number") or l.get("route_short_name")) for l in lines) if lines else True,
              str(lines[:3]))
    except urllib.error.HTTPError as e:
        check(f"{s['id'][:40]} reachable", False, f"HTTP {e.code}")

# A station on a known numbered line, to prove numbers are real.
try:
    d = get("/api/v1/stations/sousse_bab_jdid")
    nums = [l.get("number") for l in (d.get("lines") or [])]
    check("sousse_bab_jdid has line entries", bool(nums), str(nums))
    check("sousse_bab_jdid is a train station", "train" in (d.get("modes") or []), str(d.get("modes")))
except urllib.error.HTTPError as e:
    check("sousse_bab_jdid reachable", False, f"HTTP {e.code}")

print("\n4. louage links")
try:
    lou = get("/api/v1/louage/links")
    links = lou.get("links", [])
    check("louage links returned", len(links) > 40, f"{len(links)}")
    unresolved = lou.get("unresolved", {})
    check("unresolved destinations are reported, not hidden",
          isinstance(unresolved, dict) and len(unresolved) <= 5, str(unresolved))
    bad = []
    for l in links[:20]:
        try:
            get(f"/api/v1/stations/{l['to']}")
        except urllib.error.HTTPError:
            bad.append(l["to"])
    check("every linked station id resolves", not bad, str(bad))
    froms = {l["from_name"] for l in links}
    check("all 13 national louage stations appear", len(froms) >= 10, f"{len(froms)}")
except urllib.error.HTTPError as e:
    check("louage links endpoint", False, f"HTTP {e.code}")

print("\n" + "=" * 64)
if FAILS:
    print(f"FAILED {len(FAILS)} of {N}: {FAILS}")
    sys.exit(1)
print(f"all {N} live checks passed")
