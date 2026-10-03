#!/usr/bin/env python3
"""Parse the official Tunisian transport open-data exports into one JSON file.

Source: C:\\Users\\cy1in\\Downloads\\transport — a portal export of per-operator
datasets (Transtu, SNCFT, RFR, SNTRI, SORETRAS, SRTGN, SRTM, SRTJ, SRTB,
SORETRAK). These are operator-published positions and stop lists, so they are a
better authority than OpenStreetMap for "is this stop a rail halt or a bus
stop" and "what are its real coordinates".

The files are heterogeneous: some are GTFS (`stop_id,stop_name,stop_lat,...`),
some tab-separated with a header row, some UTF-16, some with no header at all.
This sniffs each file rather than assuming one schema, and records which
operator and mode it came from so downstream comparison can weight them.

Output: one JSON array of {operator, mode, name, lat, lon, source_file}.

Read-only. Writes only the --out file.

    python tool/parse_official_data.py --src <dir> --out official_stops.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

# Which export directories to read, and what mode they describe. Ordered by
# authority: operator feeds first, so a name/coordinate collision prefers them.
#
#   TRANSTU/SNTRI  bus networks in and around Tunis
#   RFR            Réseau Ferroviaire Rapide (Sousse–Monastir–Mahdia commuter)
#   SNCFT          national rail
#   TGM/métro      light rail
SOURCES: list[tuple[str, str, str]] = [
    ("resau ferre", "train", "SNCFT"),
    ("Position géographique des stations du réseau ferré de la SNCFT", "train", "SNCFT"),
    ("Cartographie des stations du réseau ferroviaire rapide du RFR", "train", "RFR"),
    ("Cartographie des stations du Banlieue Sud SNCFT", "train", "SNCFT"),
    ("Cartographie des stations du Banlieue sahel SNCFT", "train", "SNCFT"),
    ("Positions géographiques des stations du réseau bus de la TRANSTU", "bus", "TRANSTU"),
    ("Positions géographiques des stations du réseau bus de la SORETRAS", "bus", "SORETRAS"),
    ("Positions géographiques des stations du réseau bus de la SRTGN", "bus", "SRTGN"),
    ("Positions géographiques des stations de la société régionale de transport de jendouba SRTJ", "bus", "SRTJ"),
    ("Positions géographiques des stations de la ligne TGM de la Transtu", "metro", "TGM"),
    ("cartographie des stations du réseau métro de la Transtu", "metro", "TGM"),
    ("Positions géographiques des stations du réseau bus de la SNTRI", "bus", "SNTRI"),
    ("Cartographie des Stations SNTRI", "bus", "SNTRI"),
    ("liste des stations de la SRTM et leurs positions géographiques", "bus", "SRTM"),
    ("Liste des stations régionales de SORETRAS", "bus", "SORETRAS"),
]

NUM = r"[-+]?\d{1,3}(?:\.\d+)?"
COORD_RE = re.compile(rf"({NUM})\s*[,;]\s*({NUM})")


def sniff(path: Path) -> tuple[str, str]:
    """Return (decoded text, delimiter).

    Encoding order matters and was the source of a real bug: `utf-16` decodes
    almost any byte sequence without raising, so trying it early turned a
    cp1252 file into mojibake (`瑳瑡椻...`) that then parsed as one junk row,
    silently dropping every station in it. UTF-16 is now only tried when a BOM
    actually says so, and single-byte decoders are preferred otherwise.
    """
    raw = path.read_bytes()

    # Trust an explicit BOM first.
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), _delim_of(raw.decode("utf-16"))
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig"), _delim_of(raw.decode("utf-8-sig"))

    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        # Reject a decode that produced private-use characters, the signature
        # of a wide encoding being misread as narrow.
        if any(0xE000 <= ord(c) <= 0xF8FF or 0x50000 <= ord(c) <= 0x10FFFD
               for c in text[:400]):
            continue
        return text, _delim_of(text)

    return raw.decode("latin-1", errors="replace"), _delim_of(
        raw.decode("latin-1", errors="replace")
    )


def _delim_of(text: str) -> str:
    """Most common column separator on the first line; tab if none present."""
    head = text.splitlines()[0] if text.splitlines() else ""
    counts = {d: head.count(d) for d in (",", "\t", ";", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] else "\t"


def looks_like_header(cells: list[str]) -> bool:
    """A header row names fields; a data row does not."""
    joined = " ".join(cells).lower()
    return any(
        k in joined
        for k in ("stop_name", "nom", "name", "lat", "lon", "géograph", "latitude",
                  "station", "arrêt", "x", "y", "code")
    )


def pick(columns: dict[str, str], lat_keys, lon_keys) -> tuple[str, str] | None:
    """Find a lat/lon column pair, matching by header keyword."""
    lower = {k.strip().lower(): v for k, v in columns.items()}
    lat = lon = None
    for k, v in lower.items():
        if lat is None and any(s in k for s in lat_keys):
            lat = v
        if lon is None and any(s in k for s in lon_keys):
            lon = v
    if lat and lon:
        return lat.strip(), lon.strip()
    return None


LAT_KEYS = ("stop_lat", "latitude", "lat", " y", "ylat", "coordy", "_y")
LON_KEYS = ("stop_lon", "longitude", "lon", "lng", "long", " x", "xlong", "_x")


def parse_file(path: Path, mode: str, operator: str) -> list[dict]:
    text, delim = sniff(path)
    rows = list(csv.DictReader(text.splitlines(), delimiter=delim))
    if not rows:
        return []

    columns = {k: v for k, v in rows[0].items() if k is not None}
    header = looks_like_header(list(columns))

    out: list[dict] = []
    for row in rows:
        if not header:
            # No usable header: take the first coordinate pair we can find.
            vals = list(row.values())
            for i in range(len(vals)):
                m = COORD_RE.search(vals[i])
                if m:
                    lat, lon = m.group(1), m.group(2)
                    name = next(
                        (v.strip() for v in vals[:i]
                         if v and not COORD_RE.fullmatch(v.strip()) and v.strip()),
                        "",
                    )
                    out.append(_rec(name, lat, lon, mode, operator, path))
                    break
            continue

        pair = pick(row, LAT_KEYS, LON_KEYS)
        if not pair:
            # Some feeds put both coordinates in one cell, "lat;lon" or "lat,lon".
            for v in row.values():
                if v and COORD_RE.fullmatch(v.strip()):
                    m = COORD_RE.fullmatch(v.strip())
                    lower = {k.strip().lower(): row.get(k) for k in row}
                    name = next(
                        (str(lower[k]).strip() for k in lower
                         if k and ("nom" in k or "name" in k or "arrêt" in k)
                         and lower[k]),
                        "",
                    )
                    out.append(_rec(name, m.group(1), m.group(2), mode, operator, path))
                    break
            continue

        lat, lon = pair
        name = ""
        for k, v in row.items():
            if not v:
                continue
            kl = (k or "").strip().lower()
            # `Label_fr` is the French label column in the portal's own exports;
            # without it the busiest datasets parse with no names at all.
            if any(s in kl for s in ("stop_name", "nom", "name", "label", "libelle",
                                     "arrêt", "station")):
                name = v.strip()
                break
        out.append(_rec(name, lat, lon, mode, operator, path))
    return [r for r in out if r]


def _to_float(raw: str) -> float | None:
    """Parse a coordinate cell.

    Tunisian exports mix decimal separators: some write `36.8097`, others
    `36,8097` — and in a comma-delimited file the latter arrives quoted. A bare
    float() call raises on the comma form and silently drops the whole dataset,
    which is how the 1 691-row TRANSTU file went unread.
    """
    if raw is None:
        return None
    s = str(raw).strip().strip('"').strip("'")
    if not s:
        return None
    # A comma can only be a decimal separator here: these are single values,
    # never "lat,lon" pairs, because the caller already split the columns.
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _rec(name: str, lat: str, lon: str, mode: str, operator: str, path: Path) -> dict | None:
    la, lo = _to_float(lat), _to_float(lon)
    if la is None or lo is None:
        return None
    # Tunisia's bounds; anything else is a parsing artefact, not a real position.
    if not (30.0 <= la <= 38.0 and 6.5 <= lo <= 12.5):
        return None
    return {
        "operator": operator,
        "mode": mode,
        "name": re.sub(r"\s+", " ", name).strip(),
        "lat": la,
        "lon": lo,
        "source_file": str(path),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True, help="root of the transport export")
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", type=int, default=8)
    args = ap.parse_args()

    root = Path(args.src)
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")

    all_recs: list[dict] = []
    used: list[str] = []
    missing: list[str] = []
    for sub, mode, operator in SOURCES:
        d = root / sub
        if not d.is_dir():
            missing.append(sub)
            continue
        found = 0
        for f in sorted(d.rglob("*.csv")):
            recs = parse_file(f, mode, operator)
            if recs:
                found += len(recs)
                used.append(f"{sub}/{f.name} ({len(recs)})")
            all_recs.extend(recs)
        if not found:
            missing.append(f"{sub} (no usable rows)")

    # De-duplicate on operator+mode+coordinates: the same stop is often exported
    # by more than one dataset.
    seen: set[tuple] = set()
    unique: list[dict] = []
    for r in all_recs:
        key = (r["operator"], r["mode"], round(r["lat"], 5), round(r["lon"], 5))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    Path(args.out).write_text(json.dumps(unique, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    import collections

    print(f"source dir ........... {root}")
    print(f"files parsed ......... {len(used)}")
    print(f"rows read ............ {len(all_recs)}")
    print(f"after de-duplication . {len(unique)}")
    if missing:
        print(f"\nnot found / no usable rows ({len(missing)}):")
        for m in missing[: args.report]:
            print(f"  - {m}")

    print("\nby operator:")
    for op, n in collections.Counter(r["operator"] for r in unique).most_common():
        print(f"  {op:10s} {n}")
    print("\nby mode:")
    for m, n in collections.Counter(r["mode"] for r in unique).most_common():
        print(f"  {m:10s} {n}")

    named = sum(1 for r in unique if r["name"])
    print(f"\nrecords with a name .. {named}/{len(unique)}")

    print(f"\nwrote {args.out}")
    print("\nfiles used:")
    for u in used[: args.report]:
        print(f"  {u}")
    if len(used) > args.report:
        print(f"  ... and {len(used) - args.report} more")


if __name__ == "__main__":
    main()