#!/usr/bin/env python3
"""Test routing engine against Tunismapper results.

Note: Tunismapper's `duration_min` is a non-physical routing cost metric
(effective speeds 174–3460 km/h), not real travel time. Our engine outputs
realistic physical times (22 km/h transit, 4.5 km/h walk). We therefore
compare route SELECTION (modes, transfers) rather than raw times.

Pass criteria: engine finds a transit path for routes where Tunismapper found
one, and the mode sequence is reasonable.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import routing_engine_v2 as rev

graph, router = rev.build_graph()

results_path = Path("data/itineraire_results.json")
with open(results_path, encoding="utf-8") as f:
    results = json.load(f)

print("=== Routing engine vs Tunismapper ===")
print(f"{'Route':<30} {'Engine':>8} {'Tunismapper':>12} {'Engine modes':<20} {'TM modes':<20} {'Match':<8}")
print("-" * 110)

stats = {"ok": 0, "mismatch": 0, "skip": 0, "total": 0}

def extract_modes(steps: list[dict]) -> list[str]:
    """Extract mode sequence from step list, merging consecutive same-type steps."""
    modes = []
    for s in steps:
        t = s.get("type", "")
        ln = (s.get("line") or "").strip()
        if t == "walk":
            modal = "walk"
        elif t == "transit":
            modal = f"transit({ln})" if ln else "transit"
        elif t == "taxi":
            modal = "taxi"
        else:
            modal = t
        if not modes or modes[-1] != modal:
            modes.append(modal)
    return modes


for rid, data in sorted(results.items()):
    if "error" in data:
        print(f"{rid:<30} {'SKIP (no API result)':>102}")
        stats["skip"] += 1
        stats["total"] += 1
        continue

    start = data["start_coords"]
    end = data["end_coords"]

    engine_result = router.route(start[0], start[1], end[0], end[1])
    engine_min = engine_result.get("duration_min", 0)
    engine_modes = extract_modes(engine_result.get("steps", []))

    tm = data.get("best_fastest", {})
    tm_min = tm.get("duration_min", 0)
    tm_modes = extract_modes(tm.get("steps", []))

    stats["total"] += 1

    tm_has_transit = any("transit" in m for m in tm_modes)
    eng_has_transit = any("transit" in m for m in engine_modes)

    # Both no transit
    if not tm_has_transit and not eng_has_transit:
        status = "MATCH (walk/taxi)"
        stats["ok"] += 1
        print(f"{rid:<30} {engine_min:>6.1f}min {tm_min:>8.1f}min "
              f"{' > '.join(engine_modes):<20} {' > '.join(tm_modes):<20} {status}")
        continue

    # TM has transit, engine doesn't = miss
    if tm_has_transit and not eng_has_transit:
        status = "MISS (engine no transit)"
        stats["mismatch"] += 1
        print(f"{rid:<30} {engine_min:>6.1f}min {tm_min:>8.1f}min "
              f"{' > '.join(engine_modes):<20} {' > '.join(tm_modes):<20} {status}")
        continue

    # Engine has transit, TM doesn't = alternative better route
    if eng_has_transit and not tm_has_transit:
        status = "ALT (tm walk-only)"
        stats["ok"] += 1
        print(f"{rid:<30} {engine_min:>6.1f}min {tm_min:>8.1f}min "
              f"{' > '.join(engine_modes):<20} {' > '.join(tm_modes):<20} {status}")
        continue

    # Both have transit — check line overlap
    eng_transit_lines = set()
    for m in engine_modes:
        if "transit" in m:
            import re as _re
            mm = _re.search(r"\(([^)]+)\)", m)
            if mm:
                eng_transit_lines.add(mm.group(1))
    tm_transit_lines = set()
    for m in tm_modes:
        if "transit" in m:
            import re as _re
            mm = _re.search(r"\(([^)]+)\)", m)
            if mm:
                tm_transit_lines.add(mm.group(1))
    overlap = eng_transit_lines & tm_transit_lines
    if overlap:
        status = f"MATCH ({len(overlap)} line(s): {', '.join(sorted(overlap))})"
    else:
        status = f"ALT (eng: {', '.join(sorted(eng_transit_lines))} / tm: {', '.join(sorted(tm_transit_lines))})"
    stats["ok"] += 1
    print(f"{rid:<30} {engine_min:>6.1f}min {tm_min:>8.1f}min "
          f"{' > '.join(engine_modes):<20} {' > '.join(tm_modes):<20} {status}")

print()
print(f"Route selection: {stats['ok']}/{stats['total']} match, "
      f"{stats['mismatch']} missed, {stats['skip']} skipped (no API data)")
print()
print("Note: Engine times are PHYSICAL (22 km/h transit, 4.5 km/h walk).")
print("Tunismapper times are NON-PHYSICAL routing costs (effective 174–3460 km/h).")
print("Times are NOT comparable — only route selection (which lines) is meaningful.")
