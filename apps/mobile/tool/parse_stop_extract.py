#!/usr/bin/env python3
"""Parse the Tunisia transit stop extract into structured JSON.

Input is the plain-text extract produced from Overpass (ODbL 1.0). Records are
delimited by a `===` rule; each field is an indented `key : value` line, and a
record starts with its bare name on a line of its own.

Writes JSON that `compare_with_reference.py` can consume, and prints a summary
so a parse that silently drops half the file is visible immediately.

    python tool/parse_stop_extract.py --in stops.txt --out stops.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Field keys seen in the extract, mapped onto stable names.
FIELD_MAP = {
    "for": "mode",
    "location": "latlon",
    "name/fr": "name_fr",
    "name/ar": "name_ar",
    "name/en": "name_en",
    "city": "city",
    "routes": "routes",
    "operator": "operator",
    "osm": "osm_ref",
    "verify": "osm_url",
    "area": "area",
    "kind": "kind",
}

# "TUNIS?"-style suffixes mean the extract's author inferred the mode from text.
UNCONFIRMED = re.compile(r"\?$")

# Section banners: "TUNISIA - EVERY BUS STOP, ...", "--- Tunis ---",
# "GRAND TUNIS LIGHT RAIL - METRO & TRAM STATIONS (...)". All-caps alone is not
# enough — real stop names are all-caps too ("FINANCES MANSOURAH - ALLER"), so a
# heading must also contain the " - " separator the extract uses for them.
_HEADING_WORDS = re.compile(
    r" - .*(?:STATIONS?|STOPS?|RAIL|METRO|SECTION|RECORDS?|TUNISIA)", re.IGNORECASE
)


def is_heading(text: str) -> bool:
    if " - " not in text:
        return False
    if not text.isupper() and not _HEADING_WORDS.search(text):
        return False
    # A stop name never carries a record-count or coordinate payload on the
    # heading line, and headings in this extract are followed by a `---` or `===`
    # rule; requiring the separator plus a mode-ish keyword is enough to tell
    # "GRAND TUNIS LIGHT RAIL - METRO & TRAM STATIONS" from
    # "FINANCES MANSOURAH - ALLER" (no mode keyword).
    return bool(_HEADING_WORDS.search(text))


def parse(in_path: Path) -> list[dict]:
    lines = in_path.read_text(encoding="utf-8", errors="replace").splitlines()

    records: list[dict] = []
    cur: dict | None = None
    pending_name: str | None = None
    in_records = False

    for raw in lines:
        line = raw.rstrip()

        # Section banners look like "TUNISIA - EVERY ..." or
        # "GRAND TUNIS LIGHT RAIL - ...". Start collecting after the summary.
        if line.startswith("===") or line.startswith("---"):
            continue
        if not line.strip():
            continue

        # A field line: "    key : value"
        field = re.match(r"^\s{4}([\w/ ]+?)\s*:\s*(.*)$", line)
        if field and cur is not None:
            raw_key = field.group(1).strip()
            key = FIELD_MAP.get(raw_key, raw_key)
            cur[key] = field.group(2).strip()
            if key == "latlon":
                parts = cur["latlon"].replace(",", " ").split()
                if len(parts) >= 2:
                    try:
                        cur["lat"], cur["lon"] = float(parts[0]), float(parts[1])
                    except ValueError:
                        pass
            continue

        # A bare line is a record name (or a section heading).
        stripped = line.strip()
        if not line.startswith(" "):
            if is_heading(stripped):
                in_records = True
                cur = None
                pending_name = None
                continue
            if in_records:
                cur = {"name": stripped}
                pending_name = stripped
                records.append(cur)

    return [r for r in records if "lat" in r and "lon" in r]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    args = ap.parse_args()

    records = parse(Path(args.inp))
    Path(args.out).write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    total_lines = len(Path(args.inp).read_text(encoding="utf-8", errors="replace").splitlines())
    print(f"input lines          : {total_lines}")
    print(f"records parsed       : {len(records)}")
    print(f"records with coords  : {len(records)}")
    print(f"dropped (no coords)  : {len(records) == 0}")

    import collections

    modes = collections.Counter(r["mode"].split()[0] if r.get("mode") else "?" for r in records)
    print("\nby mode:")
    for m, n in modes.most_common():
        print(f"  {m:18s} {n}")

    unconfirmed = [r for r in records if UNCONFIRMED.search(r.get("mode", ""))]
    print(f"\nunconfirmed modes ('?') : {len(unconfirmed)}")

    unnamed = [r for r in records if "(UNNAMED STOP)" in r.get("name", "").upper()]
    print(f"unnamed stops           : {len(unnamed)}")

    named = [r for r in records if r.get("name_fr") or r.get("name_en")]
    print(f"records with a latin name: {len(named)}")

    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()