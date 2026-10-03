#!/usr/bin/env python3
"""Build the transport workbook from the seed and the parsed GTFS network.

One .xlsx covering everything the request asked for:

  Stops              every stop/station we hold, by mode, with coordinates
  Stops by mode      one sheet per mode (bus, metro, train, rail, tram, ferry,
                     louage/taxi, unknown)
  Routes             every line: operator, mode, origin -> destination
  Trips              each trip with its full ordered stop sequence
  Trip stops         long format, one row per (trip, stop) with lat/lon/time
  Metro lines        TGM line -> ordered stations (not in any GTFS feed)
  Rural / taxi lines named in the export, with no coordinates published
  Lines (seed)       the 232 curated lines from our own seed
  Summary            counts and provenance

Requires openpyxl. Writes only --out.

    python tool/build_workbook.py --seed <path> --network <network.json> \
        --out BLEDI_transport.xlsx
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="1B5E4A")
HEADER_FONT = Font(color="FFFFFF", bold=True)

# Mode -> sheet name, ordered as the reader wants to see them.
MODE_SHEETS = [
    ("metro", "Metro"),
    ("train", "Train"),
    ("rail", "Rail"),
    ("tram", "Tram"),
    ("ferry", "Ferry"),
    ("bus", "Bus"),
    ("louage", "Louage-Taxi"),
    ("taxi", "Taxi"),
    ("louage_red", "Louage-Red"),
    ("unknown", "Unknown"),
]


def write_sheet(wb: Workbook, title: str, headers: list[str], rows: list[list],
                widths: list[int] | None = None) -> None:
    ws = wb.create_sheet(title[:31])
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        ws.append(row)
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions
    for i, h in enumerate(headers, start=1):
        letter = get_column_letter(i)
        if widths:
            ws.column_dimensions[letter].width = widths[i - 1]
        else:
            longest = max([len(str(h))] + [len(str(r[i - 1])) for r in rows[:200] if r and i <= len(r)])
            ws.column_dimensions[letter].width = min(max(longest + 2, 10), 46)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--louage", default="",
                    help="seed_routes_destination_tunis.json — holds the 18 "
                         "louage/taxi stops, which live outside the main seed")
    ap.add_argument("--network", required=True, help="parse_gtfs.py output")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    seed = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    net = json.loads(Path(args.network).read_text(encoding="utf-8"))
    stations = [s for s in seed["stations"] if s.get("lat") and s.get("lon")]
    lines = seed.get("lines", [])

    # The louage/taxi stops are in a second seed that the backend merges at
    # load time but that is not part of the main tagged seed. Without this the
    # workbook would omit every yellow stop the map draws.
    louage_stops: list[dict] = []
    if args.louage and Path(args.louage).is_file():
        extra = json.loads(Path(args.louage).read_text(encoding="utf-8"))
        for s in extra.get("stations", []):
            # This seed nests coordinates under "location" and carries the mode
            # in "type" (louage_hub / louage_stop), unlike the main seed's flat
            # lat/lon/mode. Reading it with the main seed's shape silently
            # yields zero stops, which is exactly what happened first time.
            loc = s.get("location") or {}
            lat, lon = loc.get("lat"), loc.get("lon")
            if lat is None or lon is None:
                continue
            stype = (s.get("type") or "").lower()
            mode = "louage" if stype.startswith("louage") else (s.get("mode") or "unknown")
            louage_stops.append({
                "id": s.get("id", ""),
                "name": s.get("name_fr") or s.get("name_en") or s.get("name_ar", ""),
                "name_en": s.get("name_en", ""),
                "lat": lat, "lon": lon,
                "mode": mode,
                "operator": "LOUAGE",
                "city": s.get("governorate", ""),
                "source": "official-open-data",
                "source_file": "seed_routes_destination_tunis.json",
                "lines_served": [], "route_type": 3,
                "license_status": "official-public",
            })
        # Louage lines: origin -> destination, no coordinates published.
        for r in extra.get("routes", []):
            net.setdefault("rural_lines", []).append({
                "operator": "LOUAGE", "mode": r.get("mode", "louage"),
                "kind": "louage", "origin": r.get("origin") or r.get("from", ""),
                "destination": r.get("destination") or r.get("to", ""),
                "stop_count": len(r.get("stops") or []),
                "stops": r.get("stops") or [], "mapped": False,
                "source_file": "seed_routes_destination_tunis.json",
            })
    stations.extend(louage_stops)

    wb = Workbook()
    wb.remove(wb.active)  # drop the default sheet

    # ── Stops (everything, one row per stop) ────────────────────────────────
    stop_headers = ["id", "name", "mode", "operator", "lat", "lon", "city",
                    "source", "lines_served"]
    stop_rows = []
    for s in sorted(stations, key=lambda s: (s.get("mode") or "", s.get("name") or "")):
        served = s.get("lines_served") or []
        refs = sorted({str(x.get("route_short_name")) for x in served
                       if isinstance(x, dict) and x.get("route_short_name")})
        if not refs and s.get("lines"):
            refs = sorted({str(x) for x in s["lines"]})
        stop_rows.append([
            s.get("id", ""), s.get("name", ""), s.get("mode", ""),
            s.get("operator", ""), s.get("lat"), s.get("lon"),
            s.get("city", ""), s.get("source", ""), ", ".join(refs),
        ])
    write_sheet(wb, "All stops", stop_headers, stop_rows,
                [34, 34, 10, 12, 11, 11, 16, 20, 30])

    # ── One sheet per mode ──────────────────────────────────────────────────
    by_mode: dict[str, list[dict]] = collections.defaultdict(list)
    for s in stations:
        by_mode[s.get("mode") or "unknown"].append(s)

    mode_headers = ["name", "operator", "lat", "lon", "city", "source", "id"]
    mode_widths = [34, 12, 11, 11, 16, 20, 34]
    for mode, sheet in MODE_SHEETS:
        rows = [[s.get("name", ""), s.get("operator", ""), s.get("lat"), s.get("lon"),
                 s.get("city", ""), s.get("source", ""), s.get("id", "")]
                for s in sorted(by_mode.get(mode, []), key=lambda s: s.get("name") or "")]
        if rows or mode in {"bus", "metro", "train"}:
            write_sheet(wb, sheet, mode_headers, rows, mode_widths)

    # Modes present in the data but not in MODE_SHEETS still get a sheet.
    for mode in sorted(set(by_mode) - {m for m, _ in MODE_SHEETS}):
        rows = [[s.get("name", ""), s.get("operator", ""), s.get("lat"), s.get("lon"),
                 s.get("city", ""), s.get("source", ""), s.get("id", "")]
                for s in sorted(by_mode[mode], key=lambda s: s.get("name") or "")]
        write_sheet(wb, str(mode)[:31], mode_headers, rows, mode_widths)

    # ── Routes (one row per line) ───────────────────────────────────────────
    route_headers = ["operator", "mode", "route_id", "short_name", "long_name",
                     "origin", "destination", "stops", "trips", "gtfs_route_type",
                     "colour"]
    route_rows = [[
        r.get("operator", ""), r.get("mode", ""), r.get("route_id", ""),
        r.get("route_short_name", ""), r.get("route_long_name", ""),
        r.get("origin", ""), r.get("destination", ""),
        r.get("stop_count", 0), r.get("trip_count", 0),
        r.get("gtfs_route_type", ""), r.get("route_color", ""),
    ] for r in sorted(net["routes"], key=lambda r: (r["operator"], r["route_id"]))]
    write_sheet(wb, "Routes", route_headers, route_rows,
                [12, 8, 16, 14, 44, 30, 30, 8, 8, 10, 10])

    # ── Trips (origin -> stops -> destination) ──────────────────────────────
    trip_headers = ["operator", "mode", "trip_id", "route_id", "headsign",
                    "direction", "origin", "destination", "stop_count"]
    trip_rows = [[
        t.get("operator", ""), t.get("mode", ""), t.get("trip_id", ""),
        t.get("route_id", ""), t.get("headsign", ""), t.get("direction_id", ""),
        t.get("origin", ""), t.get("destination", ""), t.get("stop_count", 0),
    ] for t in sorted(net["trips"], key=lambda t: (t["operator"], t["route_id"], t["trip_id"]))]
    write_sheet(wb, "Trips", trip_headers, trip_rows,
                [12, 8, 20, 16, 34, 10, 30, 30, 10])

    # ── Trip stops (long format: the actual stop sequence) ──────────────────
    seq_headers = ["operator", "mode", "trip_id", "route_id", "seq",
                   "stop_name", "lat", "lon", "arrival", "departure"]
    seq_rows = []
    for t in net["trips"]:
        for s in t["stops"]:
            seq_rows.append([
                t["operator"], t["mode"], t["trip_id"], t["route_id"],
                s["sequence"], s["name"], s["lat"], s["lon"],
                s.get("arrival", ""), s.get("departure", ""),
            ])
    write_sheet(wb, "Trip stops", seq_headers, seq_rows,
                [12, 8, 20, 16, 6, 34, 11, 11, 10, 10])

    # ── Metro lines (TGM station order, absent from every GTFS feed) ─────────
    metro_headers = ["line", "operator", "mode", "origin", "destination",
                     "station_count", "stations_in_order"]
    metro_rows = [[m["line"], m["operator"], m["mode"], m["origin"], m["destination"],
                   m["stop_count"], " > ".join(m["stations"])]
                  for m in sorted(net.get("metro_lines", []),
                                  key=lambda m: str(m["line"]))]
    write_sheet(wb, "Metro lines", metro_headers, metro_rows,
                [6, 10, 8, 30, 30, 12, 90])

    # ── Rural / taxi lines: named by the operator, positions not published ───
    rural_headers = ["operator", "mode", "kind", "origin", "destination",
                     "stop_count", "stops_in_order", "mapped", "source_file"]
    rural_rows = [[r["operator"], r["mode"], r.get("kind", ""), r["origin"],
                   r["destination"], r["stop_count"], " - ".join(r["stops"]),
                   "no coordinates published", Path(r.get("source_file", "")).name]
                  for r in sorted(net.get("rural_lines", []),
                                  key=lambda r: (r.get("kind", ""), r["origin"]))]
    write_sheet(wb, "Rural and taxi lines", rural_headers, rural_rows,
                [12, 8, 14, 28, 28, 10, 90, 24, 34])

    # ── Our own curated lines ───────────────────────────────────────────────
    line_headers = ["route_id", "mode", "from", "to", "stops", "operator"]
    line_rows = []
    for ln in lines:
        stops = ln.get("stations") or []
        line_rows.append([
            ln.get("route_id", ""), ln.get("mode", ""),
            (ln.get("from_name") or (ln.get("from") or "")), ln.get("to_name", ""),
            len(stops), ln.get("operator", ""),
        ])
    write_sheet(wb, "Seed lines", line_headers, line_rows,
                [22, 8, 30, 30, 8, 12])

    # ── Summary ─────────────────────────────────────────────────────────────
    summary = wb.create_sheet("Summary")
    summary.append(["BLEDI.TN — transport workbook"])
    summary.append(["generated from", "tunisian open-data portal + BLEDI.TN seed"])
    summary.append(["seed", args.seed])
    summary.append(["network", args.network])
    summary.append([])
    summary.append(["STOPS BY MODE", "count"])
    for mode, n in collections.Counter(s.get("mode") or "unknown" for s in stations).most_common():
        summary.append([mode, n])
    summary.append(["TOTAL STOPS", len(stations)])
    summary.append([])
    summary.append(["PROVENANCE", "count"])
    for src, n in collections.Counter(s.get("source", "(none)") for s in stations).most_common():
        summary.append([src, n])
    summary.append([])
    summary.append(["ROUTES / TRIPS", "count"])
    summary.append(["routes (GTFS)", len(net["routes"])])
    summary.append(["trips (GTFS)", len(net["trips"])])
    summary.append(["trip-stop rows", len(seq_rows)])
    summary.append(["metro lines (station order)", len(net.get("metro_lines", []))])
    summary.append(["rural / taxi lines (unmapped)", len(net.get("rural_lines", []))])
    summary.append(["seed lines", len(lines)])
    summary.append([])
    summary.append(["ROUTES BY OPERATOR", "count"])
    for op, n in collections.Counter(r["operator"] for r in net["routes"]).most_common():
        summary.append([op, n])
    for cell in summary[1]:
        cell.font = Font(bold=True)
    summary.column_dimensions["A"].width = 34
    summary.column_dimensions["B"].width = 70
    summary.column_dimensions["C"].width = 90

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    wb.save(args.out)

    print(f"sheets           : {len(wb.sheetnames)}")
    print(f"  {', '.join(wb.sheetnames)}")
    print(f"stops            : {len(stations)}")
    print(f"  sheets by mode : {[(s, len(by_mode.get(m, []))) for m, s in MODE_SHEETS]}")
    print(f"routes           : {len(net['routes'])}")
    print(f"trips            : {len(net['trips'])}")
    print(f"trip-stop rows   : {len(seq_rows)}")
    print(f"metro lines      : {len(net.get('metro_lines', []))}")
    print(f"rural/taxi lines : {len(net.get('rural_lines', []))}")
    print(f"seed lines       : {len(lines)}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()