#!/usr/bin/env python3
"""Apply the station coordinate corrections from data/station_corrections.json.

Idempotent: re-running changes nothing. Every applied correction is re-tested
against the water index, so a "fix" that still lands in water fails loudly
instead of silently shipping.

    python tool/apply_station_corrections.py            # apply
    python tool/apply_station_corrections.py --dry-run  # show what would change
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))
from audit_station_placement import WaterIndex  # noqa: E402

SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"
CORR = ROOT / "data" / "station_corrections.json"
WATER = ROOT / "data" / "water_polys.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    corr = json.loads(CORR.read_text(encoding="utf-8"))["corrections"]
    idx = WaterIndex(json.loads(WATER.read_text(encoding="utf-8"))["elements"])
    by_id = {s["id"]: s for s in seed["stations"]}

    changes = 0
    failures: list[str] = []
    print(f"{len(corr)} corrections declared\n")

    for c in corr:
        sid = c["id"]
        s = by_id.get(sid)
        if s is None:
            failures.append(f"{sid}: not found in the seed")
            print(f"  MISSING  {sid}")
            continue

        if c["action"] == "quarantine":
            already = bool(s.get("quarantined"))
            if already and s.get("lat") is None and s.get("lon") is None:
                print(f"  already quarantined  {c['name']}")
                continue
            print(f"  QUARANTINE  {c['name']}  ({s.get('lat')}, {s.get('lon')})")
            if not args.dry_run:
                s["quarantined_from"] = {"lat": s.get("lat"), "lon": s.get("lon")}
                s["quarantine_reason"] = c["reason"]
                s["quarantined"] = True
                s["lat"] = None
                s["lon"] = None
            changes += 1

        elif c["action"] == "move":
            if s.get("lat") == c["new_lat"] and s.get("lon") == c["new_lon"]:
                print(f"  already correct  {c['name']}")
                continue
            wet = idx.contains(c["new_lat"], c["new_lon"])
            if wet:
                failures.append(f"{sid}: the NEW coordinate is in water ({wet})")
                print(f"  REFUSED  {c['name']} — new coordinate is in water ({wet})")
                continue
            print(f"  MOVE  {c['name']}  ({s.get('lat')}, {s.get('lon')}) -> "
                  f"({c['new_lat']}, {c['new_lon']})  [on land]")
            if not args.dry_run:
                s.setdefault("corrections", []).append({
                    "field": "lat/lon",
                    "from": {"lat": s.get("lat"), "lon": s.get("lon")},
                    "to": {"lat": c["new_lat"], "lon": c["new_lon"]},
                    "reason": c["reason"],
                    "confidence": c.get("confidence"),
                    "applied": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
                s["lat"] = c["new_lat"]
                s["lon"] = c["new_lon"]
            changes += 1
        else:
            failures.append(f"{sid}: unknown action {c['action']!r}")

    print(f"\nchanges: {changes}   failures: {len(failures)}")
    for f in failures:
        print(f"  FAIL {f}")

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 1 if failures else 0

    if failures:
        print("\nrefusing to write while corrections failed")
        return 1

    # Back up, then write.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = SEED.with_suffix(f".json.bak-{stamp}")
    shutil.copy2(SEED, backup)
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nbacked up -> {backup.name}")
    print(f"wrote {SEED}")

    # Prove the result: no station may sit in water after this.
    after = json.loads(SEED.read_text(encoding="utf-8"))["stations"]
    wet_now = [(s["name"], s.get("lat"), s.get("lon"))
               for s in after
               if s.get("lat") and s.get("lon") and idx.contains(s["lat"], s["lon"])]
    print(f"\nstations still in water: {len(wet_now)}")
    for n, la, lo in wet_now[:30]:
        print(f"  {str(n)[:38]:38s} {la},{lo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
