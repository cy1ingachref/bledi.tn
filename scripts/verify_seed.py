#!/usr/bin/env python3
"""Verify the corrected seed file: its checksum, and the invariants the pipeline guarantees.

The seed is the input to every routing answer, so a silent edit to it is a silent change
to what the app tells people. This script fails when the bytes change, and when the
structure drifts from what the corrected pipeline produced.

The checksum is taken over the file with its line endings normalised to LF, because git
stores it that way: the working copy has CRLF on Windows and LF on the build agents, and
both must hash the same.

Run it with no argument to check. After an intentional regeneration, run it with
--update to print the digests to paste back into EXPECTED_SHA256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"

# The seed the pipeline reads, and the seed it writes.
SOURCE_SEED = DATA / "seed_all_tunisia_routes.tagged.json"
CORRECTED_SEED = DATA / "seed_all_tunisia_routes.CLEANED.corrected.json"

EXPECTED_SHA256 = {
    SOURCE_SEED: "ebcaf874e812982a7178ab7a92f3407c53cf2228b03a471a534d67d8a76bce08",
    CORRECTED_SEED: "ef5afdc8bd45c2a2ff0771946ebd4378aec455e0abd7ba4d0d5f6abe5757af7b",
}

# What the corrected pipeline produced.
EXPECTED_STATIONS = 7451
EXPECTED_LINES = 379
# The rows whose coordinates are unknown, quarantined rather than guessed.
EXPECTED_WITHOUT_COORDS = 7
# The padded bounding box of Tunisia, with the western limit at 7.50 so Hazoua stays in.
BOX = (30.23, 37.56, 7.50, 11.65)
# The correction the pipeline applies: the real Louage & Regional Bus Station footprint.
AIN_DRAHEM = (36.77803, 8.68783)

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")
        failures.append(name)


def digest(path: Path) -> str:
    """The SHA-256 of the file as git stores it: CRLF folded to LF."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_checksums() -> None:
    print("checksums")
    for path, expected in EXPECTED_SHA256.items():
        if not path.is_file():
            check(f"{path.name} exists", False, str(path))
            continue
        actual = digest(path)
        check(f"{path.name} checksum", actual == expected, f"expected {expected}, got {actual}")


def verify_structure() -> None:
    print("structure")
    if not CORRECTED_SEED.is_file():
        check("the corrected seed exists", False, str(CORRECTED_SEED))
        return

    seed = json.loads(CORRECTED_SEED.read_text(encoding="utf-8"))
    stations = seed.get("stations", [])
    lines = seed.get("lines", [])

    check(f"{EXPECTED_STATIONS} stations", len(stations) == EXPECTED_STATIONS, str(len(stations)))
    check(f"{EXPECTED_LINES} lines", len(lines) == EXPECTED_LINES, str(len(lines)))

    ids = [s["id"] for s in stations]
    check("the station ids are unique", len(ids) == len(set(ids)))

    without = [s["id"] for s in stations if not s.get("lat") or not s.get("lon")]
    check(
        f"{EXPECTED_WITHOUT_COORDS} stations without coordinates",
        len(without) == EXPECTED_WITHOUT_COORDS,
        str(without),
    )

    lat_min, lat_max, lon_min, lon_max = BOX
    outside = [
        s["id"]
        for s in stations
        if s.get("lat") and s.get("lon")
        and not (lat_min <= s["lat"] <= lat_max and lon_min <= s["lon"] <= lon_max)
    ]
    check("every station is inside the padded bounding box", not outside, str(outside))

    ain_drahem = [s for s in stations if s["id"] == "ain_drahem"]
    check(
        "ain_drahem keeps its corrected coordinates",
        len(ain_drahem) == 1
        and (ain_drahem[0]["lat"], ain_drahem[0]["lon"]) == AIN_DRAHEM,
        str([(s.get("lat"), s.get("lon")) for s in ain_drahem]),
    )

    check(
        "Hazoua survives the western padding",
        any(s["id"] == "sntri_hazoua_7cfe222ed7" for s in stations),
    )

    metadata = seed.get("metadata", {})
    check(
        "the metadata counts the stations it wrote",
        metadata.get("stations") == len(stations) and metadata.get("lines") == len(lines),
        str(metadata),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="print the current digests instead of checking them",
    )
    args = parser.parse_args()

    if args.update:
        for path in EXPECTED_SHA256:
            if path.is_file():
                print(f"{digest(path)}  {path.name}")
            else:
                print(f"missing: {path}", file=sys.stderr)
        return 0

    verify_checksums()
    verify_structure()

    if failures:
        print(f"\n{len(failures)} check(s) failed", file=sys.stderr)
        return 1
    print("\nthe corrected seed is intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
