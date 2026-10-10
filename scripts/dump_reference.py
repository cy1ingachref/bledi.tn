"""Dump reference values from the Python engine, for Rust-vs-Python parity.

This is the ONLY way to prove the Rust port is faithful: pin the same
numbers on both sides. Run from the repo root:

    python scripts/dump_reference.py > reference.json
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "backend"))

from app import routing as R
from app import road_routing as RR
from app import rail_geometry as RG

# (label, start, end)
OD = [
    ("tunis_carthage", (36.806, 10.184), (36.8928, 10.3230)),
    ("tunis_sousse", (36.806, 10.184), (35.8256, 10.6360)),
    ("tunis_bizerte", (36.806, 10.184), (37.2744, 9.8739)),
    ("sousse_sfax", (35.8256, 10.6360), (34.7406, 10.7603)),
]

MODE_CAR, MODE_FOOT = 1, 2
PROFILE = {"car": MODE_CAR, "foot": MODE_FOOT}


def rd(x, nd=1):
    """Round for a stable textual comparison."""
    return None if x is None else round(float(x), nd)


def main():
    out = {"od": {}}

    rg = RR.load_graph()
    rail = RG.load_rail_graph()
    print("road graph:", rg.n_nodes, "nodes", rg.n_edges, "edges", file=sys.stderr)
    print("rail graph:", rail.n_nodes, "nodes", rail.n_edges, "edges", file=sys.stderr)

    for label, (a_lat, a_lon), (b_lat, b_lon) in OD:
        rec = {"start": [a_lat, a_lon], "end": [b_lat, b_lon]}
        straight = R.haversine(a_lat, a_lon, b_lat, b_lon)
        rec["straight_m"] = rd(straight, 2)

        for mode in ("car", "foot"):
            r = RR.road_route_cached(rg, a_lat, a_lon, b_lat, b_lon, mode)
            rec[f"road_{mode}"] = None if r is None else {
                "distance_m": rd(r.distance_m, 1),
                "duration_s": rd(r.duration_s, 1),
                "n_points": len(r.geometry),
                "first": [round(float(r.geometry[0][0]), 6), round(float(r.geometry[0][1]), 6)],
                "last": [round(float(r.geometry[-1][0]), 6), round(float(r.geometry[-1][1]), 6)],
                "names": r.road_names[:6],
            }
        t = RG.track_between_cached(rail, a_lat, a_lon, b_lat, b_lon)
        rec["rail"] = None if t is None else {
            "distance_m": rd(t.distance_m, 1),
            "n_points": len(t.geometry),
            "first": [round(float(t.geometry[0][0]), 6), round(float(t.geometry[0][1]), 6)],
            "last": [round(float(t.geometry[-1][0]), 6), round(float(t.geometry[-1][1]), 6)],
        }
        out["od"][label] = rec

    # Transit router: one unfiltered search and one full plan, per OD.
    _seed, router = R.build_graph()
    print("stations:", len(router.stations), "adj:", len(router.adj), file=sys.stderr)
    out["graph"] = {
        "stations": len(router.stations),
        "adj_nodes": len(router.adj),
        "walk_edges": sum(1 for l in router.adj.values() for e in l if e.mode == "walk"),
        "transit_edges": sum(1 for l in router.adj.values() for e in l if e.mode != "walk"),
    }
    waits = sorted(router.line_wait.values())
    out["line_wait"] = {
        "n": len(waits),
        "median_s": rd(waits[len(waits) // 2], 1),
        "max_s": rd(waits[-1], 1),
    }

    plans = {}
    routes = {}
    for label, (a_lat, a_lon), (b_lat, b_lon) in OD:
        raw = router.route(a_lat, a_lon, b_lat, b_lon)
        routes[label] = {
            "mode": raw.get("mode"),
            "duration_min": rd(raw.get("duration_min"), 1),
            "n_steps": len(raw.get("steps") or []),
            "types": [s.get("type") for s in (raw.get("steps") or [])],
            "distances_m": [rd(s.get("distance_m"), 0) for s in (raw.get("steps") or [])],
        }
        for objective in ("fastest", "cheapest", "fewest_transfers"):
            plan = router.route_plan(a_lat, a_lon, b_lat, b_lon, objective=objective)
            its = plan.get("itineraries") or []
            plans[f"{label}/{objective}"] = {
                "n": len(its),
                "cards": [
                    {
                        "id": it["id"],
                        "label": it["label"],
                        "rank_reason": it["rank_reason"],
                        "duration_min": rd(it["duration_min"], 1),
                        "transfers": it["transfers"],
                        "fare_estimate_dinars": rd(it["fare_estimate_dinars"], 2),
                        "modes_used": it["modes_used"],
                        "searched_for": it["searched_for"],
                        "geometry_complete": it["geometry_complete"],
                        "n_gaps": len(it["gaps"] or []),
                        "n_legs": len(it["legs"] or []),
                        "leg_types": [l.get("type") for l in (it["legs"] or [])],
                        "leg_lines": [l.get("line") for l in (it["legs"] or [])],
                        "leg_dist_m": [rd(l.get("distance_m"), 0) for l in (it["legs"] or [])],
                        "leg_geom_points": [len(l.get("geometry") or []) for l in (it["legs"] or [])],
                    }
                    for it in its
                ],
            }
    out["routes"] = routes
    out["plans"] = plans

    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()