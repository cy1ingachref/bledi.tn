#!/usr/bin/env python3
"""Audit the committed route geometry cache for plausibility.

Lives in the repo rather than a temp dir for the same reason as
verify_routing.py: a check that is deleted after its run leaves no artefact and
becomes indistinguishable from "never checked". This one guards the file that
decides what the map draws, so a bad entry is a visible lie.

    python src/backend/tool/verify_geometry.py

Asserts, over every cached segment:
  1. both key stations exist in the seed
  2. the polyline begins at one endpoint and ends at the other, to ~1 m
  3. no path exceeds MAX_DETOUR_FACTOR times the straight line it replaces
  4. reports the path/straight distribution so a drift in shape is visible

Exit 0 when all assertions hold, 1 otherwise. Reads only.
"""

import json, math, os, sys
from collections import Counter

REPO = r'C:\Users\cy1in\bledi.tn'
CACHE = os.path.join(REPO, 'data', 'route_geometry.json')
SEED = os.path.join(REPO, 'data', 'seed_all_tunisia_routes.tagged.json')

def hav(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))

cache = json.load(open(CACHE, encoding='utf-8'))
seed = json.load(open(SEED, encoding='utf-8'))
sidx = {s['id']: s for s in seed['stations']}
seg = cache['segments']
print(f"cache: {len(seg)} segments, metadata={cache['metadata']['resolved']} resolved")

bad_key = detaches = too_long = 0
ratios = []
srcs = Counter()
for key, v in seg.items():
    srcs[v['source']] += 1
    a_id, b_id = key.split('|')
    if not (a_id in sidx and b_id in sidx):
        bad_key += 1
        continue
    a, b = sidx[a_id], sidx[b_id]
    g = v['geometry']
    if not g:
        continue
    # 1. must start at one endpoint and end at the other.
    #    Compared with a small tolerance, not exact equality: the builder snaps
    #    these to the station coordinates, but a rounding artefact here would
    #    report every entry as detached and hide real problems.
    TOL = 1e-5  # ~1.1 m
    near = lambda p, s: abs(p[0]-s['lat']) < TOL and abs(p[1]-s['lon']) < TOL
    if not ((near(g[0], a) or near(g[0], b)) and (near(g[-1], a) or near(g[-1], b))):
        detaches += 1
    # 2. path length vs straight line
    L = sum(hav(g[i], g[i+1]) for i in range(len(g)-1))
    S = hav((a['lat'], a['lon']), (b['lat'], b['lon']))
    if S > 50:
        ratios.append((L/S, key, L, S))
        if L > S * 4.0:
            too_long += 1

ratios.sort()
print(f"sources: {dict(srcs)}")
print(f"keys not in seed: {bad_key}")
print(f"geometries not touching both endpoints: {detaches}")
print(f"path > 4x straight line: {too_long}")
if ratios:
    r = [x[0] for x in ratios]
    print(f"path/straight ratio over {len(ratios)} resolved: min {r[0]:.2f} "
          f"median {r[len(r)//2]:.2f} p99 {r[int(len(r)*0.99)]:.2f} max {r[-1]:.2f}")
    print("worst 5:")
    for ratio, key, L, S in ratios[-5:]:
        print(f"  {ratio:5.2f}x  path {L:8.0f}m  straight {S:8.0f}m  {key}")

missing = [(k, v['reason']) for k, v in seg.items() if not v['geometry']]
print(f"\nmissing {len(missing)}:")
for r, c in Counter(r for _, r in missing).most_common():
    print(f"  {c:4d}  {r}")

ok = not bad_key and not detaches and not too_long
print("\n" + ("GEOMETRY AUDIT PASS" if ok else "GEOMETRY AUDIT FAILED"))
sys.exit(0 if ok else 1)
