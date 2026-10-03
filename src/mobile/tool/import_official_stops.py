#!/usr/bin/env python3
"""Import official operator stops that the seed does not have, into the seed.

The operator exports publish 3 171 stops; our seed carries 1 711 stations.
Adding the ~1 500 we are missing roughly doubles network coverage, and unlike
the earlier OSM work these positions come from the operators themselves.

What this adds, per stop:
  * a stable id derived from operator + name + position
  * name (Latin from the export), operator, mode
  * mode taken from the operator, never inferred from proximity
  * `source="official-open-data"` and `source_file`, so provenance survives

What it deliberately does NOT do:
  * guess a line for a stop. The exports publish stop positions, not line
    membership for every stop; the GTFS feeds do carry that, but only for the
    559 stops they list. Stops imported here have `lines_served: []` and the
    router will not route through them until line membership exists.
  * touch existing stations. Only genuinely new positions are added, so no
    id, name or mode of the curated 1 711 can be disturbed.

Refuses to overwrite an existing seed unless --out names a new file.

    python tool/import_official_stops.py --seed <in> --official stops.json \
        --out <corrected>
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from osm_common import haversine_m, norm  # noqa: E402

# Official mode -> our seed's vocabulary.
MODE_MAP = {
    "bus": "bus",
    "train": "train",
    "metro": "metro",
    "tram": "tram",
    "ferry": "ferry",
    "louage": "louage",
}


def slug(s: str) -> str:
    out = unicodedata.normalize("NFD", s or "")
    out = "".join(c for c in out if unicodedata.category(c) != "Mn").lower()
    return "".join(c if c.isalnum() else "_" for c in out).strip("_")[:48]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--official", required=True, help="parse_official_data.py output")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tolerance", type=float, default=120.0,
                    help="metres; closer than this counts as already present")
    args = ap.parse_args()

    seed_path = Path(args.seed)
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    # Copy: `data["stations"]` is a live reference, so extending it later would
    # also change `existing` and make the before/after counts identical.
    existing = list(data["stations"])
    before_count = len(existing)

    # Spatial + name index of what we already hold. Deduplication deliberately
    # considers only these pre-existing stations, never records added from the
    # same batch: several distinct places can share a position (a bus terminus
    # and the taxi rank outside it are 40 m apart), and inserting new records
    # into the index discarded all but the first of each such cluster.
    cell = max(args.tolerance / 111320.0, 1e-5)
    index: dict[tuple[int, int], list[dict]] = {}
    for s in existing:
        if s.get("lat") and s.get("lon"):
            index.setdefault((int(s["lat"] // cell), int(s["lon"] // cell)), []).append(s)
    existing_names = {norm(s.get("name", "")) for s in existing}
    # Names already claimed, so the same record twice in one source is still
    # caught even without touching the spatial index.
    claimed_names = set(existing_names)

    def near(lat: float, lon: float):
        best, bd = None, None
        ky, kx = int(lat // cell), int(lon // cell)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for c in index.get((ky + dy, kx + dx), []):
                    d = haversine_m(lat, lon, c["lat"], c["lon"])
                    if bd is None or d < bd:
                        best, bd = c, d
        return best, bd

    official = json.loads(Path(args.official).read_text(encoding="utf-8"))
    added: list[dict] = []
    skipped_position = 0
    skipped_name = 0

    for r in official:
        lat, lon = r.get("lat"), r.get("lon")
        if lat is None or lon is None:
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        # A stop we already hold under a near-identical name is not new.
        if norm(name) in claimed_names:
            skipped_name += 1
            continue
        hit, dist = near(lat, lon)
        if hit is not None and dist <= args.tolerance:
            # Same place, different wording — keep the curated record.
            skipped_position += 1
            continue

        mode = MODE_MAP.get(r.get("mode", ""), r.get("mode") or "unknown")
        digest = hashlib.sha1(
            f"{r.get('operator')}|{name}|{lat:.5f}|{lon:.5f}".encode("utf-8")
        ).hexdigest()[:10]
        rec = {
            "id": f"{slug(r.get('operator', 'op'))}_{slug(name)[:28]}_{digest}",
            "name": name,
            "name_en": name,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "mode": mode,
            "operator": r.get("operator", ""),
            # Carry the source's own provenance through instead of stamping
            # everything "official-open-data": a Google Places record has a
            # place_id and a raw type string that make it re-checkable, and
            # flattening those away loses the only way to audit it.
            "source": r.get("source") or "official-open-data",
            "source_file": Path(r.get("source_file", "")).name,
            "lines_served": [],
            "route_type": 3,
            "license_status": r.get("license_status", "official-public"),
        }
        for key in ("place_id", "type_raw", "source_sheet", "city",
                    "governorate", "address", "hours", "notes"):
            if r.get(key):
                rec[key] = r[key]
        added.append(rec)
        claimed_names.add(norm(name))

    data["stations"].extend(added)
    data["metadata"]["official_import"] = {
        "source": "tunisian open-data portal (operator exports)",
        "imported": len(added),
        "skipped_same_name": skipped_name,
        "skipped_same_position": skipped_position,
        "tolerance_m": args.tolerance,
    }

    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")

    print(f"seed stations before ....... {before_count}")
    print(f"official stops offered ..... {len(official)}")
    print(f"skipped, same name ......... {skipped_name}")
    print(f"skipped, same position ..... {skipped_position}")
    print(f"added ...................... {len(added)}")
    print(f"seed stations after ........ {len(data['stations'])}")

    print("\nadded by mode:")
    for m, n in collections.Counter(s["mode"] for s in added).most_common():
        print(f"  {m:10s} {n}")
    print("\nadded by operator:")
    for o, n in collections.Counter(s["operator"] for s in added).most_common():
        print(f"  {o:10s} {n}")

    named = sum(1 for s in added if s["name"])
    print(f"\nadded records carrying a name: {named}/{len(added)}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()