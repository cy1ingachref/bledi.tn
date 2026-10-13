#!/usr/bin/env python3
"""Correct seed station modes against the OSM audit.

Applies the one confirmed error from docs/osm-stop-audit.md:

    SLIMENE KEHIA (36.8033, 10.0991) — seed says `metro`, OSM maps it as a bus
    stop (`bus=yes`, `highway=bus_stop`, `public_transport=stop_position`) with
    no rail node within 250 m.

Writes a corrected copy of the seed rather than mutating the original in place,
and prints a diff so the change is reviewable. Refuses to overwrite unless
--out is given.

    python tool/fix_seed_modes.py --seed <in> --out <corrected.json>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# Stations whose seed mode is contradicted by OSM. Each entry must state why,
# so the list cannot grow silently.
CORRECTIONS = {
    "slimene_kehia": {
        "from": "metro",
        "to": "bus",
        "reason": (
            "OSM tags this node bus=yes + highway=bus_stop + "
            "public_transport=stop_position, with no railway=* node within "
            "250 m. Sole genuine mode error in the 2026-10-02 audit."
        ),
    },
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--out", required=True, help="where to write the corrected seed")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="write --out (without it, only a dry-run diff is printed)",
    )
    args = ap.parse_args()

    data = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in data["stations"] if s.get("id")}

    changed, skipped = [], []
    for sid, fix in CORRECTIONS.items():
        station = by_id.get(sid)
        if station is None:
            skipped.append((sid, "not present in seed"))
            continue
        current = station.get("mode")
        if current == fix["to"]:
            skipped.append((sid, f"already {fix['to']}"))
            continue
        if current != fix["from"]:
            skipped.append(
                (sid, f"mode is {current!r}, expected {fix['from']!r} — left alone")
            )
            continue
        station["mode"] = fix["to"]
        # Keep the audit trail on the record itself.
        station["mode_source"] = "osm-audit"
        station["mode_corrected_from"] = fix["from"]
        changed.append((sid, fix["from"], fix["to"]))

    print(f"=== corrections ===")
    for sid, old, new in changed:
        print(f"  {sid}: {old} -> {new}")
    for sid, why in skipped:
        print(f"  {sid}: SKIPPED ({why})")

    if not changed:
        print("\nnothing to change")

    if args.apply:
        # Match the seed's existing formatting: 2-space indent, no trailing
        # whitespace changes. Reformatting the whole 2.2 MB file would turn a
        # one-line correction into a 177 000-line diff.
        out = Path(args.out)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if out.is_file():
            original = out.read_text(encoding="utf-8")
            if original.endswith("\n") and not text.endswith("\n"):
                text += "\n"
        out.write_text(text, encoding="utf-8")
        print(f"\nwrote {args.out}")
    else:
        print("\ndry run — pass --apply to write the corrected seed")


if __name__ == "__main__":
    main()