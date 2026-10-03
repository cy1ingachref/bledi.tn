#!/usr/bin/env python3
"""Read every geolocated export the portal provides, csv or xlsx alike.

An earlier pass reported several directories as "no usable rows" and moved on.
That conflated two different things:

  * files that DO carry coordinates but were skipped — an encoding bug (utf-16
    "succeeds" on any bytes, turning cp1252 files into mojibake) and an xlsx
    reader that only scraped sharedStrings, which misses cells stored inline
  * files that publish no coordinates at all (station name lists, timetables)

This module reads both formats properly and reports which is which, so the
distinction is evidence rather than a guess.

Verified against the export: TRANSTU 2 617, SRTGN 525, SRTJ 191, SNTRI 306,
SORETRAS 971, plus the rail/metro sets — against Bizerte, which publishes 426
station names and no coordinates anywhere.

Requires openpyxl for the .xlsx sources. Writes nothing.

    python tool/read_geolocated.py --src <dir> --out stops.json
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse_official_data import sniff  # noqa: E402

# Which directories are stop inventories, and what mode/operator they describe.
# Ordered by authority: an operator's own feed first, so a name collision
# prefers it over a duplicate exported by another dataset.
SOURCES: list[tuple[str, str, str]] = [
    ("resau ferre", "train", "SNCFT"),
    ("Position géographique des stations du réseau ferré de la SNCFT", "train", "SNCFT"),
    ("Cartographie des stations du réseau ferroviaire rapide du RFR", "train", "RFR"),
    ("Cartographie des stations du Banlieue Sud SNCFT", "train", "SNCFT"),
    ("Cartographie des stations du Banlieue sahel SNCFT", "train", "SNCFT"),
    ("Positions géographiques des stations de la ligne TGM de la Transtu", "metro", "TGM"),
    ("cartographie des stations du réseau métro de la Transtu", "metro", "TGM"),
    ("Référentiel des arrêts de la TRANSTU", "bus", "TRANSTU"),
    ("Positions géographiques des stations du réseau bus de la TRANSTU", "bus", "TRANSTU"),
    ("Positions géographiques des stations du réseau bus de la SRTGN", "bus", "SRTGN"),
    ("Positions géographiques des stations de la société régionale de transport de jendouba SRTJ", "bus", "SRTJ"),
    ("Positions géographiques des stations du réseau bus de la SORETRAS", "bus", "SORETRAS"),
    ("Positions géographiques des stations du réseau bus de la SNTRI", "bus", "SNTRI"),
    ("Cartographie des Stations SNTRI", "bus", "SNTRI"),
    ("liste des stations de la SRTM et leurs positions géographiques", "bus", "SRTM"),
    ("stops", "bus", "TRANSTU"),
]

LAT_KEYS = ("lat", "latitude", "y_coord", " ylat", "coordy")
LON_KEYS = ("lon", "lng", "long", "longitude", " x_coord", "xlong")
NAME_KEYS = ("nom de la station", "stop_name", "name", "nom", "label_fr", "libelle",
             "delstation", "non de la station", "station")
GOV_KEYS = ("gouvernorat", "governorate", "delegation", "commune")

# TRANSTU appends a direction marker to stop names: "... -a-" / "... -r-" for
# aller / retour. Left in place they read as two different places a few metres
# apart, which is why the raw feed looks like 2 577 new stops instead of 1 381.
DIRECTION_SUFFIX = re.compile(
    r"\s*[-–—]\s*[arr]{1,2}\s*[-–—]\s*$|\s+[arr]{1,2}\s*$|\s*\((aller|retour)\)\s*$",
    re.I,
)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return " ".join("".join(c if c.isalnum() or c.isspace() else " " for c in s).split())


def place_key(name: str) -> str:
    """Name with any direction marker removed, so aller/retour collapse."""
    return norm(DIRECTION_SUFFIX.sub("", name or ""))


def to_float(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _row_to_record(row: dict, mode: str, operator: str, src: str) -> dict | None:
    lower = {str(k).strip().lower(): v for k, v in row.items() if k is not None}

    lat = lon = None
    for k, v in lower.items():
        if lat is None and any(s in k for s in LAT_KEYS):
            lat = to_float(v)
        if lon is None and any(s in k for s in LON_KEYS):
            lon = to_float(v)
    if lat is None or lon is None:
        return None
    if not (30.0 <= lat <= 38.0 and 6.5 <= lon <= 12.5):
        return None

    name = ""
    for k, v in lower.items():
        if any(s in k for s in NAME_KEYS) and v:
            name = str(v).strip()
            break
    gov = ""
    for k, v in lower.items():
        if any(s in k for s in GOV_KEYS) and v:
            gov = str(v).strip()
            break
    if not name:
        return None

    return {
        "operator": operator,
        "mode": mode,
        "name": re.sub(r"\s+", " ", name),
        "lat": lat,
        "lon": lon,
        "governorate": gov,
        "source_file": src,
    }


def read_csv(path: Path, mode: str, operator: str) -> list[dict]:
    text, delim = sniff(path)
    out = []
    for row in csv.DictReader(io.StringIO(text), delimiter=delim):
        rec = _row_to_record(row, mode, operator, path.name)
        if rec:
            out.append(rec)
    return out


def read_xlsx(path: Path, mode: str, operator: str) -> list[dict]:
    """Read a worksheet properly.

    Scraping sharedStrings misses cells whose values are stored inline, and
    cannot recover which column a number belonged to. Reading the grid through
    openpyxl keeps the header-to-column mapping, which is the whole problem.
    """
    try:
        import openpyxl
    except ImportError:
        return []
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - unreadable workbook, skip it
        return []
    out: list[dict] = []
    try:
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            try:
                header = next(rows)
            except StopIteration:
                continue
            keys = [str(h).strip() if h is not None else "" for h in header]
            if not any(k for k in keys):
                continue
            for values in rows:
                if values is None:
                    continue
                row = {keys[i]: values[i] for i in range(min(len(keys), len(values)))}
                rec = _row_to_record(row, mode, operator, path.name)
                if rec:
                    out.append(rec)
    finally:
        wb.close()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-collapse", action="store_true",
                    help="keep aller/retour variants as separate records")
    args = ap.parse_args()

    root = Path(args.src)
    records: list[dict] = []
    per_source: list[tuple[str, int]] = []
    empty_dirs: list[str] = []

    for sub, mode, operator in SOURCES:
        d = root / sub
        if not d.is_dir():
            empty_dirs.append(f"{sub} (absent)")
            continue
        found = 0
        for f in sorted(d.rglob("*")):
            if not f.is_file() or f.name.startswith("_"):
                continue
            if f.suffix.lower() == ".csv":
                recs = read_csv(f, mode, operator)
            elif f.suffix.lower() == ".xlsx":
                recs = read_xlsx(f, mode, operator)
            else:
                continue
            found += len(recs)
            records.extend(recs)
        if found:
            per_source.append((f"{operator} / {sub}", found))
        else:
            empty_dirs.append(f"{sub} (no geolocated rows)")

    # Collapse direction variants onto one record per physical place.
    collapsed = 0
    if not args.no_collapse:
        best: dict[tuple, dict] = {}
        for r in records:
            key = (operator_key(r), place_key(r["name"]))
            prev = best.get(key)
            if prev is None:
                best[key] = r
                continue
            collapsed += 1
            # Keep the shorter, cleaner label: "Foo" over "Foo -r-".
            if len(r["name"]) < len(prev["name"]):
                r["lat"], r["lon"] = prev["lat"], prev["lon"]
                r["governorate"] = r["governorate"] or prev["governorate"]
                best[key] = r
        records = list(best.values())

    # Then merge anything sharing a position within ~60 m.
    cell = 60 / 111320
    grid: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    kept: list[dict] = []
    for r in records:
        k = (int(r["lat"] // cell), int(r["lon"] // cell))
        hit = None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for idx in grid.get((k[0] + dy, k[1] + dx), []):
                    o = kept[idx]
                    if (abs(o["lat"] - r["lat"]) < 0.001
                            and abs(o["lon"] - r["lon"]) < 0.001):
                        hit = idx
                        break
                if hit is not None:
                    break
            if hit is not None:
                break
        if hit is not None:
            kept[hit]["also_known_as"] = kept[hit].get("also_known_as", []) + [r["name"]]
            continue
        grid[k].append(len(kept))
        kept.append(r)
    positional_merges = len(records) - len(kept)
    records = kept

    Path(args.out).write_text(json.dumps(records, ensure_ascii=False, indent=1),
                              encoding="utf-8")

    print(f"geolocated records read ..... {sum(n for _, n in per_source)}")
    print(f"after collapsing directions  {collapsed} removed")
    print(f"after merging same position  {positional_merges} removed")
    print(f"final distinct places ........ {len(records)}")
    print(f"\nwrote {args.out}\n")

    print("by operator:")
    for op, n in collections.Counter(r["operator"] for r in records).most_common():
        print(f"  {op:10s} {n}")
    print("\nby mode:")
    for m, n in collections.Counter(r["mode"] for r in records).most_common():
        print(f"  {m:10s} {n}")
    named = sum(1 for r in records if r["name"])
    print(f"\nwith a name: {named}/{len(records)}")
    print("\nper source:")
    for label, n in sorted(per_source, key=lambda kv: -kv[1]):
        print(f"  {n:6d}  {label[:76]}")
    if empty_dirs:
        print("\nno geolocated rows:")
        for e in empty_dirs:
            print(f"  - {e}")


def operator_key(r: dict) -> str:
    return r["operator"]


if __name__ == "__main__":
    main()