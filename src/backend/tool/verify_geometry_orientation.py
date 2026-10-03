#!/usr/bin/env python3
"""Verify route geometry is oriented along the direction of travel.

The cache is keyed by an unordered station pair and every polyline is stored
min -> max, so a leg travelling the other way must be reversed or the map draws
the line backwards through the intermediate stops. That fault is invisible in a
leg count and only shows on screen, so it gets an explicit check.

Queries the live API in both directions of each pair, which is what actually
exercises the reversal: a one-way test would pass even with the reversal broken.

    python src/backend/tool/verify_geometry_orientation.py   [--port 8000]

Requires the backend to be running. Exit 0 when every geometry leg starts at its
step's start point and ends at its end point, 1 otherwise.
"""

import json, sys, urllib.parse, urllib.request

import argparse

_ap = argparse.ArgumentParser()
_ap.add_argument('--port', type=int, default=8000)
BASE = f'http://127.0.0.1:{_ap.parse_args().port}'

def route(a, b):
    u = BASE + '/api/v1/route/transit?' + urllib.parse.urlencode(
        dict(start_lat=a[0], start_lon=a[1], end_lat=b[0], end_lon=b[1]))
    return json.load(urllib.request.urlopen(u, timeout=120))

TRIPS = {
    'Tunis->Sfax': ((36.8078, 10.1815), (34.7406, 10.7603)),
    'Sfax->Tunis': ((34.7406, 10.7603), (36.8078, 10.1815)),   # reverse of the above
    'Tunis->Bizerte': ((36.8078, 10.1815), (37.2744, 9.8739)),
    'Bizerte->Tunis': ((37.2744, 9.8739), (36.8078, 10.1815)),
    'Tunis->La Marsa': ((36.8078, 10.1815), (36.8781, 10.3230)),
    'Sousse->Nabeul': ((35.8256, 10.6360), (36.4560, 10.7376)),
    'Tunis->Gabes': ((36.8078, 10.1815), (33.8815, 10.0982)),
}

TOL = 1e-5
bad = 0
total = 0
for name, (a, b) in TRIPS.items():
    r = route(a, b)
    steps = (r.get('best_fastest') or {}).get('steps') or []
    wrong = []
    geom_legs = 0
    for s in steps:
        g = s.get('geometry') or []
        if len(g) < 2:
            continue
        geom_legs += 1
        total += 1
        # The polyline must begin at this step's start and end at its end.
        starts_ok = (abs(g[0][0] - s['start'][0]) < TOL and
                     abs(g[0][1] - s['start'][1]) < TOL)
        ends_ok = (abs(g[-1][0] - s['end'][0]) < TOL and
                   abs(g[-1][1] - s['end'][1]) < TOL)
        if not (starts_ok and ends_ok):
            wrong.append((s['type'], s.get('stop_name'), starts_ok, ends_ok,
                          g[0], s['start'], g[-1], s['end']))
    status = 'OK' if not wrong else f'{len(wrong)} WRONG'
    print(f'{name:18s} {len(steps):2d} legs, {geom_legs:2d} with geometry  {status}')
    for w in wrong[:3]:
        print(f'    type={w[0]} stop={w[1]!r} start_ok={w[2]} end_ok={w[3]}')
        print(f'      geom first={w[4]} step start={w[5]}')
        print(f'      geom last ={w[6]} step end  ={w[7]}')
    bad += len(wrong)

print(f'\n{total} geometry legs checked, {bad} mis-oriented')
print('ORIENTATION PASS' if bad == 0 else 'ORIENTATION FAILED')
sys.exit(0 if bad == 0 else 1)
