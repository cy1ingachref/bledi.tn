#!/usr/bin/env python3
"""Resolve `mode: unknown` stations using the official rail exports.

54 of the seed's 130 `unknown` stations sit at 0 m from a stop in the SNCFT's
own published file — they are rail halts that were never classified. Leaving
them `unknown` renders them in the fallback colour on the map and excludes them
from the rail filter, so a rail station the operator publishes is invisible as
one.

Only exact-evidence matches are changed:

  * the station must lie within --tolerance metres of an SNCFT stop, AND
  * the names must agree once normalised, OR the distance must be ~0

A name match far from the official coordinate is *not* applied: that is the
signature of two different places sharing a name, and the OSM audit already
found 30-odd of those across Tunisia.

Every other `unknown` is left alone. Being unclassified is honest; being
wrongly classified is not.

    python tool/resolve_unknown_modes.py --seed in.json --out out.json
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from osm_common import haversine_m, norm  # noqa: E402
from parse_official_data import sniff  # noqa: E402

RAIL_DIR = "Position géographique des stations du réseau ferré de la SNCFT"


def load_rail(src: Path) -> list[dict]:
    out: list[dict] = []
    for f in sorted((src / RAIL_DIR).glob("*.csv")):
        text, delim = sniff(Path(f))
        for row in csv.DictReader(io.StringIO(text), delimiter=delim):
            try:
                lat = float(row.get("stop_lat", ""))
                lon = float(row.get("stop_lon", ""))
            except (TypeError, ValueError):
                continue
            if 30.0 <= lat <= 38.0 and 6.5 <= lon <= 12.5:
                out.append({"name": row.get("stop_name", "").strip(),
                            "lat": lat, "lon": lon,
                            "code": row.get("stop_code", "")})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--src", default=r"C:\Users\cy1in\Downloads\transport",
                    help="root of the portal export, for the SNCFT rail file")
    ap.add_argument("--tolerance", type=float, default=150.0)
    ap.add_argument("--exact-metres", type=float, default=25.0,
                    help="at this distance a name match is not required")
    args = ap.parse_args()

    rail = load_rail(Path(args.src))
    if not rail:
        print(f"no SNCFT rail stops found under {args.src / RAIL_DIR}")
        return 1
    data = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    stations = data["stations"]
    unknown = [s for s in stations if s.get("mode") == "unknown"]

    resolved: list[tuple[dict, dict, float]] = []
    skipped_far: list[tuple[dict, dict, float]] = []
    for s in unknown:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        best = min(rail, key=lambda r: haversine_m(s["lat"], s["lon"], r["lat"], r["lon"]))
        dist = haversine_m(s["lat"], s["lon"], best["lat"], best["lon"])
        if dist > args.tolerance:
            continue
        names_agree = norm(s.get("name", "")) == norm(best["name"])
        if names_agree or dist <= args.exact_metres:
            resolved.append((s, best, dist))
        else:
            # Close, but a different name: two places, not a misclassification.
            skipped_far.append((s, best, dist))

    for s, best, dist in resolved:
        s["mode"] = "train"
        s["mode_source"] = "official-sncft-rail-export"
        s["mode_evidence"] = (
            f"{best['name']} ({best['code']}) at {dist:.0f} m "
            f"in the SNCFT rail export"
        )

    data["metadata"]["unknown_mode_resolution"] = {
        "source": RAIL_DIR,
        "resolved": len(resolved),
        "left_unknown": len(unknown) - len(resolved),
        "rejected_name_mismatch": len(skipped_far),
        "tolerance_m": args.tolerance,
        "exact_metres": args.exact_metres,
    }
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")

    print(f"SNCFT rail stops read .......... {len(rail)}")
    print(f"unknown stations in seed ....... {len(unknown)}")
    print(f"resolved to train .............. {len(resolved)}")
    print(f"rejected on name mismatch ...... {len(skipped_far)}")
    print(f"still unknown ................. "
          f"{len(unknown) - len(resolved)}")
    if skipped_far:
        print("\nrejected (close by, different name — likely a namesake):")
        for s, best, d in skipped_far[:10]:
            print(f"  {s['name'][:26]:26s} {d:5.0f} m from {best['name'][:26]}")
    print("\nresolved sample:")
    for s, best, d in resolved[:10]:
        print(f"  {s['name'][:26]:26s} {d:4.0f} m  <- {best['name'][:26]}")
    modes = collections.Counter(s.get("mode") for s in stations)
    print(f"\nmode totals now: {dict(modes)}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())