#!/usr/bin/env python3
"""Import every genuine station/stop source from the Downloads transport dump.

The dump (C:\\Users\\cy1in\\Downloads\\transport) holds the official operator
exports collected for this project. This importer reads the files that
actually describe STOPS, and deliberately skips the ones that do not.

INCLUDED (stop registries with coordinates)
  TNRP national bus-stop registry (8 148 rows, official, per-governorate)
  TRANSTU  stops referentiel / positions / line-stop itineraries
  SORETRAS, SRTGN, SRTM, SRT Bizerte, SRTJ, SNTRI station lists
  TGM tramway station positions
  BLEDI_transport.xlsx "Louage-Taxi" sheet (curated louage stands)
  All operator GTFS feeds (stops.txt inside each .zip)

EXCLUDED, with reason
  resau ferre/**/SNCFT-PN-*   -> "passages a niveau" = level crossings, not stops
  rural .../lycee, .../ecoles primaires -> schools (rural demand points)
  rural .../pistes agricoles -> farm tracks, not stops
  rural .../liste des lignes de taxi collectif|transport rural -> line names only
  ATTT / parc / tarif / ateliers / aeroport files -> not stop data

Usage:
    python scripts/import_downloads_transport.py --dry-run
    python scripts/import_downloads_transport.py --write
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import sys
import warnings
import zipfile
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"
# Consolidated 2026-10-11: the operator exports moved from
# ~/Downloads/transport to the organised resource folder.
DUMP = Path(os.environ.get(
    "BLEDI_OPERATOR_EXPORTS",
    Path.home() / "Downloads" / "tunisia-transport-data" / "01-bus-network" / "operator-exports",
))
TOLERANCE_M = 150.0
CELL = 0.002  # ~220 m grid cell


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
    """Parse a coordinate from a cell, rejecting NaN/blank/out-of-Tunisia."""
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
    # Tunisia bounding box, generous
    return la is not None and lo is not None and 30.0 < la < 38.0 and 7.0 < lo < 12.0


# ── source allowlist: (filename prefix, label, kind) ────────────────────────
# kind = "xlsx" | "csv" | "zip"
SOURCES: list[tuple[str, str, str]] = [
    ("a6787314", "TNRP national bus-stop registry", "xlsx"),
    ("aa88bb16", "TRANSTU stops referentiel", "xlsx"),
    ("3adfe935", "TRANSTU stop positions", "xlsx"),
    ("d503239c", "TRANSTU line-stop itineraries", "xlsx"),
    ("5de6b51e", "SRTM stations (Medenine)", "xlsx"),
    ("d7948165", "SORETRAS stops", "xlsx"),
    ("ede7395f", "SRTGN stations", "xlsx"),
    ("3debcd31", "TGM tramway positions", "xlsx"),
    ("6b25abd2", "SNTRI stops", "xlsx"),
    ("BLEDI_transport.xlsx", "BLEDI curated workbook", "xlsx"),
    # Rail / metro station cartography (GTFS-format or Label/Lat/Lon)
    ("90805137", "SNCFT Banlieue Sud stations", "csv"),
    ("4c7c7cef", "SNCFT Banlieue Sahel stations", "csv"),
    ("245e848e", "RFR rapid-rail stations", "csv"),
    ("bac19c8e", "SNCFT national rail stations", "csv"),
    ("56db3909", "Transtu metro stations", "xlsx"),
    ("e739131c", "Transtu metro line-stops", "xlsx"),
    ("4b860131", "TGM tramway itinerary", "xlsx"),
    ("57f3d316", "TGM tramway timetable", "xlsx"),
    ("df46ae89", "SRTJ station positions", "csv"),
    ("cf2741e2", "GTFS stops (SNTRI feed)", "csv"),
]

# explicit exclusions, checked against the full relative path
EXCLUDE_PAT = re.compile(
    r"SNCFT-PN|passages . niveau|lycee|ecoles primaires|pistes agricoles|"
    r"taxi collectif|transport rural concernant|ATTT|parc des|tarif|"
    r"ateliers|a[ée]roport|visite technique|SONOTRAK",
    re.I,
)

LAT_KEYS = ("stop_lat", "lat", "latitude", "y", "latitude (y)", "label_lat")
LON_KEYS = ("stop_lon", "lon", "longitude", "x", "longitude (x)", "label_lon")
NAME_KEYS = (
    "stop_name", "nom de la station", "nom de station", "name", "nom",
    "nom français", "label_fr", "etablissement", "delstation",
    # RFR cartography puts the station name in "Trajet"; "Itinéraire" holds the
    # line label on the header row only, so it is tried last.
    "trajet", "itineraire",
)
MODE_HINTS = (
    ("metro", "metro"), ("tram", "tram"), ("tgm", "tram"),
    ("train", "train"), ("rfr", "rfr"), ("sncft", "train"),
    ("louage", "louage"), ("taxi", "taxi"),
)


def guess_mode(label: str, name: str = "") -> str:
    blob = f"{label} {name}".lower()
    for needle, mode in MODE_HINTS:
        if needle in blob:
            return mode
    return "bus"


def pick_nonempty(d: dict, keys: tuple[str, ...]):
    """First candidate column that holds a non-blank value.

    Column-shifted exports (the RFR cartography) have every candidate column
    present but empty on data rows, so a plain key lookup returns "" and
    shadows the column that actually holds the name.
    """
    low = {str(k).strip().lower(): k for k in d}
    for want in keys:
        for lk, orig in low.items():
            if lk == want or want in lk:
                v = d[orig]
                if v is not None and str(v).strip():
                    return v
    return None


def pick(d: dict, keys: tuple[str, ...]):
    """Column lookup, case/space-insensitive, exact key match on the tuple."""
    low = {str(k).strip().lower(): k for k in d}
    for want in keys:
        if want in low:
            return d[low[want]]
    # fuzzy fallback
    for want in keys:
        for lk, orig in low.items():
            if want in lk:
                return d[orig]
    return None


def iter_xlsx_rows(path: Path):
    import pandas as pd

    try:
        sheets = pd.read_excel(path, sheet_name=None)
    except Exception as e:  # noqa: BLE001
        print(f"    ! unreadable: {type(e).__name__}")
        return
    for sheet, df in sheets.items():
        if df is None or df.empty:
            continue
        for rec in df.to_dict("records"):
            yield sheet, rec


def iter_csv_rows(path: Path):
    """Read a CSV, tolerating UTF-16 (with BOM) and ';' delimiters.

    Several operator exports are UTF-16LE tab/semicolon files; a plain
    utf-8 read raises and the whole file used to be skipped silently.
    """
    raw = path.read_bytes()
    for enc in ("utf-16", "utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
        # strip a stray BOM that survived
        text = text.lstrip("\ufeff")
        first = text.split("\n", 1)[0]
        delim = ";" if first.count(";") > first.count(",") else ","
        try:
            rdr = csv.DictReader(io.StringIO(text), delimiter=delim)
            rows = list(rdr)
        except csv.Error:
            continue
        if rows:
            yield from rows
            return


def iter_gtfs_rows(path: Path):
    try:
        zf = zipfile.ZipFile(path)
    except Exception:  # noqa: BLE001
        return
    with zf:
        nm = next((n for n in zf.namelist() if n.lower().endswith("stops.txt")), None)
        if not nm:
            return
        raw = zf.read(nm)
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                yield from csv.DictReader(io.StringIO(raw.decode(enc)))
                return
            except (UnicodeDecodeError, csv.Error):
                continue


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.write):
        ap.error("pass --dry-run or --write")

    if not DUMP.exists():
        print(f"ERROR: dump not found: {DUMP}", file=sys.stderr)
        return 2

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    stations = seed["stations"]
    print(f"seed: {len(stations)} stations")

    # proximity index of everything already in the seed
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for s in stations:
        la, lo = num(s.get("lat")), num(s.get("lon"))
        if valid(la, lo):
            grid.setdefault((round(la / CELL), round(lo / CELL)), []).append((la, lo))

    def known(la: float, lo: float) -> bool:
        ci, cj = round(la / CELL), round(lo / CELL)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for sla, slo in grid.get((ci + di, cj + dj), ()):
                    if hav(la, lo, sla, slo) <= TOLERANCE_M:
                        return True
        return False

    # collect every candidate file
    files: list[Path] = []
    for root, _dirs, fnames in os.walk(DUMP):
        for fn in fnames:
            p = Path(root) / fn
            rel = os.path.relpath(p, DUMP)
            if EXCLUDE_PAT.search(rel):
                continue
            files.append(p)

    existing_ids = {s["id"] for s in stations}
    added: list[dict] = []
    per_source: dict[str, tuple[int, int]] = {}  # label -> (rows, new)
    seen_names: dict[str, int] = {}

    for prefix, label, kind in SOURCES:
        hits = [
            p for p in files
            if os.path.basename(p).startswith(prefix)
            and p.suffix.lower() in (".xlsx", ".xls", ".csv")
        ]
        if not hits:
            print(f"  {label:44s} (no file)")
            continue
        rows = 0
        new = 0
        for p in hits:
            # only the stop-ish sheets of the BLEDI workbook
            if prefix.startswith("BLEDI_transport"):
                for sheet, rec in iter_xlsx_rows(p):
                    if "stop" not in sheet.lower() and "louage" not in sheet.lower():
                        continue
                    rows += 1
                    new += _consider(
                        rec, label, guess_mode(f"{label} {sheet}"),
                        grid, known, added, existing_ids, seen_names,
                    )
                continue

            it = iter_xlsx_rows(p) if p.suffix.lower() in (".xlsx", ".xls") else iter_csv_rows(p)
            for rec in it:
                if isinstance(rec, tuple):
                    rec = rec[1]
                rows += 1
                la = num(pick(rec, LAT_KEYS))
                lo = num(pick(rec, LON_KEYS))
                nm = str(pick(rec, NAME_KEYS) or "").strip()
                new += _consider(
                    rec, label, guess_mode(label, nm),
                    grid, known, added, existing_ids, seen_names,
                )
        per_source[label] = (rows, new)
        print(f"  {label:44s} rows={rows:6d} new={new:5d}")

    # GTFS feeds
    print("  --- GTFS feeds ---")
    for root, _dirs, fnames in os.walk(DUMP):
        for fn in fnames:
            p = Path(root) / fn
            if p.suffix.lower() != ".zip":
                continue
            rel = os.path.relpath(p, DUMP)
            if EXCLUDE_PAT.search(rel):
                continue
            label = f"GTFS {os.path.basename(os.path.dirname(p))[:34]}"
            rows = new = 0
            for rec in iter_gtfs_rows(p):
                rows += 1
                nm = str(rec.get("stop_name") or "").strip()
                new += _consider(
                    rec, label, guess_mode(label, nm),
                    grid, known, added, existing_ids, seen_names,
                )
            if rows:
                per_source[label] = (rows, new)
                print(f"  {label:44s} rows={rows:6d} new={new:5d}")

    by_mode: dict[str, int] = {}
    for a in added:
        by_mode[a["mode"]] = by_mode.get(a["mode"], 0) + 1

    print(f"\nTOTAL new stations: {len(added)}")
    for m, n in sorted(by_mode.items(), key=lambda x: -x[1]):
        print(f"    {m:8s} {n}")

    if not added:
        print("\nNothing to add.")
        return 0

    if args.dry_run:
        print("\n--dry-run: seed NOT modified. First 25:")
        for a in added[:25]:
            print(f"  + {a['mode']:7s} {a['name'][:44]:46s} {a['lat']:.5f},{a['lon']:.5f}")
        return 0

    seed["stations"] = stations + added
    md = seed.setdefault("metadata", {})
    md["total_stations"] = len(seed["stations"])
    md["downloads_transport_import"] = {
        "source_dir": str(DUMP),
        "added": len(added),
        "by_mode": by_mode,
        "tolerance_m": TOLERANCE_M,
        "per_source": {k: {"rows": v[0], "new": v[1]} for k, v in per_source.items()},
        "excluded": "SNCFT level crossings, schools, farm tracks, line-name-only lists",
    }
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nWrote {SEED} ({len(seed['stations'])} stations).")
    return 0


def _consider(rec, label, mode, grid, known, added, existing_ids, seen_names) -> int:
    """Add one candidate stop if it is real, new, and not a duplicate."""
    la = num(pick(rec, LAT_KEYS))
    lo = num(pick(rec, LON_KEYS))
    if not valid(la, lo):
        return 0
    if known(la, lo):
        return 0
    nm = str(pick_nonempty(rec, NAME_KEYS) or "").strip()
    # Drop repeated line-label rows (the RFR file repeats "Ligne F"), numeric
    # leftovers from misaligned columns, and anything unnamed -- an unnamed
    # marker is worse than no marker.
    if not nm or re.match(r"^(ligne|line)\b", nm, re.I):
        return 0
    if re.match(r"^[\d.,\s]+(km|m)?$", nm, re.I):
        return 0
    sid = f"dl_{slug(label)}_{slug(nm)}"
    n = seen_names.get(sid, 0)
    seen_names[sid] = n + 1
    if n:
        sid = f"{sid}_{n}"
    if sid in existing_ids:
        return 0
    op = str(pick(rec, ("Societe", "operator", "agence")) or "").strip()
    added.append({
        "id": sid,
        "name": nm,
        "name_en": nm,
        "lat": la,
        "lon": lo,
        "mode": mode,
        "operator": op.upper() or label.upper()[:24],
        "lines_served": [],
        "route_type": 3 if mode == "bus" else 2,
        "source": f"downloads:{label}",
        "license_status": "official-open-data",
    })
    existing_ids.add(sid)
    grid.setdefault((round(la / CELL), round(lo / CELL)), []).append((la, lo))
    return 1


if __name__ == "__main__":
    sys.exit(main())
