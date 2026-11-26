#!/usr/bin/env python3
"""Rebuild the transit seed from OPEN sources only (owner decision 1).

This script does NOT touch `data/seed_all_tunisia_routes.json` or any other
source seed (brief rule 3). It reads Overpass-style JSON exports of OSM
public-transport data and writes a *derived* seed:

    data/seed_open_source.json

Inputs (all optional, all derived from OpenStreetMap, ODbL):
  - an Overpass JSON export containing nodes with `public_transport=stop_position`
    / `highway=bus_stop` / `railway=station` etc. and relations of type
    `route=bus|train|tram|subway` with `member` roles;
  - the existing `data/osm_overpass/taxi_louage_stations.json` for taxi/louage
    hubs (already OSM-derived and committed).

Fetch an export (run where the Overpass API is reachable), e.g.:

    curl -G --data-urlencode 'data=[out:json][timeout:180];
      area["name"="Tunisie"]->.a;
      (node(area.a)["public_transport"];
       node(area.a)["highway"="bus_stop"];
       node(area.a)["railway"="station"];
       relation(area.a)["type"="route"]["route"];
      );
      out body; >; out skel qt;' \
      https://overpass-api.de/api/interpreter > data/osm_overpass/tunisia_pt.json

Then:

    python scripts/rebuild_seed_from_osm.py data/osm_overpass/tunisia_pt.json

Output shape matches the runtime seed closely enough for the importers:
{ "metadata": {...}, "stations": [...], "lines": [...] }

Stations carry `source: "osm"`, `license_status: "odbl"`, and an OSM id so
attribution is auditable. Lines carry `source: "osm"`, `license_status: "odbl"`,
mode, operator, and ordered stop ids from the route relation members.

NOTE: the rebuild is staged. This first slice produces the derived file and a
provenance report; switching the services to read it is a separate, tested
task (do not silently swap the seed under a green test suite).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT = REPO / "data" / "osm_overpass" / "tunisia_pt.json"
OUT = REPO / "data" / "seed_open_source.json"
LOUAGE = REPO / "data" / "osm_overpass" / "taxi_louage_stations.json"

MODE_MAP = {
    "bus": "bus",
    "train": "train",
    "rail": "rail",
    "tram": "tram",
    "subway": "metro",
    "metro": "metro",
    "ferry": "ferry",
}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def elements(payload):
    if isinstance(payload, dict) and "elements" in payload:
        return payload["elements"]
    if isinstance(payload, list):
        return payload
    raise ValueError("unrecognised Overpass export shape")


def osm_stations(els):
    stations = {}
    for el in els:
        if el.get("type") != "node":
            continue
        tags = el.get("tags") or {}
        lat, lon = el.get("lat"), el.get("lon")
        if lat is None or lon is None:
            continue
        mode = None
        if tags.get("public_transport") in ("stop_position", "platform", "station"):
            mode = MODE_MAP.get(tags.get("mode") or "")
            if not mode:
                if tags.get("railway") in ("station", "halt", "tram_stop"):
                    mode = "train" if tags.get("railway") != "tram_stop" else "tram"
                elif tags.get("amenity") == "bus_station" or tags.get("highway") == "bus_stop":
                    mode = "bus"
                elif tags.get("amenity") == "ferry_terminal":
                    mode = "ferry"
        if not mode:
            continue
        name = tags.get("name") or tags.get("name:fr") or f"osm-node-{el['id']}"
        stations[f"osm:{el['id']}"] = {
            "id": f"osm:{el['id']}",
            "name": name,
            "name_ar": tags.get("name:ar", ""),
            "name_fr": tags.get("name:fr", ""),
            "name_en": tags.get("name:en", ""),
            "lat": lat,
            "lon": lon,
            "mode": mode,
            "operator": tags.get("operator", ""),
            "source": "osm",
            "license_status": "odbl",
            "osm_id": el["id"],
        }
    return stations


def osm_lines(els, stations):
    lines = []
    node_to_id = {
        sid.rsplit(":", 1)[1]: sid
        for sid in stations
        if sid.startswith("osm:")
    }
    for el in els:
        if el.get("type") != "relation":
            continue
        tags = el.get("tags") or {}
        route = tags.get("route")
        if route not in MODE_MAP:
            continue
        stops = []
        for m in el.get("members", []):
            if m.get("type") == "node" and str(m.get("ref")) in node_to_id:
                sid = node_to_id[str(m["ref"])]
                if sid not in stops:
                    stops.append(sid)
        if not stops:
            continue
        lines.append({
            "id": f"osm:route:{el['id']}",
            "name": tags.get("name") or tags.get("ref") or f"route-{el['id']}",
            "number": tags.get("ref", ""),
            "mode": MODE_MAP[route],
            "operator": tags.get("operator", ""),
            "stops": stops,
            "source": "osm",
            "license_status": "odbl",
            "osm_id": el["id"],
        })
    return lines


def louage_stations():
    if not LOUAGE.exists():
        return []
    data = load_json(LOUAGE)
    out = []
    for s in data.get("stations", []):
        out.append({
            "id": f"osm:louage:{s['id']}",
            "name": s.get("name") or f"louage-{s['id']}",
            "name_ar": s.get("name_ar", ""),
            "lat": s["lat"],
            "lon": s["lon"],
            "mode": "louage",
            "operator": s.get("operator", "Louage"),
            "source": "osm",
            "license_status": "odbl",
            "osm_id": s["id"],
            "louage_route_type": s.get("louage_route_type", "local"),
        })
    return out


def main():
    export = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXPORT
    if not export.exists():
        print(f"ERROR: OSM export not found: {export}", file=sys.stderr)
        print("Fetch it with the Overpass query in this script's docstring.", file=sys.stderr)
        return 2
    payload = load_json(export)
    els = elements(payload)
    stations = osm_stations(els)
    lines = osm_lines(els, stations)
    for s in louage_stations():
        stations.setdefault(s["id"], s)

    served = {sid for line in lines for sid in line["stops"]}
    for sid in served:
        if sid in stations:
            stations[sid].setdefault("lines_served", []).append(
                next(line["id"] for line in lines if sid in line["stops"])
            )

    out = {
        "metadata": {
            "source": "OpenStreetMap (ODbL) public-transport exports + OSM taxi/louage hubs",
            "license": "ODbL — attribution required",
            "generated_by": "scripts/rebuild_seed_from_osm.py",
            "input_export": str(export.relative_to(REPO)) if export.is_relative_to(REPO) else str(export),
            "total_lines": len(lines),
            "total_stations": len(stations),
        },
        "stations": list(stations.values()),
        "lines": lines,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"wrote {OUT.relative_to(REPO)}: {len(stations)} stations, {len(lines)} lines")
    print("source data: OpenStreetMap (ODbL). Attribute OSM in the UI and docs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
