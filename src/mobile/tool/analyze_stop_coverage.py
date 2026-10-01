"""Measure how much of the per-line stop data is actually new information.

The question this answers: if the app already loads /api/v1/stations
(1 711 GeoJSON points), does it still need 232 calls to
/api/v1/lines/{id} to show "every station and every stop"?

If the stop coordinates are already contained in the station set, the extra
232 requests are wasted latency for zero additional map content.
"""

import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://localhost:8000"
STOP = 0.00005  # ~5 m, for rounding


def get(path):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as r:
        return json.load(r)


def rnd(lat, lon):
    return (round(lat, 5), round(lon, 5))


t0 = time.time()
stations = get("/api/v1/stations")["features"]
st_ids = {f["properties"]["id"] for f in stations}
st_pts = {
    rnd(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0])
    for f in stations
}
lines = get("/api/v1/lines?limit=500")["lines"]
print(f"stations={len(stations)} lines={len(lines)} ({time.time()-t0:.1f}s)")


def fetch(line):
    try:
        return get(f"/api/v1/lines/{line['id']}").get("stops") or []
    except Exception as exc:  # noqa: BLE001
        print("  fail", line["id"], exc)
        return []


t0 = time.time()
with ThreadPoolExecutor(16) as pool:
    per_line = list(pool.map(fetch, lines))
fetch_s = time.time() - t0

flat = [s for group in per_line for s in group]
withpt = [s for s in flat if s.get("lat") is not None and s.get("lon") is not None]
stop_ids = {s.get("stop_id") for s in flat if s.get("stop_id")}
stop_pts = {rnd(s["lat"], s["lon"]) for s in withpt}

print(f"\nfetched in {fetch_s:.1f}s (16 workers)")
print(f"  total stop refs           : {len(flat)}")
print(f"  stops with coordinates    : {len(withpt)}")
print(f"  unique stop ids           : {len(stop_ids)}")
print(f"  unique stop coordinates   : {len(stop_pts)}")
print(f"  stations w/ coordinates   : {len(st_pts)}")
print(
    f"\n  stop ids also in stations : {len(stop_ids & st_ids)}"
    f" of {len(stop_ids)}"
)
print(
    f"  stop coords already in stations : {len(stop_pts & st_pts)}"
    f" of {len(stop_pts)}"
)
extra = stop_pts - st_pts
print(f"  stop coords NOT in stations     : {len(extra)}")
for pt in sorted(extra)[:5]:
    print(f"     {pt}")