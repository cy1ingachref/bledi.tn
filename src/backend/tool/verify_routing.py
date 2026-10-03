#!/usr/bin/env python3
"""Verify the walk-edge router: long trips are multi-leg, not one taxi line.

Committed rather than kept in a temp dir on purpose. The temp copy was deleted
after its run, which left no artefact and made this verification
indistinguishable from "not re-checked since" -- the same trap
tool/verify_import.py's docstring warns about. Anything written to check this
behaviour belongs here, next to the code it checks.

    python src/backend/tool/verify_routing.py
    python src/backend/tool/verify_routing.py --skip-live

Checks, against the seed and the router built from it:

  1. the graph has walk edges (it had none; a destination stop was reachable
     only if a line happened to call there)
  2. long trips return multi-leg itineraries, and transit wins outright
  3. walk legs render as their own legs, timed at walking speed
  4. taxi is offered as an alternative, never as the answer when transit exists
  5. an unserved destination gets an explicit labelled vehicle hop rather than
     a silent straight line, timed at vehicle speed
  6. optionally, that the live :8000 and :8080 endpoints agree

Exits 0 when every check passes, 1 otherwise. Writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.backend.app.routing import (  # noqa: E402
    DROP_OFF_CANDIDATES,
    MAX_WALK_EDGE_METERS,
    WALK_EDGE,
    Router,
    _load_seed,
)

# No line in the seed serves Kairouan and its nearest line-served station is
# 44.3 km away, so a single taxi leg is the only truthful answer there. Kept in
# the sample to prove the router does not invent a transfer that does not exist.
UNSERVED = "Tunis->Kairouan"

TRIPS: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "Tunis->Sfax": ((36.8078, 10.1815), (34.7406, 10.7603)),
    "Tunis->Bizerte": ((36.8078, 10.1815), (37.2744, 9.8739)),
    "Tunis->La Marsa": ((36.8078, 10.1815), (36.8781, 10.3230)),
    "Tunis->Mahdia": ((36.8078, 10.1815), (34.0622, 11.35)),
    "Sousse->Nabeul": ((35.8256, 10.6360), (36.4560, 10.7376)),
    UNSERVED: ((36.8078, 10.1815), (35.6781, 10.0963)),
}

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{f' — {detail}' if detail else ''}")
    if not ok:
        failures.append(label)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-live", action="store_true", help="skip the HTTP checks")
    args = ap.parse_args()

    t0 = time.time()
    seed = _load_seed()
    router = Router({s["id"]: s for s in seed["stations"]}, seed["lines"])
    edges = sum(len(v) for v in router.adj.values())
    walk = [e for adj in router.adj.values() for e in adj if e[2] == "walk"]

    print(f"1. graph ({time.time() - t0:.2f}s, {edges} edges)")
    check(len(walk) > 1000, "walk edges exist", f"{len(walk)}")
    check(all(e[1] == WALK_EDGE for e in walk), "walk edges carry the sentinel")
    check(all(0 <= e[4] <= MAX_WALK_EDGE_METERS for e in walk), f"within {MAX_WALK_EDGE_METERS} m")
    # Bidirectional: a one-way walk edge would let a route reach a stop it could
    # not then leave, and the asymmetry is invisible in a leg count.
    pairs = {(src, e[0]) for src, adj in router.adj.items() for e in adj if e[2] == "walk"}
    unpaired = [p for p in pairs if (p[1], p[0]) not in pairs]
    check(not unpaired, "walk edges are bidirectional", f"{len(unpaired)} one-way")

    print("\n2. long trips are multi-leg, transit wins")
    routes: dict[str, dict] = {}
    for name, (a, b) in TRIPS.items():
        res = router.route(a[0], a[1], b[0], b[1])
        routes[name] = res
        steps = res.get("steps") or []
        if name == UNSERVED:
            check(res.get("mode") == "taxi", f"{name}: stays taxi (no line serves it)")
            continue
        check(
            not (len(steps) == 1 and steps[0].get("type") == "taxi"),
            f"{name}: not one straight taxi leg",
            f"{res.get('mode')}, {len(steps)} legs",
        )
        check(res.get("mode") == "transit", f"{name}: transit wins", str(res.get("mode")))

    print("\n3. walk legs render at walking speed")
    steps = routes["Tunis->Sfax"]["steps"]
    kinds = {s["type"] for s in steps}
    check({"walk", "ride"} <= kinds, "itinerary mixes walk and ride")
    interior = [s for i, s in enumerate(steps) if s["type"] == "walk" and 0 < i < len(steps) - 1]
    check(bool(interior), "walk legs between rides (transfer handovers)", f"{len(interior)}")
    brisk = [
        s
        for s in steps
        if s["type"] == "walk"
        and s.get("distance_m", 0) > 0
        and s.get("duration_min", 0) > 0
        and (s["distance_m"] / 1000) / (s["duration_min"] / 60) > 12
    ]
    check(not brisk, "no walk leg above 12 km/h", f"{len(brisk)} suspicious")

    print("\n4. taxi is an alternative, not the answer")
    alts = routes["Tunis->Sfax"].get("alternatives") or []
    check(any(a.get("mode") == "taxi" for a in alts), "taxi offered alongside transit")
    near = router.route(36.806, 10.184, 36.815, 10.184)
    offered = {s["type"] for s in near.get("steps") or []} | {
        a.get("mode") for a in (near.get("alternatives") or [])
    }
    check("taxi" not in offered, "short hop gains no taxi leg")

    print("\n5. unserved destination gets a labelled vehicle hop")
    hops = [s for s in routes["Tunis->Mahdia"]["steps"] if s.get("note") == "no_stop_near_destination"]
    if check(bool(hops), "explicit hop leg present, not a silent straight line"):
        for h in hops:
            kmh = (h["distance_m"] / 1000) / (h["duration_min"] / 60)
            check(h["type"] != "walk", "hop not labelled a walk", f"{h['distance_m'] / 1000:.1f} km")
            check(20 < kmh < 80, "hop at vehicle speed", f"{kmh:.1f} km/h")
    check(DROP_OFF_CANDIDATES == 1, "drop-off limited to nearest served station")

    if not args.skip_live:
        print("\n6. live endpoints agree")
        for port in (8000, 8080):
            url = (
                f"http://127.0.0.1:{port}/api/v1/route/transit"
                "?start_lat=36.8078&start_lon=10.1815&end_lat=34.7406&end_lon=10.7603"
            )
            try:
                bf = json.loads(urllib.request.urlopen(url, timeout=90).read())["best_fastest"]
            except Exception as exc:  # noqa: BLE001
                check(False, f":{port} reachable", str(exc))
                continue
            legs = bf.get("steps") or []
            check(len(legs) > 5, f":{port} multi-leg itinerary", f"{len(legs)} legs")
            check({"walk", "ride"} <= {s["type"] for s in legs}, f":{port} mixes walk and ride")
            check(
                not (len(legs) == 1 and legs[0]["type"] == "taxi"),
                f":{port} not one straight taxi line",
            )

    print("\n" + ("ALL CHECKS PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
