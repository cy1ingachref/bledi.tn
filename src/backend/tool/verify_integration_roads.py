"""End-to-end check that app/routing.py now emits real road polylines.

Run:  python src/backend/tool/verify_integration_roads.py

Loads the real router over the real seed data and asserts that the access
walk, the final leg and the taxi leg all carry a polyline that follows the
road graph, instead of two points joined by a straight line.
"""

from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "app"))
sys.path.insert(0, APP)

import routing  # noqa: E402

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def max_offroad_m(geom, a, b) -> float:
    if len(geom) < 2:
        return float("inf")
    base = routing.haversine(a[0], a[1], b[0], b[1])
    worst = 0.0
    for lat, lon in geom[1:-1]:
        d = routing.haversine(lat, lon, a[0], a[1]) + routing.haversine(lat, lon, b[0], b[1])
        worst = max(worst, (d - base) / 2.0)
    return worst


def main() -> int:
    t0 = time.time()
    graph, router = routing.build_graph()
    check("router built", router is not None, f"{len(graph['stations'])} stations in {time.time() - t0:.1f}s")
    check("road graph attached", router.road_graph is not None,
          "" if router.road_graph is None else f"{router.road_graph.n_nodes:,} road nodes")

    trips = [
        ("Tunis centre -> Carthage", 36.8065, 10.1815, 36.8528, 10.3233),
        ("Tunis -> Sousse", 36.8065, 10.1815, 35.8256, 10.6360),
        ("Sfax -> Sidi Bouzid", 34.7406, 10.7603, 35.3767, 9.4850),
    ]
    total_geom = 0
    straight_only = 0
    for label, a_lat, a_lon, b_lat, b_lon in trips:
        t1 = time.time()
        res = router.route(a_lat, a_lon, b_lat, b_lon)
        dt = time.time() - t1
        # Router.route() returns the winning itinerary at the top level plus
        # alternatives; there is no "options" array. Collect both.
        opts = [res] + list(res.get("alternatives") or [])
        legs = 0
        straight_only = 0
        with_geom = 0
        worse: list = []
        for opt in opts:
            for step in opt.get("steps") or []:
                g = step.get("geometry")
                if not g:
                    continue
                legs += 1
                with_geom += 1
                total_geom += 1
                frm = step.get("from") or {}
                to = step.get("to") or {}
                if not (frm.get("lat") is not None and to.get("lat") is not None):
                    continue
                off = max_offroad_m(g, (frm["lat"], frm["lon"]), (to["lat"], to["lon"]))
                # Only the legs this change touches are asserted on: walks
                # (access/final/transfer) and taxi. A 2-point polyline on a bus
                # or rail ride comes from the precomputed transit cache
                # data/route_geometry.json and is real track data, not a
                # straight-line fallback -- flagging those would be measuring
                # the wrong thing.
                if step.get("type") in ("walk", "taxi") and off < 1.0 and len(g) <= 2:
                    straight_only += 1
                    worse.append((step.get("type"), frm, to, len(g)))
        check(
            f"{label}: walk/taxi legs are real roads, not lines",
            legs > 0 and straight_only == 0,
            f"{with_geom} legs with geometry across {len(opts)} itineraries, "
            f"{straight_only} straight-line, {dt:.1f}s"
            + (f" -- offenders {worse[:2]}" if worse else ""),
        )
        # Distances must not be below the straight line: no route can be shorter.
        bad = []
        for opt in opts:
            for step in opt.get("steps") or []:
                d = step.get("distance_m")
                s = step.get("straight_m")
                if d is not None and s is not None and d < 0.95 * s:
                    bad.append((step.get("type"), d, s))
        check(f"{label}: no leg shorter than its straight line", not bad, str(bad[:3]))

    check("total legs with geometry > 0", total_geom > 0, f"{total_geom} legs")

    print("\n-- direct module check on a taxi leg --")
    live = routing.road_leg(router, 36.8065, 10.1815, 35.8256, 10.6360, "car")
    check("road_leg returns a route", live is not None)
    if live:
        geom, dist = live
        check(
            "taxi leg geometry follows roads",
            len(geom) > 5 and dist > 100000,
            f"{len(geom)} pts, {dist / 1000:.1f} km",
        )
    # offshore must refuse rather than invent
    none_case = routing.road_leg(router, 36.90, 11.50, 36.8065, 10.1815, "car")
    check("offshore origin refuses to invent a road", none_case is None,
          "" if none_case is None else f"got {len(none_case[0])} pts")

    print("\n" + "=" * 60)
    if fails:
        print(f"FAILED {len(fails)} check(s):")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("ALL INTEGRATION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())