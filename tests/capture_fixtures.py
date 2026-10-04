"""Capture example API responses as committed fixtures (deliverable F).

Run:  python tests/capture_fixtures.py     (server must be up on :8000)

Writes trimmed JSON fixtures to tests/fixtures/:
  station_multi_mode.json   station served by more than one mode
  itinerary_bus_only.json   bus-only filtered plan
  line_with_geometry_gap.json  a line whose track is incomplete

Geometry arrays are trimmed (first/last N points) because the point is the
SHAPE of the contract, not the payload size.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import urllib.request

# Run from the repo root, or make the package importable regardless of cwd.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

BASE = os.environ.get("BLED_API", "http://127.0.0.1:8000/api/v1")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

KEEP = 6  # points kept at each end of a trimmed polyline


def get(path: str) -> Any:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def trim_geometry(obj: Any, keep: int = KEEP) -> Any:
    """Replace long [[lat,lon],...] arrays with head + '...' + tail."""
    if isinstance(obj, dict):
        return {k: trim_geometry(v, keep) for k, v in obj.items()}
    if isinstance(obj, list):
        if (
            obj
            and all(isinstance(x, (list, tuple)) and len(x) == 2 for x in obj)
            and len(obj) > keep * 2
        ):
            return obj[:keep] + [["..."]] + obj[-keep:]
        return [trim_geometry(x, keep) for x in obj]
    return obj


def write(name: str, payload: Any) -> None:
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        size = os.path.getsize(path)
    print(f"  wrote {name} ({size / 1024:.1f} KB)")


def main() -> int:
    print(f"capturing fixtures from {BASE}")

    # 1. A station served by more than one mode.
    from src.backend.app.main import ROUTER  # noqa: E402

    target = None
    for sid, lids in ROUTER.lines_by_station.items():
        modes = {
            ROUTER.user_mode_of_line.get(lid)
            for lid in lids
            if lid in ROUTER.user_mode_of_line
        }
        modes.discard(None)
        if len(modes) >= 2:
            target = sid
            break
    if target is None:
        print("  SKIP station_multi_mode: no multi-mode station in the seed")
    else:
        print(f"  station with multiple modes: {target}")
        write("station_multi_mode.json", get(f"/stations/{target}"))

    # 2. A bus-only plan.
    plan = get(
        "/route/plan?start_lat=36.7961&start_lon=10.18055"
        "&end_lat=36.75978&end_lon=10.19059&modes_include=bus&max_itineraries=5"
    )
    write("itinerary_bus_only.json", trim_geometry(plan))

    # 3. A line whose geometry has an explicit gap.
    from src.backend.app.main import LINE_BY_ID  # noqa: E402

    gap_line = None
    for lid in LINE_BY_ID:
        try:
            d = get(f"/lines/{lid}")
        except Exception:
            continue
        if d.get("gaps"):
            gap_line = lid
            write("line_with_geometry_gap.json", trim_geometry(d))
            break
    if gap_line is None:
        print("  NOTE no line with a geometry gap found")

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())