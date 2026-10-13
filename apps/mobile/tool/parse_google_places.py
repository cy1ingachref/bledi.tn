#!/usr/bin/env python3
"""Read the Bizerte / Mateur / Ras Jebel workbook into the station JSON.

Source: bizerte_mateur_transport.xlsx — 27 places with WGS84 coordinates and
Google Place IDs, compiled from Google Places listings (user-supplied).

Why this file matters: the operator portal publishes 426 SRT Bizerte station
names and, in every one of its four datasets, zero coordinates. This workbook
supplies coordinates for the terminals, louage stands and taxi stands — the
category the portal never covered at all. Several are the only louage records
anywhere north of Tunis.

Provenance is carried on every record rather than flattened:

  source       "google-places-workbook"
  place_id     Google's stable identifier, kept so records can be re-checked
  source_sheet which sheet the row came from
  type_raw     the workbook's own wording, unmodified

Mode comes from that Type column by explicit keyword rules, never from
proximity. Where the Type is ambiguous the record keeps mode "unknown" and is
reported as such, rather than being forced into a colour.

    python tool/parse_google_places.py --xlsx <file> --out stops.json
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import openpyxl

# Type wording -> our vocabulary. Checked most-specific first: "Louage / Taxi /
# Bus hub" must not be claimed by the plain "bus" rule below it.
TYPE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("louage rural", "rural transport"), "louage"),
    (("bus station",), "bus"),
    (("bus stop", "bus / taxi", "bus/taxi", "bus + taxi"), "bus"),
    (("bus company office", "company office"), "bus"),
    (("train station",), "train"),
    (("taxi station", "taxi stand"), "taxi"),
    (("taxi",), "taxi"),
    (("louage",), "louage"),
    (("intercity",), "bus"),
]

# Sheet -> governorate. Ras Jebel and Mateur both sit in Bizerte governorate;
# the workbook's own Notes sheet says so. Anything unlisted inherits its sheet
# name, which is also the city.
SHEET_GOV = {"Mateur": "Bizerte", "Ras Jebel": "Bizerte"}


def col(header: list[str], *names: str) -> int | None:
    """Index of the first matching column, or None."""
    for n in names:
        if n in header:
            return header.index(n)
    return None


def classify(type_raw: str) -> str:
    """Map the workbook's Type wording to a mode, or 'unknown' if ambiguous.

    A record whose type names several modes at once ("Louage / Taxi / Bus hub")
    is a terminus serving all of them. Routing treats it as the primary mode and
    the app still shows it, so the dominant mode is used and the raw wording is
    preserved in `type_raw` — nothing is lost.
    """
    t = (type_raw or "").strip().lower()
    for needles, mode in TYPE_RULES:
        if any(n in t for n in needles):
            return mode
    return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    wb = openpyxl.load_workbook(args.xlsx, read_only=True, data_only=True)
    records: list[dict] = []
    skipped: list[str] = []

    for sheet in wb.sheetnames:
        if sheet == "Notes":
            continue
        ws = wb[sheet]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(h).strip().lower() if h else "" for h in rows[0]]

        i_name = col(header, "name")
        i_type = col(header, "type")
        i_lat = col(header, "latitude", "lat")
        i_lon = col(header, "longitude", "lon", "lng")
        i_addr = col(header, "address / plus code", "address")
        i_pid = col(header, "google place id", "id", "place_id")
        i_hours = col(header, "hours (per google)", "hours")
        i_notes = col(header, "operator / notes", "notes")
        if i_name is None or i_lat is None or i_lon is None:
            skipped.append(f"{sheet}: header lacks name/lat/lon -> {header[:6]}")
            continue

        for row in rows[1:]:
            name = row[i_name] if i_name < len(row) else None
            lat = row[i_lat] if i_lat < len(row) else None
            lon = row[i_lon] if i_lon < len(row) else None
            if not name or lat is None or lon is None:
                continue
            try:
                lat, lon = float(lat), float(lon)
            except (TypeError, ValueError):
                skipped.append(f"{sheet}: unparseable coordinate {lat},{lon}")
                continue
            if not (30.0 <= lat <= 38.0 and 6.5 <= lon <= 12.5):
                skipped.append(f"{sheet}/{name}: outside Tunisia ({lat},{lon})")
                continue

            def cell(idx: int | None) -> str:
                if idx is None or idx >= len(row) or row[idx] is None:
                    return ""
                return str(row[idx]).strip()

            type_raw = cell(i_type)
            records.append({
                "operator": "GOOGLE-PLACES",
                "mode": classify(type_raw),
                "name": str(name).strip(),
                "lat": lat,
                "lon": lon,
                "governorate": SHEET_GOV.get(sheet, sheet),
                "city": sheet,
                "source_file": Path(args.xlsx).name,
                "source_sheet": sheet,
                "source": "google-places-workbook",
                "place_id": cell(i_pid),
                "type_raw": type_raw,
                "address": cell(i_addr),
                "hours": cell(i_hours),
                "notes": cell(i_notes),
                "license_status": "user-compiled-from-google-places",
            })

    wb.close()
    Path(args.out).write_text(json.dumps(records, ensure_ascii=False, indent=1),
                              encoding="utf-8")

    print(f"records read .................... {len(records)}")
    print(f"wrote {args.out}\n")
    print("by mode:")
    for m, n in collections.Counter(r["mode"] for r in records).most_common():
        print(f"  {m:10s} {n}")
    print("\nby sheet:")
    for s, n in collections.Counter(r["source_sheet"] for r in records).most_common():
        print(f"  {s:12s} {n}")
    print("\nby city:")
    for c, n in collections.Counter(r["city"] for r in records).most_common():
        print(f"  {c:12s} {n}")
    named = sum(1 for r in records if r["name"])
    pids = sum(1 for r in records if r["place_id"])
    print(f"\nwith a name:      {named}/{len(records)}")
    print(f"with a Place ID:  {pids}/{len(records)}")
    unknown = [r for r in records if r["mode"] == "unknown"]
    if unknown:
        print(f"\n{len(unknown)} record(s) left as unknown mode:")
        for r in unknown:
            print(f"  {r['name'][:36]:36s} type_raw={r['type_raw'][:40]!r}")
    if skipped:
        print(f"\n{len(skipped)} row(s) skipped:")
        for s in skipped:
            print(f"  {s}")


if __name__ == "__main__":
    main()