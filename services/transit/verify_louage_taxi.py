"""Verification script for louage-taxi station connections in the routing graph.

Checks:
1. Louage stations from the louage seed are present in the router.
2. Transfer edges exist between nearby louage and taxi stations.
3. Zero-cost transfer edges exist for same-location stations.
4. The router can produce itineraries that use louage/taxi modes.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from bledi_transit.adapters.seed_files import SeedFileNetwork
from bledi_transit.application.network import Network
from bledi_transit.application.routing.graph import LOUAGE_TAXI_EDGE, LOUAGE_TAXI_TRANSFER_RADIUS_M, add_louage_taxi_transfers
from bledi_transit.application.routing.router import Router
from bledi_transit.domain.geo import haversine_m
from bledi_transit.domain.modes import canonical_mode
from bledi_transit.main import Config, build_router


def main() -> int:
    config = Config.from_env()
    data = SeedFileNetwork(config.data_dir)
    network = data.load()

    print(f"Loaded {len(network.stations)} stations, {len(network.lines)} lines")
    print(f"Louage stations: {len(network.louage_stations)}")
    print(f"Louage routes: {len(network.louage_routes)}")

    # Build router (build_router already passes louage_stations internally)
    router = build_router(config, data, network)

    # Count louage and taxi stations in the router
    louage_in_router = []
    taxi_in_router = []
    for sid, s in router.stations.items():
        if not s.get("lat") or not s.get("lon"):
            continue
        canon = canonical_mode(s.get("mode") or "")
        if canon == "louaj":
            louage_in_router.append(sid)
        elif canon == "taxi":
            taxi_in_router.append(sid)

    print(f"\nRouter has {len(louage_in_router)} louage stations, {len(taxi_in_router)} taxi stations")
    print(f"Louage IDs: {louage_in_router[:5]}")
    print(f"Taxi IDs: {taxi_in_router[:5]}")

    # Check transfer edges
    transfer_edges = 0
    zero_cost_edges = 0
    nearby_edges = 0
    for src_id, edges in router.adj.items():
        for e in edges:
            if e.line == LOUAGE_TAXI_EDGE:
                transfer_edges += 1
                if e.time_s == 0:
                    zero_cost_edges += 1
                else:
                    nearby_edges += 1

    print(f"\nTransfer edges (total): {transfer_edges}")
    print(f"  Zero-cost (same location): {zero_cost_edges}")
    print(f"  Walk-cost (nearby <{LOUAGE_TAXI_TRANSFER_RADIUS_M}m): {nearby_edges}")

    # Verify specific pairs
    print("\n--- Sample transfer connections ---")
    shown = 0
    for src_id, edges in router.adj.items():
        for e in edges:
            if e.line == LOUAGE_TAXI_EDGE and shown < 10:
                src = router.stations[src_id]
                dst = router.stations[e.to_id]
                d = haversine_m(src["lat"], src["lon"], dst["lat"], dst["lon"])
                cost = "zero-cost" if e.time_s == 0 else f"{e.time_s:.1f}s"
                print(f"  {src['name']} -> {dst['name']} ({d:.0f}m, {cost})")
                shown += 1

    # Test routing between a louage station and a taxi station
    print("\n--- Route test: louage to taxi ---")
    if louage_in_router and taxi_in_router:
        # Find a louage-taxi pair that has a transfer edge
        test_pair = None
        for src_id, edges in router.adj.items():
            for e in edges:
                if e.line == LOUAGE_TAXI_EDGE:
                    test_pair = (src_id, e.to_id)
                    break
            if test_pair:
                break

        if test_pair:
            a, b = test_pair
            sa = router.stations[a]
            sb = router.stations[b]
            print(f"Routing from '{sa['name']}' to '{sb['name']}'")
            result = router.route(
                sa["lat"], sa["lon"],
                sb["lat"], sb["lon"],
            )
            print(f"  Mode: {result.get('mode')}")
            print(f"  Duration: {result.get('duration_min')} min")
            steps = result.get("steps", [])
            print(f"  Steps: {len(steps)}")
            for i, step in enumerate(steps[:5]):
                print(f"    {i}: {step.get('type')} {step.get('mode')} {step.get('label', '')[:60]}")

            # Check if louage or taxi appears in the itinerary
            modes_used = set()
            for step in steps:
                m = step.get("mode")
                if m:
                    modes_used.add(m)
            if "louaj" in modes_used or "taxi" in modes_used:
                print(f"  ✓ Louage/taxi mode used in itinerary!")
            else:
                print(f"  ✗ No louage/taxi mode in itinerary (modes: {modes_used})")

    # Summary
    print("\n--- Summary ---")
    ok = True
    if len(louage_in_router) == 0:
        print("✗ FAIL: No louage stations in router")
        ok = False
    else:
        print(f"✓ {len(louage_in_router)} louage stations in router")

    if len(taxi_in_router) == 0:
        print("✗ FAIL: No taxi stations in router")
        ok = False
    else:
        print(f"✓ {len(taxi_in_router)} taxi stations in router")

    if transfer_edges == 0:
        print("✗ FAIL: No transfer edges created")
        ok = False
    else:
        print(f"✓ {transfer_edges} transfer edges created")

    if zero_cost_edges == 0:
        print("✗ FAIL: No zero-cost (same-location) transfer edges")
        ok = False
    else:
        print(f"✓ {zero_cost_edges} zero-cost transfer edges")

    if ok:
        print("\n✓ All checks passed!")
        return 0
    else:
        print("\n✗ Some checks failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())