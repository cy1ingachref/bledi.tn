#!/usr/bin/env python3
"""Import routes, trips, and schedules from GTFS feeds, BLEDI_transport.xlsx,
and PDF timetables into the bledi.tn seed file.

Reads:
  - 4 GTFS zip feeds (SNTRI, SORETRAK, TRANSTU, SRTJ)
  - BLEDI_transport.xlsx (Routes, Trips, Trip stops, Metro lines sheets)
  - transtu_tebourba_bus_lines_2018.csv (PDF timetable extraction)

Merges into seed_all_tunisia_routes.tagged.json:
  - New stations (unmatched by name + coordinates)
  - New lines (unmatched by operator + route number/name)
  - Schedule data on existing lines (departures, first/last times)
  - Station lines_served arrays updated

Usage:
    python scripts/import_routes_schedules.py --dry-run
    python scripts/import_routes_schedules.py --write
"""
from __future__ import annotations

import argparse
import csv
import difflib
import io
import json
import math
import os
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"
DUMP = Path(os.environ.get(
    "BLEDI_OPERATOR_EXPORTS",
    Path.home() / "Downloads" / "tunisia-transport-data" / "01-bus-network" / "operator-exports",
))
TOLERANCE_M = 150.0
CELL = 0.002  # ~220 m grid cell

# GTFS route_type → mode
GTFS_TYPE_MAP = {
    "0": "tram",
    "1": "subway",
    "2": "train",
    "3": "bus",
    "4": "ferry",
}

# Operator name normalisation
OPERATOR_ALIASES = {
    "sntri": "SNTRI",
    "soretrak": "SORETRAK",
    "transtu": "TRANSTU",
    "srtj": "SRTJ",
    "tgm": "TGM",
    "sncft": "SNCFT",
    "societe nationale de transport interurbain": "SNTRI",
    "société nationale de transport interurbain": "SNTRI",
    "societe regionale de transport de kairouan": "SORETRAK",
    "société régionale de transport de kairouan": "SORETRAK",
    "jendouba": "SRTJ",
    "societe des transports de tunis": "TRANSTU",
    "société des transports de tunis": "TRANSTU",
}

# Folder name → operator short name (fallback)
FOLDER_OPERATOR_MAP = {
    "sntri": "SNTRI",
    "soretrak": "SORETRAK",
    "transtu": "TRANSTU",
    "srtj": "SRTJ",
    "tgm": "TGM",
    "sncft": "SNCFT",
}


def norm_operator(op: str) -> str:
    op_stripped = op.strip()
    # Try exact alias match
    short = OPERATOR_ALIASES.get(op_stripped.lower())
    if short:
        return short
    # Try partial match
    for alias, short in OPERATOR_ALIASES.items():
        if alias in op_stripped.lower():
            return short
    return op_stripped.upper()


def detect_operator_from_path(path: Path) -> str:
    """Detect operator from the parent folder name."""
    folder = path.parent.name.lower()
    for key, op in FOLDER_OPERATOR_MAP.items():
        if key in folder:
            return op
    return ""


def hav(a: float, b: float, c: float, d: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def slug(t: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "_" for c in t)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")[:44] or "stop"


def num(v) -> float | None:
    if v is None:
        return None
    s = str(v).replace(",", ".").strip()
    if not s or s.lower() in ("nan", "none", "-", ""):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    if f != f or f in (0.0,):
        return None
    return f


def valid(la: float | None, lo: float | None) -> bool:
    return la is not None and lo is not None and 30.0 < la < 38.0 and 7.0 < lo < 12.0


def norm_name(s: str) -> str:
    """Normalise a station/stop name for fuzzy matching."""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def name_similarity(a: str, b: str) -> float:
    """Fuzzy name similarity using token overlap + subset/substring matching."""
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return 0.0
    # Exact match
    if na == nb:
        return 1.0
    # Token overlap
    ta = set(na.split())
    tb = set(nb.split())
    inter = len(ta & tb)
    union = len(ta | tb)
    token_sim = inter / union if union else 0.0
    # Subset matching: one name's tokens are a subset of the other
    subset_sim = 0.0
    if ta and tb:
        if ta.issubset(tb) or tb.issubset(ta):
            subset_sim = 0.85
    # Substring matching for single tokens or spelling variants
    substr_sim = 0.0
    if len(ta) == 1 and len(tb) == 1:
        sa, sb = next(iter(ta)), next(iter(tb))
        if sa in sb or sb in sa:
            substr_sim = 0.8
        else:
            substr_sim = difflib.SequenceMatcher(None, sa, sb).ratio()
    return max(token_sim, subset_sim, substr_sim)


def norm_operator(op: str) -> str:
    op = op.strip()
    return OPERATOR_ALIASES.get(op.lower(), op.upper())


# ── GTFS parsing ─────────────────────────────────────────────────────────────

def read_gtfs_zip(zip_path: Path) -> dict | None:
    """Read a GTFS zip and return parsed tables, or None if invalid."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError):
        return None

    result = {"path": zip_path, "operator": "", "stops": {}, "routes": {},
              "trips": {}, "stop_times": []}

    with zf:
        names = {n.lower(): n for n in zf.namelist() if not n.endswith("/")}

        # agency.txt → operator name
        if "agency.txt" in names:
            raw = zf.read(names["agency.txt"])
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    rows = list(csv.DictReader(io.StringIO(raw.decode(enc))))
                    if rows:
                        result["operator"] = rows[0].get("agency_name", "").strip()
                    break
                except (UnicodeDecodeError, csv.Error):
                    continue

        # stops.txt
        if "stops.txt" in names:
            raw = zf.read(names["stops.txt"])
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    for row in csv.DictReader(io.StringIO(raw.decode(enc))):
                        sid = row.get("stop_id", "").strip()
                        if sid:
                            result["stops"][sid] = {
                                "name": row.get("stop_name", "").strip(),
                                "lat": num(row.get("stop_lat")),
                                "lon": num(row.get("stop_lon")),
                            }
                    break
                except (UnicodeDecodeError, csv.Error):
                    continue

        # routes.txt
        if "routes.txt" in names:
            raw = zf.read(names["routes.txt"])
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    for row in csv.DictReader(io.StringIO(raw.decode(enc))):
                        rid = row.get("route_id", "").strip()
                        if rid:
                            rtype = row.get("route_type", "3").strip()
                            result["routes"][rid] = {
                                "short_name": row.get("route_short_name", "").strip(),
                                "long_name": row.get("route_long_name", "").strip(),
                                "type": GTFS_TYPE_MAP.get(rtype, "bus"),
                                "color": row.get("route_color", "").strip() or None,
                            }
                    break
                except (UnicodeDecodeError, csv.Error):
                    continue

        # trips.txt
        if "trips.txt" in names:
            raw = zf.read(names["trips.txt"])
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    for row in csv.DictReader(io.StringIO(raw.decode(enc))):
                        tid = row.get("trip_id", "").strip()
                        if tid:
                            result["trips"][tid] = {
                                "route_id": row.get("route_id", "").strip(),
                                "headsign": row.get("trip_headsign", "").strip(),
                                "direction_id": row.get("direction_id", "").strip(),
                            }
                    break
                except (UnicodeDecodeError, csv.Error):
                    continue

        # stop_times.txt
        if "stop_times.txt" in names:
            raw = zf.read(names["stop_times.txt"])
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    for row in csv.DictReader(io.StringIO(raw.decode(enc))):
                        result["stop_times"].append({
                            "trip_id": row.get("trip_id", "").strip(),
                            "stop_id": row.get("stop_id", "").strip(),
                            "stop_sequence": int(row.get("stop_sequence", "0") or "0"),
                            "departure_time": row.get("departure_time", "").strip(),
                            "arrival_time": row.get("arrival_time", "").strip(),
                        })
                    break
                except (UnicodeDecodeError, csv.Error, ValueError):
                    continue

    # Validate: need at least stops + routes
    if not result["stops"] or not result["routes"]:
        return None
    return result


def build_gtfs_lines(feed: dict) -> list[dict]:
    """Build line entries from a parsed GTFS feed."""
    lines = []
    stop_times_by_trip: dict[str, list[dict]] = defaultdict(list)
    for st in feed["stop_times"]:
        stop_times_by_trip[st["trip_id"]].append(st)

    for route_id, route in feed["routes"].items():
        # Collect all trips for this route
        route_trips = [
            tid for tid, t in feed["trips"].items()
            if t["route_id"] == route_id
        ]
        if not route_trips:
            continue

        # Build station sequence from first trip's stop_times
        first_trip_id = route_trips[0]
        trip_stops = sorted(
            stop_times_by_trip.get(first_trip_id, []),
            key=lambda x: x["stop_sequence"],
        )
        if not trip_stops:
            continue

        station_ids = []
        departures = []
        for ts in trip_stops:
            stop = feed["stops"].get(ts["stop_id"])
            if not stop:
                continue
            # We'll match/create stations later; use a temp key
            station_ids.append({
                "stop_id": ts["stop_id"],
                "name": stop["name"],
                "lat": stop["lat"],
                "lon": stop["lon"],
            })
            dep = ts["departure_time"] or ts["arrival_time"]
            if dep:
                # Normalise "24:51:00" → "24:51" (keep as string)
                parts = dep.split(":")
                if len(parts) >= 2:
                    dep = f"{int(parts[0]):02d}:{parts[1]}"
                departures.append(dep)
            else:
                departures.append("")

        if not station_ids:
            continue

        op = norm_operator(feed["operator"]) if feed["operator"] else "UNKNOWN"
        short = route["short_name"] or route_id
        long_name = route["long_name"] or short

        lines.append({
            "operator": op,
            "mode": route["type"],
            "route_id": route_id,
            "short_name": short,
            "long_name": long_name,
            "color": route["color"],
            "stations": station_ids,  # temp: list of dicts
            "departures": departures,
            "source": f"gtfs:{feed['path'].parent.name}",
            "license_status": "official-open-data",
        })

    return lines


# ── XLSX parsing ─────────────────────────────────────────────────────────────

def read_xlsx_sheet(path: Path, sheet_name: str) -> list[dict]:
    """Read a sheet from BLEDI_transport.xlsx as list of dicts."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name not in wb.sheetnames:
            return []
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(min_row=1, values_only=True))
        if not rows:
            return []
        headers = [str(h).strip() if h else f"col{i}" for i, h in enumerate(rows[0])]
        result = []
        for row in rows[1:]:
            if all(v is None for v in row):
                continue
            result.append(dict(zip(headers, row)))
        return result
    finally:
        wb.close()


def build_bledi_lines(xlsx_path: Path) -> list[dict]:
    """Build line entries from BLEDI_transport.xlsx Routes + Trips + Trip stops."""
    routes = read_xlsx_sheet(xlsx_path, "Routes")
    trips = read_xlsx_sheet(xlsx_path, "Trips")
    trip_stops = read_xlsx_sheet(xlsx_path, "Trip stops")

    if not routes:
        return []

    # Index trip stops by (trip_id) and by (route_id)
    stops_by_trip: dict[str, list[dict]] = defaultdict(list)
    stops_by_route: dict[str, list[dict]] = defaultdict(list)
    for ts in trip_stops:
        tid = str(ts.get("trip_id", "")).strip()
        rid = str(ts.get("route_id", "")).strip()
        seq = int(ts.get("seq", 0) or 0)
        stops_by_trip[tid].append({
            "seq": seq,
            "stop_name": str(ts.get("stop_name", "")).strip(),
            "lat": num(ts.get("lat")),
            "lon": num(ts.get("lon")),
            "arrival": str(ts.get("arrival", "") or "").strip(),
            "departure": str(ts.get("departure", "") or "").strip(),
        })
        stops_by_route[rid].append({
            "seq": seq,
            "stop_name": str(ts.get("stop_name", "")).strip(),
            "lat": num(ts.get("lat")),
            "lon": num(ts.get("lon")),
            "arrival": str(ts.get("arrival", "") or "").strip(),
            "departure": str(ts.get("departure", "") or "").strip(),
        })

    # Sort each group by seq
    for k in stops_by_trip:
        stops_by_trip[k].sort(key=lambda x: x["seq"])
    for k in stops_by_route:
        stops_by_route[k].sort(key=lambda x: x["seq"])

    lines = []
    for route in routes:
        op = norm_operator(str(route.get("operator", "")))
        mode = str(route.get("mode", "bus")).strip().lower()
        route_id = str(route.get("route_id", "")).strip()
        short_name = str(route.get("short_name", "") or "").strip()
        long_name = str(route.get("long_name", "") or "").strip()
        origin = str(route.get("origin", "") or "").strip()
        destination = str(route.get("destination", "") or "").strip()
        colour = str(route.get("colour", "") or "").strip() or None
        gtfs_type = str(route.get("gtfs_route_type", "3") or "3").strip()

        if not route_id:
            continue

        # Use route-level stops if available, else fall back to first trip
        route_stops = stops_by_route.get(route_id, [])
        if not route_stops:
            # Find first trip for this route
            route_trips = [t for t in trips if str(t.get("route_id", "")).strip() == route_id]
            if route_trips:
                first_tid = str(route_trips[0].get("trip_id", "")).strip()
                route_stops = stops_by_trip.get(first_tid, [])

        if not route_stops:
            continue

        station_ids = []
        departures = []
        for s in route_stops:
            station_ids.append({
                "stop_id": "",
                "name": s["stop_name"],
                "lat": s["lat"],
                "lon": s["lon"],
            })
            dep = s["departure"] or s["arrival"]
            if dep:
                # Normalise "03:52:00" → "03:52"
                parts = dep.split(":")
                if len(parts) >= 2:
                    dep = f"{int(parts[0]):02d}:{parts[1]}"
                departures.append(dep)
            else:
                departures.append("")

        # Determine mode from gtfs_route_type if mode is generic
        if mode in ("bus", ""):
            mode = GTFS_TYPE_MAP.get(gtfs_type, "bus")

        lines.append({
            "operator": op,
            "mode": mode,
            "route_id": route_id,
            "short_name": short_name or route_id,
            "long_name": long_name or short_name or route_id,
            "color": colour,
            "origin": origin,
            "destination": destination,
            "stations": station_ids,
            "departures": departures,
            "source": "bledi_transport_xlsx",
            "license_status": "official-open-data",
        })

    return lines


# ── Tebourba CSV parsing ─────────────────────────────────────────────────────

def parse_tebourba_csv(csv_path: Path) -> list[dict]:
    """Parse the Tebourba bus lines CSV (extracted from PDF timetable)."""
    if not csv_path.exists():
        return []
    raw = csv_path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        return []

    text = text.lstrip("\ufeff")
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") > first.count(",") else ","

    lines = []
    for row in csv.DictReader(io.StringIO(text), delimiter=delim):
        line_num = str(row.get("line", "") or "").strip()
        if not line_num:
            continue
        lines.append({
            "line_number": line_num,
            "origin_fr": (row.get("origin_fr") or "").strip(),
            "destination_fr": (row.get("destination_fr") or "").strip(),
            "first_to_station": (row.get("first_to_station") or "").strip(),
            "first_to_neighborhood": (row.get("first_to_neighborhood") or "").strip(),
            "last_to_station": (row.get("last_to_station") or "").strip(),
            "last_to_neighborhood": (row.get("last_to_neighborhood") or "").strip(),
        })
    return lines


# ── Seed matching ────────────────────────────────────────────────────────────

class SeedIndex:
    """Index of existing seed stations and lines for matching."""

    def __init__(self, seed: dict):
        self.stations = seed["stations"]
        self.lines = seed["lines"]
        self.station_by_id = {s["id"]: s for s in self.stations}

        # Grid index for coordinate lookup
        self.grid: dict[tuple[int, int], list[tuple[float, float, str]]] = {}
        for s in self.stations:
            la, lon = num(s.get("lat")), num(s.get("lon"))
            if valid(la, lon):
                key = (round(la / CELL), round(lon / CELL))
                self.grid.setdefault(key, []).append((la, lon, s["id"]))

        # Line index: (operator, number) → line
        self.line_by_key: dict[tuple[str, str], dict] = {}
        for l in self.lines:
            op = l.get("operator", "").upper()
            num_val = str(l.get("number", l.get("route_id", ""))).strip()
            self.line_by_key[(op, num_val)] = l

    def find_station(self, name: str, lat: float | None, lon: float | None) -> str | None:
        """Find matching station ID by name + coordinate proximity."""
        if lat is None or lon is None:
            return None

        ci, cj = round(lat / CELL), round(lon / CELL)
        best_id = None
        best_dist = TOLERANCE_M

        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for sla, slo, sid in self.grid.get((ci + di, cj + dj), ()):
                    d = hav(lat, lon, sla, slo)
                    if d <= best_dist:
                        # Also check name similarity
                        station = self.station_by_id.get(sid)
                        if station:
                            sim = name_similarity(name, station.get("name", ""))
                            if sim >= 0.3 or d < 50:  # very close = match regardless
                                best_dist = d
                                best_id = sid

        return best_id

    def find_line(self, operator: str, short_name: str, long_name: str = "") -> dict | None:
        """Find matching existing line by operator + route number/name."""
        op = operator.upper()
        # Try exact number match
        key = (op, short_name)
        if key in self.line_by_key:
            return self.line_by_key[key]

        # Try case-insensitive
        for (l_op, l_num), line in self.line_by_key.items():
            if l_op == op and l_num.lower() == short_name.lower():
                return line

        # Try name similarity on long_name
        if long_name:
            best_line = None
            best_sim = 0.0
            for line in self.lines:
                if line.get("operator", "").upper() != op:
                    continue
                line_name = line.get("name", "")
                sim = name_similarity(long_name, line_name)
                if sim > best_sim and sim >= 0.5:
                    best_sim = sim
                    best_line = line
            if best_line:
                return best_line

        return None


# ── Main import logic ────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Import routes and schedules into bledi.tn seed")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be done without modifying seed")
    ap.add_argument("--write", action="store_true", help="Actually modify the seed file")
    args = ap.parse_args()
    if not (args.dry_run or args.write):
        ap.error("pass --dry-run or --write")

    if not DUMP.exists():
        print(f"ERROR: dump not found: {DUMP}", file=sys.stderr)
        return 2

    if not SEED.exists():
        print(f"ERROR: seed not found: {SEED}", file=sys.stderr)
        return 2

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    index = SeedIndex(seed)

    print(f"Seed: {len(seed['stations'])} stations, {len(seed['lines'])} lines")
    print()

    # ── 1. Parse GTFS feeds ──────────────────────────────────────────────────
    print("=== GTFS feeds ===")
    gtfs_lines: list[dict] = []
    gtfs_zips = sorted(DUMP.rglob("*.zip"))
    for z in gtfs_zips:
        feed = read_gtfs_zip(z)
        if not feed:
            print(f"  SKIP {z.name[:60]} (invalid zip)")
            continue
        # Use folder-based operator if agency name is unknown
        if not feed["operator"] or norm_operator(feed["operator"]) == feed["operator"].upper():
            folder_op = detect_operator_from_path(z)
            if folder_op:
                feed["operator"] = folder_op
        lines = build_gtfs_lines(feed)
        op = norm_operator(feed["operator"]) if feed["operator"] else "UNKNOWN"
        print(f"  {op:10s} {len(feed['stops']):4d} stops, {len(feed['routes']):3d} routes, "
              f"{len(feed['trips']):3d} trips, {len(feed['stop_times']):4d} stop_times → {len(lines)} lines")
        gtfs_lines.extend(lines)

    # ── 2. Parse BLEDI_transport.xlsx ───────────────────────────────────────
    print("\n=== BLEDI_transport.xlsx ===")
    xlsx_path = DUMP / "BLEDI_transport.xlsx"
    bledi_lines: list[dict] = []
    if xlsx_path.exists():
        bledi_lines = build_bledi_lines(xlsx_path)
        print(f"  Routes sheet → {len(bledi_lines)} lines with stops")
    else:
        print("  SKIP (file not found)")

    # ── 3. Parse Tebourba CSV ───────────────────────────────────────────────
    print("\n=== Tebourba PDF timetables ===")
    tebourba_csv = DUMP / "transtu_tebourba_bus_lines_2018.csv"
    tebourba_lines = parse_tebourba_csv(tebourba_csv)
    print(f"  {len(tebourba_lines)} bus lines with first/last departure times")

    # ── 4. Merge into seed ──────────────────────────────────────────────────
    print("\n=== Merging ===")

    new_stations: list[dict] = []
    new_lines: list[dict] = []
    updated_lines = 0
    updated_stations = 0
    existing_station_ids = {s["id"] for s in seed["stations"]}
    existing_line_ids = {l["id"] for l in seed["lines"]}

    # Build a grid index that includes new stations for dedup
    new_grid: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def find_or_create_station(name: str, lat: float | None, lon: float | None,
                               prefix: str) -> str | None:
        """Find existing station or create a new one. Returns station ID."""
        if lat is None or lon is None:
            return None

        # Check existing seed
        sid = index.find_station(name, lat, lon)
        if sid:
            return sid

        # Check new stations we're adding
        ci, cj = round(lat / CELL), round(lon / CELL)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for sla, slo in new_grid.get((ci + di, cj + dj), ()):
                    if hav(lat, lon, sla, slo) <= TOLERANCE_M:
                        # Find the station ID for this coordinate
                        for ns in new_stations:
                            if abs(num(ns.get("lat")) - sla) < 0.0001 and \
                               abs(num(ns.get("lon")) - slo) < 0.0001:
                                return ns["id"]

        # Create new station
        base_id = f"{prefix}_{slug(name)}"
        sid = base_id
        n = 1
        while sid in existing_station_ids or any(s["id"] == sid for s in new_stations):
            sid = f"{base_id}_{n}"
            n += 1

        new_stations.append({
            "id": sid,
            "name": name,
            "name_en": name,
            "lat": lat,
            "lon": lon,
            "mode": "bus",  # will be updated
            "operator": "",
            "lines_served": [],
            "source": prefix,
            "license_status": "official-open-data",
        })
        existing_station_ids.add(sid)
        new_grid.setdefault((ci, cj), []).append((lat, lon))
        return sid

    # Process GTFS lines
    gtfs_added = 0
    gtfs_updated = 0
    for gl in gtfs_lines:
        op = gl["operator"]
        short = gl["short_name"]
        long_name = gl["long_name"]

        # Match to existing line
        existing = index.find_line(op, short, long_name)

        # Resolve station IDs
        station_ids = []
        for s in gl["stations"]:
            sid = find_or_create_station(s["name"], s["lat"], s["lon"], f"gtfs_{op.lower()}")
            if sid:
                station_ids.append(sid)

        if existing:
            # Update existing line with schedule data if missing
            changed = False
            if not existing.get("departures") and gl["departures"]:
                existing["departures"] = gl["departures"]
                changed = True
            if not existing.get("stations") and station_ids:
                existing["stations"] = station_ids
                changed = True
            # Add schedule field with first/last
            if gl["departures"]:
                first_dep = next((d for d in gl["departures"] if d), None)
                last_dep = next((d for d in reversed(gl["departures"]) if d), None)
                if first_dep and last_dep:
                    sched = existing.get("schedule", {})
                    if not sched.get("first_departure"):
                        sched["first_departure"] = first_dep
                        changed = True
                    if not sched.get("last_departure"):
                        sched["last_departure"] = last_dep
                        changed = True
                    if changed:
                        existing["schedule"] = sched
            if changed:
                gtfs_updated += 1
                updated_lines += 1
        else:
            # Create new line
            line_id = f"gtfs_{op.lower()}_{slug(short)}"
            n = 1
            while line_id in existing_line_ids:
                line_id = f"gtfs_{op.lower()}_{slug(short)}_{n}"
                n += 1

            new_line = {
                "id": line_id,
                "number": short,
                "name": f"Ligne {short}: {long_name}" if long_name != short else f"Ligne {short}",
                "operator": op,
                "mode": gl["mode"],
                "type": "urban" if gl["mode"] in ("metro", "tram", "subway") else "intercity",
                "route_id": gl["route_id"],
                "stations": station_ids,
                "departures": gl["departures"],
                "source": gl["source"],
                "license_status": gl["license_status"],
            }
            if gl.get("color"):
                new_line["color"] = gl["color"]
            new_lines.append(new_line)
            existing_line_ids.add(line_id)
            gtfs_added += 1

    # Process BLEDI xlsx lines
    bledi_added = 0
    bledi_updated = 0
    for bl in bledi_lines:
        op = bl["operator"]
        short = bl["short_name"]
        long_name = bl["long_name"]

        existing = index.find_line(op, short, long_name)

        station_ids = []
        for s in bl["stations"]:
            sid = find_or_create_station(s["name"], s["lat"], s["lon"], f"bledi_{op.lower()}")
            if sid:
                station_ids.append(sid)

        if existing:
            changed = False
            if not existing.get("departures") and bl["departures"]:
                existing["departures"] = bl["departures"]
                changed = True
            if not existing.get("stations") and station_ids:
                existing["stations"] = station_ids
                changed = True
            if bl["departures"]:
                first_dep = next((d for d in bl["departures"] if d), None)
                last_dep = next((d for d in reversed(bl["departures"]) if d), None)
                if first_dep and last_dep:
                    sched = existing.get("schedule", {})
                    if not sched.get("first_departure"):
                        sched["first_departure"] = first_dep
                        changed = True
                    if not sched.get("last_departure"):
                        sched["last_departure"] = last_dep
                        changed = True
                    if changed:
                        existing["schedule"] = sched
            if changed:
                bledi_updated += 1
                updated_lines += 1
        else:
            line_id = f"bledi_{op.lower()}_{slug(short)}"
            n = 1
            while line_id in existing_line_ids:
                line_id = f"bledi_{op.lower()}_{slug(short)}_{n}"
                n += 1

            new_line = {
                "id": line_id,
                "number": short,
                "name": f"Ligne {short}: {long_name}" if long_name != short else f"Ligne {short}",
                "operator": op,
                "mode": bl["mode"],
                "type": "urban" if bl["mode"] in ("metro", "tram", "subway") else "intercity",
                "route_id": bl["route_id"],
                "stations": station_ids,
                "departures": bl["departures"],
                "source": bl["source"],
                "license_status": bl["license_status"],
            }
            if bl.get("color"):
                new_line["color"] = bl["color"]
            if bl.get("origin"):
                new_line["origin"] = bl["origin"]
            if bl.get("destination"):
                new_line["destination"] = bl["destination"]
            new_lines.append(new_line)
            existing_line_ids.add(line_id)
            bledi_added += 1

    # Process Tebourba CSV — match to existing TRANSTU lines
    tebourba_updated = 0
    for tb in tebourba_lines:
        line_num = tb["line_number"]
        # Try to match to existing TRANSTU line
        existing = index.find_line("TRANSTU", line_num)
        if not existing:
            # Try case-insensitive number match
            for (l_op, l_num), line in index.line_by_key.items():
                if l_op == "TRANSTU" and l_num.lower() == line_num.lower():
                    existing = line
                    break

        if existing:
            sched = existing.get("schedule", {})
            changed = False
            if tb["first_to_station"] and not sched.get("first_departure"):
                sched["first_departure"] = tb["first_to_station"]
                changed = True
            if tb["last_to_station"] and not sched.get("last_departure"):
                sched["last_departure"] = tb["last_to_station"]
                changed = True
            if tb["first_to_neighborhood"] and not sched.get("first_departure_neighborhood"):
                sched["first_departure_neighborhood"] = tb["first_to_neighborhood"]
                changed = True
            if tb["last_to_neighborhood"] and not sched.get("last_departure_neighborhood"):
                sched["last_departure_neighborhood"] = tb["last_to_neighborhood"]
                changed = True
            if changed:
                existing["schedule"] = sched
                tebourba_updated += 1
                updated_lines += 1

    # ── 5. Update station lines_served ──────────────────────────────────────
    # Build line_id → station_ids map from new lines
    for nl in new_lines:
        for sid in nl.get("stations", []):
            station = index.station_by_id.get(sid)
            if not station:
                # Check new stations
                for ns in new_stations:
                    if ns["id"] == sid:
                        station = ns
                        break
            if station:
                ls = station.setdefault("lines_served", [])
                entry = {
                    "route_short_name": nl.get("number"),
                    "route_color": nl.get("color"),
                }
                if entry not in ls:
                    ls.append(entry)
                    updated_stations += 1

    # Also update existing lines that got new station data
    for line in seed["lines"]:
        if line.get("stations"):
            for sid in line["stations"]:
                station = index.station_by_id.get(sid)
                if station:
                    ls = station.setdefault("lines_served", [])
                    entry = {
                        "route_short_name": line.get("number"),
                        "route_color": line.get("color"),
                    }
                    if entry not in ls:
                        ls.append(entry)
                        updated_stations += 1

    # ── 6. Report ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  GTFS lines:     {len(gtfs_lines)} parsed, {gtfs_added} new, {gtfs_updated} updated")
    print(f"  BLEDI lines:    {len(bledi_lines)} parsed, {bledi_added} new, {bledi_updated} updated")
    print(f"  Tebourba lines: {len(tebourba_lines)} parsed, {tebourba_updated} updated")
    print(f"  New stations:   {len(new_stations)}")
    print(f"  Lines updated:  {updated_lines}")
    print(f"  Station links:  {updated_stations}")

    if args.dry_run:
        print(f"\n--dry-run: seed NOT modified.")
        if new_lines:
            print(f"\n  First 10 new lines:")
            for nl in new_lines[:10]:
                print(f"    + {nl['id']}: {nl['name'][:50]} ({len(nl.get('stations', []))} stations)")
        if new_stations:
            print(f"\n  First 10 new stations:")
            for ns in new_stations[:10]:
                print(f"    + {ns['id']}: {ns['name'][:40]} ({ns['lat']:.5f}, {ns['lon']:.5f})")
        return 0

    # ── 7. Write seed ────────────────────────────────────────────────────────
    if not new_lines and not new_stations and updated_lines == 0:
        print("\nNothing to add or update.")
        return 0

    # Add new stations
    if new_stations:
        seed["stations"].extend(new_stations)

    # Add new lines
    if new_lines:
        seed["lines"].extend(new_lines)

    # Update metadata
    md = seed.setdefault("metadata", {})
    md["total_stations"] = len(seed["stations"])
    md["total_lines"] = len(seed["lines"])
    md["routes_schedules_import"] = {
        "source_dir": str(DUMP),
        "gtfs_lines_parsed": len(gtfs_lines),
        "gtfs_lines_added": gtfs_added,
        "gtfs_lines_updated": gtfs_updated,
        "bledi_lines_parsed": len(bledi_lines),
        "bledi_lines_added": bledi_added,
        "bledi_lines_updated": bledi_updated,
        "tebourba_lines_updated": tebourba_updated,
        "new_stations": len(new_stations),
        "lines_updated": updated_lines,
        "station_links_updated": updated_stations,
        "tolerance_m": TOLERANCE_M,
    }

    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nWrote {SEED}")
    print(f"  {len(seed['stations'])} stations, {len(seed['lines'])} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())