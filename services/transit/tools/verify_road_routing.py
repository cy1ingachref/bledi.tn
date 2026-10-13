"""Verify real-road routing on the Tunisia graph, and that it beats a line.

Run:  python services/transit/tools/verify_road_routing.py

Every check is an assertion on measured output. If this file prints PASS, the
numbers quoted below came from this graph on this machine.
"""

from __future__ import annotations

import os
import time

from bledi_transit.adapters.graphs.road_graph import MODE_COL, _snap, load_graph, road_route
from bledi_transit.domain.geo import haversine_m

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH = os.path.abspath(os.path.join(HERE, "..", "..", "..", "data", "road_graph.npz"))

# Real places in Tunisia with well-known coordinates.
PLACES = {
    "tunis_carthage": (36.8528, 10.3233),
    "tunis_centre": (36.8065, 10.1815),
    "sfax": (34.7406, 10.7603),
    "sousse": (35.8256, 10.6360),
    "sidi_bouzid": (35.3767, 9.4850),
    "kairouan": (35.6781, 10.0963),
    "bizerte": (37.2744, 9.8739),
    "nabeul": (36.4561, 10.7376),
    "gabes": (33.8815, 10.0982),
    "djerba": (33.8076, 10.8451),
    "el_batin": (36.3000, 10.2000),
    "test_far_offshore": (36.9000, 11.5000),  # ~60 km out in the Gulf of Hammamet
}

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def straight_m(a, b) -> float:
    return haversine_m(a[0], a[1], b[0], b[1])


def max_offroad_m(geom, a, b) -> float:
    """How far the worst vertex strays from the straight origin->dest line."""
    if len(geom) < 2:
        return float("inf")
    worst = 0.0
    for lat, lon in geom[1:-1]:
        d = straight_m((lat, lon), a) + straight_m((lat, lon), b)
        worst = max(worst, (d - straight_m(a, b)) / 2.0)
    return worst


def main() -> int:
    t0 = time.time()
    g = load_graph(GRAPH)
    if g is None:
        print("FAIL  graph not found at", GRAPH)
        return 1
    load_s = time.time() - t0
    print(
        f"graph: {g.n_nodes:,} nodes, {g.n_edges:,} directed edges, loaded in {load_s:.1f}s"
    )
    for mode in MODE_COL:
        print(
            f"  {mode:5s} {g.csr_edge[mode].size:>12,} directed edges, "
            f"max speed {g.speed_mps[mode][g.csr_edge[mode]].max() * 3.6:5.1f} km/h, "
            f"grid cells {g.grid[mode]['n_lat']}x{g.grid[mode]['n_lon']}"
        )
    check("graph has >5M nodes", g.n_nodes > 5_000_000, f"{g.n_nodes:,}")
    # foot edges > car edges is correct and expected: every footway, path and
    # steps is walkable but not drivable, while motorway/trunk links are the
    # reverse. This check exists to catch a mode filter that collapsed.
    check(
        "both modes present and distinct",
        len({g.csr_edge[m].size for m in MODE_COL}) == len(MODE_COL),
        ", ".join(f"{m}={g.csr_edge[m].size:,}" for m in MODE_COL),
    )
    check(
        "foot-only ways (footway/steps) are walkable",
        g.csr_edge["foot"].size > g.csr_edge["car"].size,
        f"foot {g.csr_edge['foot'].size:,} > car {g.csr_edge['car'].size:,}",
    )

    # --- snap accuracy -------------------------------------------------
    print("\n-- snapping a known point to the nearest road --")
    for key in ("tunis_carthage", "sfax", "sousse"):
        lat, lon = PLACES[key]
        sa = _snap(g, "car", lat, lon, 250.0)
        check(
            f"snap {key} within 250m",
            sa is not None and sa[1] <= 250.0,
            "" if sa is None else f"{sa[1]:.1f} m",
        )

    # A point in the sea must NOT snap to a road.
    sea = _snap(g, "car", *PLACES["test_far_offshore"], 250.0)
    check("offshore point refuses to snap", sea is None,
          "" if sea is None else f"snapped {sea[1]:.1f} m (expected None)")

    # --- real routes --------------------------------------------------
    print("\n-- real-road routes (Tunis -> ?) --")
    origin = PLACES["tunis_carthage"]
    pairs = [
        ("sousse", "car"),
        ("sfax", "car"),
        ("kairouan", "car"),
        ("bizerte", "car"),
        ("nabeul", "car"),
        ("sidi_bouzid", "car"),
        ("sousse", "foot"),
    ]
    routed = []
    for dest_key, mode in pairs:
        dest = PLACES[dest_key]
        t1 = time.time()
        r = road_route(g, origin[0], origin[1], dest[0], dest[1], mode)
        dt = (time.time() - t1) * 1000
        if r is None:
            check(f"{origin_key_label()} -> {dest_key} [{mode}]", False, "no route")
            continue
        s = straight_m(origin, dest)
        ratio = r.distance_m / s
        off = max_offroad_m(r.geometry, origin, dest)
        # A real road route must be longer than the straight line (unless the
        # two points share a road) and must not be absurdly longer.
        check(
            f"{dest_key} [{mode}] real road route",
            r.distance_m >= s * 0.98 and ratio < 4.0,
            f"straight {s/1000:.1f}km -> road {r.distance_m/1000:.1f}km "
            f"(x{ratio:.2f}), {len(r.geometry)} pts, {dt:.0f}ms, "
            f"snap {r.snap_from_m:.0f}/{r.snap_to_m:.0f}m, "
            f"roads={len(r.road_names)}",
        )
        check(
            f"{dest_key} [{mode}] geometry is not the straight line",
            off > 20.0 or ratio > 1.02,
            f"max deviation from direct line {off:.0f} m",
        )
        check(
            f"{dest_key} [{mode}] stays on land (bounded deviation)",
            off < s * 0.5 + 3000,
            f"max deviation {off:.0f} m",
        )
        routed.append((dest_key, mode, s, r))

    check("most long routes found", len(routed) >= 6, f"{len(routed)}/{len(pairs)}")

    # --- sanity: a short urban hop should be barely longer than the line ---
    print("\n-- short hop sanity --")
    # two points ~3 km apart in Tunis
    a = (36.8065, 10.1815)
    b = (36.8300, 10.1900)
    r = road_route(g, a[0], a[1], b[0], b[1], "car")
    if r is None:
        check("short Tunis hop routes", False, "no route")
    else:
        s = straight_m(a, b)
        check(
            "short Tunis hop plausible",
            0.98 <= r.distance_m / s < 1.9,
            f"straight {s:.0f}m -> road {r.distance_m:.0f}m (x{r.distance_m / s:.2f}), "
            f"{len(r.geometry)} pts",
        )

    # --- connectivity: is the network one component or shards? ---------
    print("\n-- graph connectivity (does a long route actually exist?) --")
    far_pairs = [("djerba", "bizerte"), ("gabes", "nabeul")]
    for a_key, b_key in far_pairs:
        r = road_route(g, *PLACES[a_key], *PLACES[b_key], "car")
        check(
            f"{a_key} -> {b_key} connected by road",
            r is not None,
            "no route" if r is None else f"{r.distance_m / 1000:.0f} km",
        )

    print("\n" + "=" * 60)
    if fails:
        print(f"FAILED {len(fails)} check(s):")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


def origin_key_label() -> str:
    return "carthage"


if __name__ == "__main__":
    raise SystemExit(main())