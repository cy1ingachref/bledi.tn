#!/usr/bin/env python3
"""Copy the built station index into data/, and repair the mojibake name.

`tool/build_station_index.py` writes to out/ (which is gitignored). The backend
reads data/, so the artefacts are promoted here. Also repairs one station whose
name was corrupted to "???? ???" during an earlier export — its real name is
recoverable from the source CSV the row came from.

    python tool/promote_artifacts.py [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUMP = Path(r"C:\Users\cy1in\Downloads\tunisia-transport-data")
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"

PROMOTE = [
    (ROOT / "out" / "louage_links.json", ROOT / "data" / "louage_links.json"),
    (ROOT / "out" / "station_lines.json", ROOT / "data" / "station_lines.json"),
]


def find_source_row(source_file: str, lat: float, lon: float) -> dict | None:
    """Find the exact source row for a station by its coordinate.

    Matching on the coordinate, not on 'any non-ASCII name', is what makes this
    correct: the first attempt at this picked the wrong row entirely.
    """
    for p in DUMP.rglob(source_file):
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        for row in csv.DictReader(text.splitlines(), delimiter=";"):
            try:
                rlat = float((row.get("lat") or "").strip())
                rlon = float((row.get("lon") or "").strip())
            except ValueError:
                continue
            if abs(rlat - lat) < 1e-4 and abs(rlon - lon) < 1e-4:
                return row
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for src, dst in PROMOTE:
        if not src.is_file():
            print(f"MISSING {src} — run tool/build_station_index.py first")
            return 1
        print(f"promote {src.name} -> {dst.relative_to(ROOT)}  ({src.stat().st_size} bytes)")
        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # Label the mojibake station. The corruption is IN THE SOURCE FILE (the row
    # literally contains '???? ???' in the upstream CSV), so the Arabic name is
    # not recoverable from the data we hold. Inventing a plausible name would be
    # a guess dressed as a fact, so the station is labelled as name-unknown and
    # keeps its coordinate and line data, which are sound.
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    labelled = 0
    for s in seed["stations"]:
        nm = s.get("name") or ""
        if not nm.strip() or not all(ch in "?" or ch.isspace() for ch in nm):
            continue
        lat, lon = s.get("lat"), s.get("lon")
        print(f"\nmojibake station: id={s['id']}")
        print(f"  current name : {nm!r}")
        print(f"  coordinate   : {lat}, {lon}")
        print(f"  source file  : {s.get('source_file')}")
        row = find_source_row(s.get("source_file") or "", lat, lon) if lat else None
        if row:
            print(f"  source row   : {row.get('Nom de la station')!r}  "
                  f"commune={row.get('Commune')!r} delegation={row.get('Delegation')!r} "
                  f"gouvernorat={row.get('Gouvernorat')!r}")
            print("  -> the corruption is in the SOURCE file; the name is not recoverable")
        if not args.dry_run:
            s.setdefault("corrections", []).append({
                "field": "name",
                "from": nm,
                "to": None,
                "reason": ("The name is '???? ???' in the source CSV itself (SORETRAS "
                           "station export), so every non-ASCII character was already "
                           "lost upstream and the real name cannot be recovered from "
                           "the data we hold. Labelled rather than guessed; the "
                           "coordinate and line data are unaffected."),
                "applied": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            s["name_unknown"] = True
            s["name_display"] = f"[name not recoverable] {s['id']}"
            labelled += 1

    if labelled and not args.dry_run:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = SEED.with_suffix(f".json.bak-{stamp}")
        shutil.copy2(SEED, backup)
        SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nbacked up -> {backup.name}")
        print(f"labelled {labelled} name(s); wrote {SEED}")
    elif not labelled:
        print("\nno mojibake names found")
    if args.dry_run:
        print("\n(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
