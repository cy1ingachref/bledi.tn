#!/usr/bin/env python3
"""Investigate stations that appear both quarantined and placed.

The audit reported Ajim, Bir Mouzaina, Douane Bir Mouzaina and Ain Drahem as
having NO coordinates, and also as being inside water polygons. Both cannot be
true of one row, so there must be more than one row per name. This finds out.

    python tool/inspect_quarantine_overlap.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"

NAMES = ["ajim", "bir mouzaina", "douane bir mouzaina", "ain drahem", "croisement ghorfa"]


def main() -> int:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    stations = data["stations"]

    print(f"stations: {len(stations)}")
    quarantined = [s for s in stations if s.get("quarantined")]
    print(f"rows with quarantined=true: {len(quarantined)}")
    for s in quarantined:
        print(f"  {str(s.get('id'))[:44]:44s} {str(s.get('name'))[:24]:24s} "
              f"lat={s.get('lat')} lon={s.get('lon')}")
        print(f"      reason={str(s.get('quarantine_reason'))[:70]}")
        print(f"      from={str(s.get('quarantined_from'))[:70]}")

    print()
    for name in NAMES:
        rows = [s for s in stations if (s.get("name") or "").strip().lower() == name]
        print(f"=== rows named {name!r}: {len(rows)}")
        for s in rows:
            print(f"  id={str(s.get('id'))[:46]:46s} lat={s.get('lat')} lon={s.get('lon')} "
                  f"q={bool(s.get('quarantined'))} src={s.get('source')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
