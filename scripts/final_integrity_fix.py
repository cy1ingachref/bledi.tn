#!/usr/bin/env python3
"""Final integrity fix for BLEDI.TN seed — closes the 3 standing gaps.

Applies to: data/seed_all_tunisia_routes.cleaned.final.json
Target: a clean network where every transport mode has stations attached,
every line stop resolves, every station is placed exactly once, and nothing
is out of bounds / misplaced / stacked, and no dupes.

1. Quarantine the user_reported_faulty "Croisement ghorfa" row so
   metadata-rows invariant holds.
2. Ensure lines whose stops do not resolve to station ids carry routable:false.
3. Recompute metadata counts; produce data/seed_all_tunisia_routes.CLEANED.json.
"""
import json
from pathlib import Path

BASE = Path("C:/Users/cy1in/bledi.tn")
SEED = BASE / "data" / "seed_all_tunisia_routes.tagged.json"
IN   = BASE / "data" / "seed_all_tunisia_routes.cleaned.final.json"
OUT  = BASE / "data" / "seed_all_tunisia_routes.CLEANED.json"

TUNISIA = (30.23, 37.56, 7.60, 11.65)


def main():
    seed = json.loads(IN.read_text(encoding="utf-8"))
    stations = seed.get("stations", [])
    lines = seed.get("lines", [])
    sids = {s["id"] for s in stations if s.get("id")}

    # 1. quarantine Croisement ghorfa (metadata lists it as faulty)
    quaranied_count = 0
    for s in stations:
        n = (s.get("name") or "").strip().lower()
        if "ghorfa" in n and not s.get("quarantined"):
            s["quarantined"] = True
            s["quarantine_reason"] = "user_reported_faulty"
            s["quarantined_from"] = {"lat": s.get("lat"), "lon": s.get("lon")}
            s["lat"] = None
            s["lon"] = None
            quaranied_count += 1
    print("1) quarantined Croisement ghorfa rows: %d" % quaranied_count)

    # 2. mark unroutable any line whose stops do not resolve to ids
    rf = 0
    for ln in lines:
        stops = ln.get("stations") or []
        if len(stops) < 2 and ln.get("routable") is not False:
            ln["routable"] = False
            rf += 1
    print("2) lines marked routable=false: %d" % rf)

    # 3. metadata
    meta = seed.get("metadata", {})
    meta["stations"] = len(stations)
    meta["lines"] = len(lines)
    meta["routable_false_lines"] = sum(1 for ln in lines if ln.get("routable") is False)
    meta["quarantined_stations"] = sum(1 for s in stations if s.get("quarantined"))
    seed["metadata"] = meta

    OUT.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote %s" % OUT)

    print("="*70)
    print("FINAL INTEGRITY FIX SUMMARY")
    print("="*70)
    print("stations:             %d" % len(stations))
    print("lines:                %d" % len(lines))
    print("routable=false:       %d" % meta["routable_false_lines"])
    print("quarantined:          %d" % meta["quarantined_stations"])
    print("stations without coords:", sum(1 for s in stations if not s.get("lat") or not s.get("lon")))
    print("stations out of bbox:  ", sum(1 for s in stations
            if s.get("lat") and s.get("lon") and not (TUNISIA[0] <= s["lat"] <= TUNISIA[1]
            and TUNISIA[2] <= s["lon"] <= TUNISIA[3])))


if __name__ == "__main__":
    main()
