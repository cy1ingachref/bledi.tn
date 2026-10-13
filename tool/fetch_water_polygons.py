#!/usr/bin/env python3
"""Fetch and cache OSM water polygons for Tunisia, for the station audit.

The audit needs to answer "is this point in water?" for 7 465 stops, so the
polygons must be local: 7 465 Overpass queries is not an option, and the public
instances rate-limit hard.

Fetched once, cached to data/water_polys.json, then re-read offline forever.

Two things learned the hard way, both encoded here:

  1. A single Tunisia-wide query times out (the main instance returned 504), so
     the bbox is fetched as tiles.
  2. Each tile is checkpointed to data/water_tiles/<key>.json the moment it
     lands. Without that, a 40-minute run that dies on tile 15 loses 14 tiles of
     work and re-fetches from scratch. With it, a re-run resumes.

    python tool/fetch_water_polygons.py            # resume/use cache
    python tool/fetch_water_polygons.py --force    # re-fetch every tile
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "water_polys.json"
TILE_DIR = ROOT / "data" / "water_tiles"

# Tunisia, S,W,N,E. Slightly wider than the country so a misplaced point just
# off the coast is still tested against the sea.
BBOX = (30.0, 7.0, 37.8, 12.0)

# Public Overpass instances, tried in order. The main instance 504s on this
# query size; the mail.ru mirror completes it.
ENDPOINTS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

UA = "bledi.tn-station-audit/1.0 (data integrity check; contact: repo owner)"

QUERY_BODY = """
[out:json][timeout:{timeout}];
(
  way["natural"="water"]({bbox});
  relation["natural"="water"]({bbox});
  way["natural"="coastline"]({bbox});
  way["natural"="bay"]({bbox});
  way["natural"="wetland"]({bbox});
  relation["natural"="wetland"]({bbox});
  way["waterway"="riverbank"]({bbox});
  way["landuse"="reservoir"]({bbox});
  relation["landuse"="reservoir"]({bbox});
);
out geom;
"""


def tiles(bbox: tuple[float, float, float, float], n: int):
    s, w, nn, e = bbox
    dlat = (nn - s) / n
    dlon = (e - w) / n
    for i in range(n):
        for j in range(n):
            yield (s + i * dlat, w + j * dlon, s + (i + 1) * dlat, w + (j + 1) * dlon)


def tile_key(bbox: tuple[float, float, float, float]) -> str:
    return "_".join(f"{v:.3f}".replace(".", "p") for v in bbox)


def fetch_tile(bbox: tuple[float, float, float, float], timeout: int = 180) -> list[dict]:
    s, w, n, e = bbox
    query = QUERY_BODY.format(bbox=f"{s},{w},{n},{e}", timeout=timeout)
    data = urllib.parse.urlencode({"data": query}).encode()

    last: Exception | None = None
    for url in ENDPOINTS:
        req = urllib.request.Request(
            url, data=data, headers={"User-Agent": UA, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout + 90) as r:
                payload = json.loads(r.read().decode("utf-8"))
            return payload.get("elements", [])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last = exc
            print(f"        {url.split('/')[2]}: {exc}", flush=True)
            # A 504 means the instance is overloaded, not that the query is
            # wrong. Backing off a few seconds is what turns a wall of 504s
            # into completed tiles.
            time.sleep(8)
    raise RuntimeError(f"all endpoints failed for {bbox}: {last}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-fetch even cached tiles")
    ap.add_argument("--tiles", type=int, default=4, help="n for an n x n split")
    ap.add_argument("--out", default=str(CACHE))
    args = ap.parse_args()

    TILE_DIR.mkdir(parents=True, exist_ok=True)
    tile_list = list(tiles(BBOX, args.tiles))
    print(f"water fetch: {len(tile_list)} tiles over {BBOX}")

    ok, failed = 0, []
    for idx, tb in enumerate(tile_list, 1):
        kf = TILE_DIR / f"{tile_key(tb)}.json"
        if kf.is_file() and not args.force:
            print(f"  [{idx}/{len(tile_list)}] cached {kf.name}", flush=True)
            ok += 1
            continue
        print(f"  [{idx}/{len(tile_list)}] fetching {tuple(round(v, 2) for v in tb)}", flush=True)
        try:
            els = fetch_tile(tb)
        except RuntimeError as exc:
            failed.append(tb)
            print(f"        FAILED: {exc}", flush=True)
            continue
        # Checkpoint immediately: a later failure must not cost this tile.
        kf.write_text(json.dumps({"elements": els, "bbox": tb}, ensure_ascii=False),
                      encoding="utf-8")
        print(f"        +{len(els)} elements -> {kf.name}", flush=True)
        ok += 1

    # Merge every checkpointed tile into one cache.
    merged: dict[tuple[str, int], dict] = {}
    for kf in sorted(TILE_DIR.glob("*.json")):
        for el in json.loads(kf.read_text(encoding="utf-8")).get("elements", []):
            merged[(el.get("type", "?"), int(el.get("id", 0)))] = el

    if not merged:
        print("FAILED: no tiles fetched; refusing to write an empty cache")
        return 1

    elements = list(merged.values())
    out = Path(args.out)
    out.write_text(
        json.dumps({"elements": elements, "bbox": BBOX, "tiles": args.tiles}, ensure_ascii=False),
        encoding="utf-8",
    )

    kinds: dict[str, int] = {}
    for el in elements:
        t = el.get("tags") or {}
        k = t.get("natural") or t.get("waterway") or t.get("landuse") or "?"
        kinds[k] = kinds.get(k, 0) + 1
    print(f"\nwrote {out} — {len(elements)} unique elements from {ok}/{len(tile_list)} tiles")
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v}")
    if failed:
        print(f"\nWARNING: {len(failed)} tile(s) missing — the water test is INCOMPLETE:")
        for tb in failed:
            print(f"  {tuple(round(v, 2) for v in tb)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
