#!/usr/bin/env python3
"""Validate a derived OPEN seed (separate from the legacy verify_seed.py).

Usage: python scripts/verify_open_seed.py [path/to/seed_open_source.json]

Checks: schema, unique ids, every line stop resolves, Tunisia bounds, and
license_status in the allowed set (odbl, official-public). Exits non-zero on
failure. The open-profile provenance gate in CI uses this script.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SEED = REPO / "data" / "seed_open_source.json"
BOX = (30.23, 37.56, 7.50, 11.65)
ALLOWED_LICENSES = {"odbl", "official-public"}


def in_bounds(lat, lon) -> bool:
    return (
        isinstance(lat, (int, float)) and isinstance(lon, (int, float))
        and BOX[0] <= lat <= BOX[1] and BOX[2] <= lon <= BOX[3]
    )


def validate(data: dict) -> list[str]:
    failures: list[str] = []
    for key in ("metadata", "stations", "lines"):
        if key not in data:
            failures.append(f"missing top-level key: {key}")
    if failures:
        return failures

    stations = data["stations"]
    lines = data["lines"]
    if not isinstance(stations, list) or not isinstance(lines, list):
        return ["stations and lines must be lists"]

    ids = [s.get("id") for s in stations]
    if len(ids) != len(set(ids)):
        failures.append("duplicate station ids")
    for i, s in enumerate(stations):
        if not s.get("id"):
            failures.append(f"station {i} has no id")
        if not in_bounds(s.get("lat"), s.get("lon")):
            failures.append(f"station {s.get('id')} outside Tunisia bounds")
        if s.get("license_status") not in ALLOWED_LICENSES:
            failures.append(f"station {s.get('id')} bad license_status {s.get('license_status')!r}")

    station_ids = set(ids)
    for line in lines:
        if not line.get("id"):
            failures.append("a line has no id")
        if line.get("license_status") not in ALLOWED_LICENSES:
            failures.append(f"line {line.get('id')} bad license_status")
        stops = line.get("stops") or []
        if len(stops) < 2:
            failures.append(f"line {line.get('id')} has fewer than 2 stops")
        missing = [sid for sid in stops if sid not in station_ids]
        if missing:
            failures.append(f"line {line.get('id')} has unresolved stops: {missing[:3]}")
    return failures


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SEED
    if not path.is_file():
        print(f"ERROR: open seed not found: {path}", file=sys.stderr)
        return 2
    data = json.loads(path.read_text(encoding="utf-8"))
    failures = validate(data)
    if failures:
        print(f"open seed INVALID ({len(failures)} failures):")
        for f in failures[:40]:
            print("  FAIL", f)
        return 1
    print(f"open seed OK: {len(data['stations'])} stations, {len(data['lines'])} lines, all ODbL/official-public")
    return 0


if __name__ == "__main__":
    sys.exit(main())
