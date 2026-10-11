#!/usr/bin/env python3
"""Scrape the BizerteConnect bus network into the bledi.tn seed.

BizerteConnect (bizerteconnect.com) publishes its bus network through a public
JSON API used by its own /bus-schedules page. This script walks that API and
folds the result into data/seed_all_tunisia_routes.tagged.json.

What is scraped
  GET /api/v1/bus-lines/?page=N           -> every line (131, 20/page)
  GET /api/v1/bus-lines/{id}/timetable/   -> seasons -> trips -> OUTBOUND/RETURN
                                             -> departure times + Arabic notes

What is NOT available
  There is no public stops endpoint. Probed and confirmed 404:
  bus-stops/, bus-stations/, stops/, stations/, bus-trips/.
  /trips/, /season-schedules/, /bus-kpis/ return 401 (admin auth required).
  The public timetable carries origin/destination and the departure times for
  each direction, so this script imports lines + schedules, and only creates
  the origin/destination stop pairs it can prove.

Politeness: one request at a time with a delay, a real User-Agent, and
exponential backoff on 429/5xx. This is someone's small production API.

Usage:
    python scripts/scrape_bizerteconnect.py --dry-run
    python scripts/scrape_bizerteconnect.py --write
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"
CACHE = ROOT / "data" / "bizerteconnect_cache.json"
OUT_RAW = ROOT / "data" / "bizerteconnect_network.json"

API = "https://www.bizerteconnect.com/api/v1"
UA = "bledi.tn/1.0 (+https://github.com/cy1ingachref/bledi.tn; transit data import)"
DELAY_S = 0.7
TOLERANCE_M = 150.0


def fetch(path: str, tries: int = 4):
    """GET JSON with backoff. Returns None on a hard 404."""
    url = f"{API}{path}"
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(DELAY_S * (2 ** attempt))
                continue
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(DELAY_S * (2 ** attempt))
    return None


def hav(a, b, c, d):
    R = 6371000.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def slug(t: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "_" for c in str(t))
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")[:44] or "x"


def scrape_lines() -> list[dict]:
    """Walk the paginated bus-lines list."""
    lines, page = [], 1
    while True:
        data = fetch(f"/bus-lines/?page={page}")
        if not isinstance(data, dict) or "results" not in data:
            break
        lines.extend(data["results"])
        print(f"  page {page}: +{len(data['results'])} (total {len(lines)}/{data.get('count')})")
        if not data.get("next"):
            break
        page += 1
        time.sleep(DELAY_S)
    return lines


def scrape_timetables(lines: list[dict]) -> dict[str, dict]:
    """Fetch the timetable for each line id."""
    out = {}
    for i, ln in enumerate(lines, 1):
        tid = ln.get("id")
        if not tid:
            continue
        tt = fetch(f"/bus-lines/{tid}/timetable/")
        if tt:
            out[tid] = tt
        if i % 20 == 0:
            print(f"  timetables {i}/{len(lines)}")
        time.sleep(DELAY_S)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--from-cache", action="store_true",
                    help="reuse data/bizerteconnect_cache.json instead of re-fetching")
    args = ap.parse_args()
    if not (args.dry_run or args.write):
        ap.error("pass --dry-run or --write")

    # ---- 1. fetch (or reuse cache) -------------------------------------
    if args.from_cache and CACHE.exists():
        print(f"using cache {CACHE}")
        payload = json.loads(CACHE.read_text(encoding="utf-8"))
        lines = payload["lines"]
        timetables = payload["timetables"]
    else:
        print("=== scraping bus-lines ===")
        lines = scrape_lines()
        print(f"\n=== scraping {len(lines)} timetables ===")
        timetables = scrape_timetables(lines)
        CACHE.write_text(json.dumps({
            "source": f"{API}/bus-lines/",
            "scraped": time.strftime("%Y-%m-%d"),
            "lines": lines,
            "timetables": timetables,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"cached -> {CACHE}")

    if not lines:
        print("ERROR: no lines scraped", file=sys.stderr)
        return 2

    # ---- 2. normalise into lines + schedule ----------------------------
    # BizerteConnect uses "Bizerte" as the hub for most INTERNAL lines and a
    # named town as origin for the others. Both endpoints become stations.
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    stations = seed["stations"]
    existing_ids = {s["id"] for s in stations}

    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    CELL = 0.002
    for s in stations:
        try:
            la, lo = float(s["lat"]), float(s["lon"])
        except (TypeError, ValueError, KeyError):
            continue
        if la and lo:
            grid.setdefault((round(la / CELL), round(lo / CELL)), []).append((la, lo))

    def known(la: float, lo: float) -> bool:
        ci, cj = round(la / CELL), round(lo / CELL)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for sla, slo in grid.get((ci + di, cj + dj), ()):
                    if hav(la, lo, sla, slo) <= TOLERANCE_M:
                        return True
        return False

    # Bizerte hub coordinate (Bizerte - Central Station is already in the seed
    # from the louage CSV; reuse it as the anchor for hub endpoints).
    BIZERTE = (37.2675, 9.8722566)

    new_lines = []
    by_num = {}
    n_trips = n_times = 0
    season_names = set()

    for ln in lines:
        num = str(ln.get("number") or "").strip()
        name = str(ln.get("name") or "").strip()
        if not num and not name:
            continue
        tt = timetables.get(ln.get("id") or "") or {}

        # collect departure times per direction, across all seasons
        outbound, ret = [], []
        for s in tt.get("seasons") or []:
            sea = s.get("season") or {}
            if sea.get("name"):
                season_names.add(sea["name"])
            for trip in s.get("trips") or []:
                n_trips += 1
                times = [t.get("departure_time") for t in (trip.get("times") or [])
                         if t.get("departure_time")]
                n_times += len(times)
                hhmm = [t[:5] for t in times]
                if str(trip.get("direction", "")).upper() == "RETURN":
                    ret.extend(hhmm)
                else:
                    outbound.extend(hhmm)

        origin = str(ln.get("origin") or "").strip()
        dest = str(ln.get("destination") or "").strip()
        lid = f"bc_bus_{slug(num)}_{slug(name)[:24]}"
        if lid in existing_ids or lid in by_num:
            continue
        by_num[lid] = True

        new_lines.append({
            "id": lid,
            "number": num or name[:8],
            "name": f"BizerteConnect {num}: {origin} - {dest}".strip(" :"),
            "operator": "BizerteConnect",
            "mode": "bus",
            "type": "internal" if str(ln.get("type", "")).upper() == "INTERNAL" else "regional",
            "route_id": num or lid,
            # The seed's schema wants station ids; only the hub pairs are
            # provable from this API, so the line carries its named endpoints
            # and the schedule, and stations[] stays empty rather than inventing
            # geometry the source does not publish.
            "stations": [],
            "origin": origin,
            "destination": dest,
            "origin_ar": ln.get("origin_ar") or "",
            "destination_ar": ln.get("destination_ar") or "",
            "departures": sorted(set(outbound)),
            "return_departures": sorted(set(ret)),
            "source": "bizerteconnect-api",
            "license_status": "third-party-public-api",
            "external_id": ln.get("id"),
        })

    by_mode = {"bus": len(new_lines)}
    total_out = sum(len(l["departures"]) for l in new_lines)
    total_ret = sum(len(l["return_departures"]) for l in new_lines)

    print(f"\nlines scraped        : {len(lines)}")
    print(f"new lines to add     : {len(new_lines)}")
    print(f"trips seen           : {n_trips}")
    print(f"departure times seen : {n_times}")
    print(f"outbound times kept  : {total_out}")
    print(f"return times kept    : {total_ret}")
    print(f"seasons              : {sorted(season_names)}")
    print(f"stops endpoint       : NOT PUBLISHED (404 on every candidate path)")

    if not new_lines:
        print("\nNothing to add.")
        return 0

    if args.dry_run:
        print("\n--dry-run: seed NOT modified. Sample:")
        for l in new_lines[:6]:
            print(f"  {l['number']:6s} {l['name'][:52]:54s} out={len(l['departures']):2d} ret={len(l['return_departures']):2d}")
        return 0

    # ---- 3. write ------------------------------------------------------
    OUT_RAW.write_text(json.dumps({
        "source": f"{API}/bus-lines/",
        "scraped": time.strftime("%Y-%m-%d"),
        "line_count": len(lines),
        "timetable_count": len(timetables),
        "lines": lines,
        "timetables": timetables,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    seed["lines"] = seed["lines"] + new_lines
    md = seed.setdefault("metadata", {})
    md["total_lines"] = len(seed["lines"])
    md["bizerteconnect_import"] = {
        "source": f"{API}/bus-lines/",
        "lines_added": len(new_lines),
        "trips": n_trips,
        "departure_times": n_times,
        "outbound_kept": total_out,
        "return_kept": total_ret,
        "seasons": sorted(season_names),
        "stops_available": False,
        "stops_note": ("No public stops endpoint; 404 on bus-stops/, bus-stations/, "
                       "stops/, stations/, bus-trips/. /trips/ and /season-schedules/ "
                       "require auth. Lines therefore carry named endpoints + schedule."),
    }
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nWrote {SEED} ({len(seed['stations'])} stations, {len(seed['lines'])} lines).")
    print(f"Raw scrape -> {OUT_RAW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
