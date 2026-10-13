#!/usr/bin/env python3
"""Inspect the louage seed's route endpoints against its own station list.

The audit found route endpoints that name no station. This resolves each one
against (a) the louage station ids, (b) the louage station names, and
(c) the main transit seed's stop names, so we can say whether a route points
at a real place that is merely missing from the station list, or at something
that is not a place at all.

    python tool/inspect_louage_endpoints.py
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOUAGE = ROOT / "data" / "seed_routes_destination_tunis.json"
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"


def norm(s: str) -> str:
    return " ".join((s or "").lower().replace("-", " ").replace("_", " ").split())


def main() -> int:
    lou = json.loads(LOUAGE.read_text(encoding="utf-8"))
    stations = lou.get("stations", [])
    routes = lou.get("routes", [])

    ids = {s.get("id") for s in stations}
    names = {norm(s.get("name_fr") or "") for s in stations} | {
        norm(s.get("name_en") or "") for s in stations
    }

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    transit_names = {norm(s.get("name") or "") for s in seed["stations"]}

    print(f"louage stations: {len(stations)}  routes: {len(routes)}")
    print(f"station ids: {sorted(i for i in ids if i)}")
    print()

    refs = collections.Counter()
    for r in routes:
        for w in ("from", "to"):
            v = (r.get(w) or "").strip()
            if v:
                refs[v] += 1

    dangling = []
    for endpoint, n in refs.most_common():
        if endpoint in ids:
            continue
        in_names = norm(endpoint) in names
        in_transit = norm(endpoint) in transit_names
        # A near-miss: does any station name contain the endpoint or vice versa?
        fuzzy = [s.get("name_fr") for s in stations
                 if s.get("name_fr") and (norm(endpoint) in norm(s["name_fr"])
                                          or norm(s["name_fr"]) in norm(endpoint))]
        dangling.append({
            "endpoint": endpoint, "routes": n,
            "matches_louage_name": in_names,
            "matches_transit_stop_name": in_transit,
            "fuzzy_louage": fuzzy[:3],
        })

    print(f"=== endpoints naming NO louage station id: {len(dangling)} ===")
    for d in dangling:
        flags = []
        if d["matches_louage_name"]:
            flags.append("name==a louage station")
        if d["matches_transit_stop_name"]:
            flags.append("name==a transit stop")
        if d["fuzzy_louage"]:
            flags.append(f"fuzzy->{d['fuzzy_louage']}")
        print(f"  {d['endpoint'][:34]:34s} x{d['routes']:2d}  {'; '.join(flags) or 'NOTHING MATCHES'}")

    # Which routes are affected, and is the route therefore unusable?
    bad_routes = [r for r in routes
                  if (r.get("from") or "").strip() not in ids
                  or (r.get("to") or "").strip() not in ids]
    print(f"\nroutes with at least one dangling endpoint: {len(bad_routes)} of {len(routes)}")
    for r in bad_routes[:15]:
        print(f"  {str(r.get('from'))[:22]:22s} -> {str(r.get('to'))[:22]:22s} "
              f"{str(r.get('mode')):12s} {r.get('fare_display')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
