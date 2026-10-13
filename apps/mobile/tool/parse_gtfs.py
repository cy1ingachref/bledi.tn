#!/usr/bin/env python3
"""Parse the GTFS feeds and metro/rural line lists into one JSON file.

Source: C:\\Users\\cy1in\\Downloads\\transport — Tunisian open-data portal,
fetched 2026-10-03.

Three kinds of input, handled separately:

  * GTFS zip feeds (TRANSTU, SORETRAK, SRTJ, SNTRI) — routes, trips and
    stop_times, which give the full ordered stop sequence of every trip.
    This is the only source of "where does it start, where does it stop".
  * Metro line→station order ("Arrêts par lignes ... réseau métro") — the
    TGM lines are not in a GTFS feed, only their station order is.
  * Rural and taxi-collective line names ("Le transport en milieu rural") —
    these are stop sequences written as `A-B-C-D` in a single cell, with no
    coordinates anywhere. They can be listed but not mapped.

Output JSON, one array per kind:
  routes  — {operator, route_id, short_name, long_name, mode, trips:[...]}
  stops   — every stop with coordinates, from GTFS plus the operator exports

Read-only. Writes only --out.

    python tool/parse_gtfs.py --src <dir> --out network.json
"""

from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import re
import zipfile
from pathlib import Path

# Which feed directories are GTFS, and what mode each agency's routes are.
GTFS_FEEDS = {
    "Horaires des voyages de la TRANSTU (GTFS)": "TRANSTU",
    "Horaires des bus de la SORETRAK - GTFS": "SORETRAK",
    "Horaires des voyages de la société régionale du transport du Jendouba SRTJ (GTFS)": "SRTJ",
    "Horaires des bus de la SNTRI - GTFS": "SNTRI",
}

# GTFS route_type -> our vocabulary. 3=bus, 1=subway/metro, 2=rail, 0=tram.
ROUTE_TYPE_MODE = {
    "0": "tram",
    "1": "metro",
    "2": "train",
    "3": "bus",
    "4": "ferry",
    "5": "tram",
    "6": "metro",
    "7": "funicular",
}

# A stray tab survives in some TRANSTU stop_ids ("echebbi_retour\t").
ID_JUNK = re.compile(r"[\t\r\n]+")


def _read(zf: zipfile.ZipFile, name: str) -> list[dict]:
    if name not in zf.namelist():
        return []
    raw = zf.read(name).decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(raw)))


def _clean(v) -> str:
    return ID_JUNK.sub("", (v or "")).strip()


def _num(v) -> float | None:
    """Parse a number that may use a comma decimal separator."""
    s = (v or "").strip()
    if not s:
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _lat(v) -> float | None:
    """Latitude, if it is inside Tunisia."""
    f = _num(v)
    return f if f is not None and 30.0 <= f <= 38.0 else None


def _lon(v) -> float | None:
    """Longitude, if it is inside Tunisia."""
    f = _num(v)
    return f if f is not None and 6.5 <= f <= 12.5 else None


def _mode_for(route_type: str, route: dict) -> str:
    """Resolve a route's mode, trusting the name over a wrong route_type.

    TRANSTU's `ligneTGM` — the metro/light-rail line — is published with
    `route_type=4`, which GTFS defines as ferry. Trusting the tag alone files
    134 metro trips as a ferry service. The route name is unambiguous here, so
    it wins when the tag disagrees with an explicit TGM/ligh-rail marker.
    """
    name = " ".join(
        [
            (route.get("route_short_name") or ""),
            (route.get("route_long_name") or ""),
            route_type,
        ]
    ).lower()
    if "tgm" in name or "light rail" in name or "light_rail" in name:
        return "metro"
    return ROUTE_TYPE_MODE.get(route_type, "bus")


def parse_gtfs(path: Path, operator: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (routes with ordered stop sequences, trips, stops)."""
    zf = zipfile.ZipFile(path)
    routes = {_clean(r["route_id"]): r for r in _read(zf, "routes.txt")}
    trips = {_clean(t["trip_id"]): t for t in _read(zf, "trips.txt")}

    stops: dict[str, dict] = {}
    for s in _read(zf, "stops.txt"):
        sid = _clean(s.get("stop_id"))
        lat, lon = _lat(s.get("stop_lat")), _lon(s.get("stop_lon"))
        if not sid or lat is None or lon is None:
            continue
        stops[sid] = {
            "stop_id": sid,
            "name": (s.get("stop_name") or "").strip(),
            "lat": lat,
            "lon": lon,
            "operator": operator,
        }

    # stop_times: (trip_id, stop_id) -> sequence + times, then group per trip.
    by_trip: dict[str, list[tuple[int, str, str, str]]] = {}
    for st in _read(zf, "stop_times.txt"):
        tid = _clean(st.get("trip_id"))
        sid = _clean(st.get("stop_id"))
        if not tid or not sid:
            continue
        try:
            seq = int(st.get("stop_sequence") or 0)
        except ValueError:
            seq = 0
        by_trip.setdefault(tid, []).append(
            (seq, sid, (st.get("arrival_time") or "").strip(),
             (st.get("departure_time") or "").strip())
        )

    out_routes: list[dict] = []
    out_trips: list[dict] = []
    for tid, entries in by_trip.items():
        entries.sort(key=lambda e: e[0])
        trip = trips.get(tid)
        if not trip:
            continue
        rid = _clean(trip.get("route_id"))
        route = routes.get(rid)
        if not route:
            continue
        mode = ROUTE_TYPE_MODE.get((route.get("route_type") or "").strip(), "bus")
        # Trips reference stops; some may be absent from stops.txt.
        seq = [
            {
                "sequence": s,
                "stop_id": sid,
                "name": stops.get(sid, {}).get("name", sid),
                "lat": stops.get(sid, {}).get("lat"),
                "lon": stops.get(sid, {}).get("lon"),
                "arrival": a,
                "departure": d,
            }
            for s, sid, a, d in entries
        ]
        known = [e for e in seq if e["lat"] is not None]
        if not known:
            # A trip whose every stop is unmapped cannot be drawn; skip it
            # rather than emit a route with no geometry.
            continue
        out_trips.append(
            {
                "operator": operator,
                "mode": mode,
                "trip_id": tid,
                "route_id": rid,
                "headsign": (trip.get("trip_headsign") or "").strip(),
                "direction_id": (trip.get("direction_id") or "").strip(),
                "origin": known[0]["name"],
                "destination": known[-1]["name"],
                "stop_count": len(seq),
                "stops": seq,
            }
        )

    # One record per route, not per trip: a route is a line, and 262 trips
    # across 5 lines is not 262 lines.
    routes_out: dict[str, dict] = {}
    for rid, route in routes.items():
        rtype = (route.get("route_type") or "").strip()
        routes_out[rid] = {
            "operator": operator,
            "mode": _mode_for(rtype, route),
            "route_id": rid,
            "route_short_name": (route.get("route_short_name") or "").strip(),
            "route_long_name": (route.get("route_long_name") or "").strip(),
            "route_color": (route.get("route_color") or "").strip(),
            "gtfs_route_type": rtype,
            "trip_count": 0,
        }
    # A route_type the mapping does not recognise still gets its trips counted.
    trips_by_route: dict[str, list[dict]] = {}
    for t in out_trips:
        r = routes_out.get(t["route_id"])
        if r is not None:
            r["trip_count"] += 1
            trips_by_route.setdefault(t["route_id"], []).append(t)
    # Carry each route's mode onto its trips so downstream need not re-derive it.
    for t in out_trips:
        r = routes_out.get(t["route_id"])
        if r is not None:
            t["mode"] = r["mode"]

    for r in routes_out.values():
        ts = trips_by_route.get(r["route_id"], [])
        r["origin"] = ts[0]["origin"] if ts else ""
        r["destination"] = ts[0]["destination"] if ts else ""
        r["stop_count"] = ts[0]["stop_count"] if ts else 0

    return list(routes_out.values()), out_trips, list(stops.values())


def parse_metro_lines(path: Path) -> list[dict]:
    """`N° de la ligne;N° de station;Non de station` — TGM line station order."""
    rows: dict[str, list[dict]] = {}
    for f in sorted(path.glob("*.csv")):
        raw = f.read_text(encoding="utf-8-sig", errors="replace")
        for line in raw.splitlines():
            cells = [c.strip() for c in line.split(";")]
            if len(cells) < 3:
                continue
            if "ligne" in cells[0].lower():  # header
                continue
            line_no, seq, name = cells[0], cells[1], cells[2]
            if not line_no or not seq:
                continue
            try:
                rows.setdefault(line_no, []).append({"sequence": int(seq), "name": name})
            except ValueError:
                continue
    out = []
    for line_no, stations in sorted(rows.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        stations.sort(key=lambda s: s["sequence"])
        out.append(
            {
                "operator": "TGM",
                "mode": "metro",
                "line": line_no,
                "stop_count": len(stations),
                "origin": stations[0]["name"],
                "destination": stations[-1]["name"],
                "stations": [s["name"] for s in stations],
            }
        )
    return out


def parse_rural_lines(path: Path) -> list[dict]:
    """Rural / taxi-collective line names.

    These encode their stops as `A-B-C-D` in one cell and carry no coordinates,
    so they can be listed but not mapped. Recording them as unmapped is honest;
    silently dropping them would hide real services.
    """
    out: list[dict] = []
    for f in sorted(path.rglob("*.xlsx")):
        kind = "taxi_collectif" if "taxi" in f.parent.name.lower() else "rural"
        try:
            zf = zipfile.ZipFile(f)
            shared = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
        except (KeyError, zipfile.BadZipFile):
            continue
        cells = re.findall(r"<t[^>]*>([^<]*)</t>", shared)
        for raw in cells:
            name = raw.replace("_x000D_", " ").strip()
            if not name or "," not in name and "-" not in name:
                continue
            # Strip the French/Arabic "LIGNE:"/"الخط" prefixes.
            cleaned = re.sub(r"^(LIGNE[:\s]*|ligne[:\s]*|الخط\.?|الخط)", "", name).strip()
            cleaned = cleaned.rstrip("*").strip()
            parts = [p.strip() for p in cleaned.split("-") if p.strip()]
            if len(parts) < 2:
                continue
            out.append(
                {
                    "operator": "rural/taxi",
                    "mode": "louage",
                    "kind": kind,
                    "source_file": str(f.relative_to(path)),
                    "origin": parts[0],
                    "destination": parts[-1],
                    "stop_count": len(parts),
                    "stops": parts,
                    "mapped": False,  # no coordinates published for these
                }
            )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.src)
    routes: list[dict] = []
    trips: list[dict] = []
    stops: dict[tuple, dict] = {}

    print("=== GTFS feeds ===")
    for sub, operator in GTFS_FEEDS.items():
        zips = sorted((root / sub).glob("*.zip"))
        if not zips:
            print(f"  {operator:9s} MISSING ({sub})")
            continue
        r, t, s = parse_gtfs(zips[0], operator)
        routes.extend(r)
        trips.extend(t)
        for st in s:
            stops.setdefault((st["operator"], round(st["lat"], 5), round(st["lon"], 5)), st)
        print(f"  {operator:9s} routes={len(r):3d} trips={len(t):4d} stops={len(s):4d}  ({zips[0].name[:12]})")

    print("\n=== metro line order (not in any GTFS feed) ===")
    metro_dir = root / "Arrêts par lignes de transport du réseau métro de la transtu"
    metro = parse_metro_lines(metro_dir) if metro_dir.is_dir() else []
    for m in metro:
        print(f"  line {m['line']:>2s}  {m['stop_count']:3d} stations  "
              f"{m['origin'][:26]:26s} -> {m['destination'][:26]}")
    print(f"  {len(metro)} metro lines")

    print("\n=== rural / taxi-collective lines (names only, no coordinates) ===")
    rural_dir = root / "Le transport en milieu rural"
    rural = parse_rural_lines(rural_dir) if rural_dir.is_dir() else []
    print(f"  {len(rural)} lines, all unmapped (stop names published, not positions)")

    payload = {
        "source": str(root),
        "generated": "parse_gtfs.py",
        "routes": routes,
        "trips": trips,
        "stops": list(stops.values()),
        "metro_lines": metro,
        "rural_lines": rural,
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    print(f"\ntotals: routes={len(routes)} trips={len(trips)} "
          f"stops={len(stops)} metro_lines={len(metro)} rural_lines={len(rural)}")

    import collections

    print("\ntrips by operator and mode:")
    for key, n in collections.Counter((t["operator"], t["mode"]) for t in trips).most_common():
        print(f"  {key[0]:9s} {key[1]:6s} {n}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()