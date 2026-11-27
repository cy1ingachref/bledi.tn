#!/usr/bin/env python3
"""Find the CORRECT coordinates for the 5 mis-placed stations.

The seed has these at wrong points (4 are inside Lake Ichkeul / Tunis, and one
is an Arabic-named rural stop). The official operator exports in
Downloads/tunisia-transport-data should carry the right position, and where
they do not, Nominatim is the fallback. Every candidate is printed with its
source so the choice is auditable rather than assumed.

    python tool/find_station_coords.py
"""

from __future__ import annotations
from pathlib import Path

import csv
import json
import re
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
DUMP = (Path.home() / "Downloads" / "TunisiaTransport")
OUT = ROOT / "out" / "station-coord-candidates.json"

TARGETS = {
    "croisement ghorfa": "Croisement ghorfa",
    "douane bir mouzaina": "Douane Bir Mouzaina",
    "bir mouzaina": "Bir Mouzaina",
    "ajim": "Ajim",
    "محطة خاصة السيارات النقل الريفي": "محطة خاصة السيارات النقل الريفي",
}

# Normalise Arabic and accents so matching is not defeated by diacritics.
def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", s)  # Arabic diacritics + tatweel
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ى", "ي").replace("ة", "ه")
    s = re.sub(r"[^0-9a-z\u0600-\u06ff]+", " ", s)
    return " ".join(s.split())


LAT_KEYS = ("lat", "latitude", "y", "gps_lat", "y_wgs84", "lat_wgs84", "latitude_wgs84")
LON_KEYS = ("lon", "lng", "long", "longitude", "x", "gps_lon", "x_wgs84", "lon_wgs84", "longitude_wgs84")
NAME_KEYS = ("name", "nom", "station", "libelle", "libellé", "arret", "arrêt", "designation", "intitule",
             "nom_station", "nom de la station", "station_name", "name_fr", "nom_fr", "label")


def pick(rec: dict, keys) -> str | None:
    for k in rec:
        if str(k).strip().lower() in keys:
            return rec[k]
    return None


def scan_csv(path: Path, hits: list) -> None:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:  # noqa: BLE001
        return
    try:
        rows = list(csv.DictReader(text.splitlines()))
    except Exception:  # noqa: BLE001
        return
    for r in rows:
        nm = pick(r, NAME_KEYS)
        if nm is None:
            continue
        n = norm(str(nm))
        for key, label in TARGETS.items():
            if key in n or n in key:
                la, lo = pick(r, LAT_KEYS), pick(r, LON_KEYS)
                hits.append({
                    "target": label, "matched": str(nm), "lat": la, "lon": lo,
                    "source": f"{path.relative_to(DUMP)}",
                })


def scan_json(path: Path, hits: list) -> None:
    try:
        if path.stat().st_size > 40_000_000:
            return
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return

    def walk(o):
        if isinstance(o, dict):
            nm = pick(o, NAME_KEYS)
            if nm is not None:
                n = norm(str(nm))
                for key, label in TARGETS.items():
                    if key in n or n in key:
                        hits.append({
                            "target": label, "matched": str(nm),
                            "lat": pick(o, LAT_KEYS), "lon": pick(o, LON_KEYS),
                            "source": f"{path.relative_to(DUMP)}",
                        })
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)


def main() -> int:
    hits: list[dict] = []
    # Only text-ish formats; xlsx/xls need a reader, handled separately if needed.
    for p in DUMP.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext == ".csv":
            scan_csv(p, hits)
        elif ext == ".json":
            scan_json(p, hits)

    # Also the live seed, so we can see the WRONG value beside the candidates.
    seed = json.loads((ROOT / "data" / "seed_all_tunisia_routes.tagged.json").read_text(encoding="utf-8"))
    print("=== current (wrong) values in the seed ===")
    current = {}
    for s in seed["stations"]:
        n = norm(s.get("name", ""))
        for key, label in TARGETS.items():
            if key in n or n in key:
                current.setdefault(label, []).append(
                    {"id": s["id"], "name": s["name"], "lat": s.get("lat"), "lon": s.get("lon")}
                )
    for label, rows in current.items():
        for r in rows:
            print(f"  {label[:34]:34s} {r['lat']},{r['lon']}  id={r['id']}")

    print(f"\n=== candidate coordinates found in the data dump ({len(hits)}) ===")
    for label in TARGETS.values():
        rows = [h for h in hits if h["target"] == label]
        print(f"\n  {label}")
        if not rows:
            print("    (no coordinate-bearing match found)")
        seen = set()
        for h in rows[:12]:
            k = (str(h["lat"]), str(h["lon"]), h["source"])
            if k in seen:
                continue
            seen.add(k)
            print(f"    {str(h['matched'])[:34]:34s} lat={str(h['lat'])[:12]:12s} lon={str(h['lon'])[:12]:12s}  {h['source']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"current": current, "candidates": hits}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
