#!/usr/bin/env python3
"""Survey every export directory: does it hold coordinates, and how many?

The audit so far has ignored whole directories because the parser reported "no
usable rows" for them. That turned out to be two different situations conflated:

  * files that DO carry coordinates but were skipped because of an encoding or
    delimiter bug — these are recoverable and worth importing
  * files that genuinely publish no coordinates (station name lists) — nothing
    to import, and pretending otherwise would put invented points on the map

This distinguishes them, so the next step is evidence-based rather than another
guess.

    python tool/survey_exports.py --src <dir>
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse_official_data import _delim_of, sniff  # noqa: E402

COORD = re.compile(r"\d{1,3}[.,]\d{4,}")

SKIP_DIRS = {
    "Le transport en milieu rural",  # names only, surveyed separately
    "Tarif du transport de gaz à travers la SONOTRAK",
    "tarif transtu",
    "La disponibilité du parc des buses de la SORETRAK",
    "Le parc des véhicules de la SRTGN",
    "Les sites et les ateliers de la SRTGN",
    "position géographique des directions régionales de l'ATTT",
    "Les ressources disponibles à l'aéroport Tunis Carthage",
    "caractéristiques des centres de visite technique à l'ATTT",
    "Liste des lignes par agence de la SRTGN",
    "Liste des lignes régionales de SORETRAS",
    "Les lignes d'exploitation de la SRTB",
    "Passages à niveau SNCFT",
    "Temps réel - SORETRAK",
}


def classify(path: Path) -> tuple[str, int, str]:
    """Return (verdict, count, detail) for one file."""
    if path.suffix.lower() == ".xls":
        return "legacy-xls", 0, "old binary format, not parsed"
    if path.suffix.lower() == ".xlsx":
        try:
            zf = zipfile.ZipFile(path)
            shared = ""
            if "xl/sharedStrings.xml" in zf.namelist():
                shared = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
            vals = re.findall(r"<t[^>]*>([^<]*)</t>", shared)
            hits = sum(1 for v in vals if COORD.search(v))
            return ("xlsx-with-coords" if hits else "xlsx-names-only",
                    hits, f"{len(vals)} strings")
        except (KeyError, zipfile.BadZipFile):
            return "unreadable-xlsx", 0, ""
    if path.suffix.lower() == ".zip":
        try:
            zf = zipfile.ZipFile(path)
            names = zf.namelist()
            n = 0
            for nm in names:
                if nm.endswith(".txt"):
                    n += len(zf.read(nm).decode("utf-8-sig", errors="replace").splitlines())
            return "gtfs-zip", n, f"{len(names)} members, {n} rows"
        except zipfile.BadZipFile:
            return "unreadable-zip", 0, ""
    if path.suffix.lower() != ".csv":
        return "other", 0, path.suffix

    text, delim = sniff(path)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    body = [r for r in rows if any(c.strip() for c in r)]
    if not body:
        return "empty", 0, "no non-blank rows"
    # Count rows that contain at least one coordinate-looking value.
    hits = sum(1 for r in body if any(COORD.search(c) for c in r))
    if hits == 0:
        return "names-only", len(body) - 1, f"delim={delim!r}, no decimals found"
    return "csv-with-coords", hits, f"delim={delim!r}, {len(body) - 1} rows"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True)
    args = ap.parse_args()
    root = Path(args.src)

    buckets: dict[str, list[tuple[str, str, int, str]]] = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if d.name in SKIP_DIRS:
            continue
        for f in sorted(d.rglob("*")):
            if not f.is_file() or f.name.startswith("_"):
                continue
            verdict, count, detail = classify(f)
            buckets.setdefault(verdict, []).append(
                (d.name, f.name[:44], count, detail)
            )

    print(f"survey of {root}\n")
    for verdict in sorted(buckets, key=lambda v: -len(buckets[v])):
        rows = buckets[verdict]
        print(f"=== {verdict}  ({len(rows)} files)")
        # Summarise by directory, not by file, so the output stays readable.
        per_dir: dict[str, int] = {}
        for dirname, _, count, _ in rows:
            per_dir[dirname] = per_dir.get(dirname, 0) + count
        for dirname, total in sorted(per_dir.items(), key=lambda kv: -kv[1])[:14]:
            print(f"   {total:6d} rows  {dirname[:74]}")
        if len(per_dir) > 14:
            print(f"   ... and {len(per_dir) - 14} more directories")
        print()

    actionable = [
        (d, n, c, det)
        for v in ("csv-with-coords", "xlsx-with-coords", "gtfs-zip")
        for (d, n, c, det) in buckets.get(v, [])
    ]
    print(f"recoverable files: {len(actionable)}")
    for d, n, c, det in actionable[:30]:
        print(f"   {c:6d}  {d[:52]:52s} {n}")


if __name__ == "__main__":
    main()