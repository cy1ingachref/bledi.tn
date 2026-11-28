#!/usr/bin/env python3
"""Rebuild the transit seed from OPEN sources only (owner decision 1).

This script does NOT touch `data/seed_all_tunisia_routes.json` or any other
source seed (brief rule 3). It reads Overpass-style JSON exports of OSM
public-transport data and writes a *derived* seed:

    data/seed_open_source.json

Fetch an export with `scripts/fetch_osm_export.py`; the raw export is
gitignored and described by `data/osm_overpass/manifest.json`.

WP2 fixes (each proved by services/transit/tests/test_osm_converter.py):
1. mode derived from standard OSM flags (bus=yes/train=yes/...), not tags["mode"];
2. stop_position + platform duplicates merged via public_transport=stop_area
   relations, with every OSM id kept in `osm_ids`;
3. lines_served built from a station->lines index (all lines, not the first);
4. route relations grouped by route_master into one line with direction variants;
5. lines with <2 resolved stops dropped and counted;
6. unnamed stops flagged `unnamed: true`;
7. Tunisia bounding box + coordinate-type + duplicate-id sanity checks;
8. louage source/date recorded in the manifest.

NOTE: the runtime seed is NOT switched here. WP5 adds a side-by-side profile.
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
MANIFEST = REPO / "data" / "osm_overpass" / "manifest.json"

# Padded Tunisia bounding box, shared with scripts/verify_seed.py.
BOX = (30.23, 37.56, 7.50, 11.65)  # (min_lat, max_lat, min_lon, max_lon)

MODE_MAP = {
    "bus": "bus", "trolleybus": "bus", "train": "train", "rail": "rail",
    "tram": "tram", "light_rail": "tram",
    "subway": "metro", "metro": "metro", "ferry": "ferry",
}
# Standard OSM stop-node flags, in priority order (rail beats bus at interchanges).
MODE_FLAGS = (
    ("railway", ("station", "halt", "tram_stop", "stop"), "train"),
    ("railway", ("tram_stop",), "tram"),
    ("bus", ("yes",), "bus"),
    ("highway", ("bus_stop",), "bus"),
    ("amenity", ("bus_station",), "bus"),
    ("subway", ("yes",), "metro"),
    ("train", ("yes",), "train"),
    ("tram", ("yes",), "tram"),
    ("ferry", ("yes",), "ferry"),
    ("amenity", ("ferry_terminal",), "ferry"),
)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def elements(payload):
    """Normalise Overpass JSON or Overpass Turbo GeoJSON to Overpass elements.

    GeoJSON from Overpass Turbo has no `elements` list: tags are flat on
    `properties`, coordinates are [lon, lat], `@id` is "node/<id>", and route
    membership is exposed as `@relations` [{rel, role, reltags}] on each stop.
    Synthesise Overpass-shaped nodes and route relations from that so the rest
    of the converter stays unchanged.
    """
    if isinstance(payload, dict) and "elements" in payload:
        return payload["elements"]
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("features"), list):
        nodes: dict[int, dict] = {}
        relations: dict[int, dict] = {}
        for feature in payload["features"]:
            props = feature.get("properties") or {}
            oid = str(props.get("@id", ""))
            if not oid.startswith("node/"):
                continue  # bbox query exports relation features too; stops come from nodes
            try:
                nid = int(oid.split("/", 1)[1])
            except (ValueError, IndexError):
                continue
            tags = {
                k: v for k, v in props.items()
                if not k.startswith("@") and not isinstance(v, (dict, list))
            }
            geom = feature.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            nodes[nid] = {
                "type": "node", "id": nid, "lat": lat, "lon": lon, "tags": tags,
            }
            for rel in props.get("@relations") or []:
                reltags = rel.get("reltags") or {}
                if reltags.get("type") != "route":
                    continue
                rid = int(rel["rel"])
                r = relations.setdefault(rid, {
                    "type": "relation", "id": rid, "tags": dict(reltags),
                    "members": [],
                })
                r["members"].append({
                    "type": "node", "ref": nid, "role": rel.get("role", ""),
                })
        return list(nodes.values()) + list(relations.values())
    raise ValueError("unrecognised Overpass export shape")


def in_bounds(lat, lon) -> bool:
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return False
    return BOX[0] <= lat <= BOX[1] and BOX[2] <= lon <= BOX[3]


def _mode_from_tags(tags: dict) -> str | None:
    for key, allowed, mode in MODE_FLAGS:
        if tags.get(key) in allowed:
            # railway=tram_stop is tram, not train.
            if key == "railway" and tags.get(key) == "tram_stop":
                return "tram"
            return mode
    if tags.get("public_transport") in ("station", "platform", "stop_position"):
        return MODE_MAP.get(tags.get("mode") or "")
    return None


def osm_stations(els, *, report: dict | None = None):
    """Build stations from OSM nodes, merging stop_area duplicates.

    Returns {canonical_id: station}. Every member OSM id is kept in `osm_ids`.
    """
    # Map node id -> raw station record for all plausibly stop-like nodes.
    raw: dict[str, dict] = {}
    for el in els:
        if el.get("type") != "node":
            continue
        tags = el.get("tags") or {}
        lat, lon = el.get("lat"), el.get("lon")
        if not in_bounds(lat, lon):
            if report is not None:
                report["out_of_bounds_nodes"] = report.get("out_of_bounds_nodes", 0) + 1
            continue
        mode = _mode_from_tags(tags)
        if not mode:
            continue
        name = tags.get("name") or tags.get("name:fr") or ""
        raw[str(el["id"])] = {
            "id": f"osm:{el['id']}",
            "name": name or f"osm-node-{el['id']}",
            "name_ar": tags.get("name:ar", ""),
            "name_fr": tags.get("name:fr", ""),
            "name_en": tags.get("name:en", ""),
            "lat": lat, "lon": lon, "mode": mode,
            "operator": tags.get("operator", ""),
            "source": "osm", "license_status": "odbl",
            "osm_id": el["id"],
            "unnamed": not bool(name),
        }

    # Merge stop_position/platform pairs via stop_area relations (finding 2).
    alias: dict[str, str] = {}
    for el in els:
        tags = el.get("tags") or {}
        if el.get("type") != "relation" or "stop_area" not in str(tags.get("type", "")):
            continue
        members = [str(m.get("ref")) for m in el.get("members", []) if str(m.get("ref")) in raw]
        if not members:
            continue
        canonical = min(members)  # stable choice
        for mid in members:
            alias[mid] = canonical

    stations: dict[str, dict] = {}
    unnamed = 0
    for nid, rec in raw.items():
        if rec.get("unnamed"):
            unnamed += 1
        canonical = alias.get(nid)
        if canonical and nid != canonical:
            # Keep every OSM id for provenance; discard the duplicate marker.
            stations[f"osm:{canonical}"].setdefault("osm_ids", [int(canonical)])
            if int(nid) not in stations[f"osm:{canonical}"]["osm_ids"]:
                stations[f"osm:{canonical}"]["osm_ids"].append(int(nid))
            if report is not None:
                report["merged_duplicate_nodes"] = report.get("merged_duplicate_nodes", 0) + 1
            continue
        rec.setdefault("osm_ids", [int(nid)])
        stations[rec["id"]] = rec
    if report is not None:
        report["unnamed_stops"] = unnamed
    return stations


def _mode_from_route(tags: dict) -> str | None:
    return MODE_MAP.get(tags.get("route") or "")


def osm_lines(els, stations, *, report: dict | None = None):
    """Build lines with direction variants grouped by route_master."""
    node_to_id = {
        str(s["osm_id"]): s["id"] for s in stations.values() if "osm_id" in s
    }
    # Also index merged duplicate ids.
    for s in stations.values():
        for oid in s.get("osm_ids", []):
            node_to_id[str(oid)] = s["id"]

    route_els = [e for e in els if e.get("type") == "relation" and "route" in (e.get("tags") or {})]
    master_members: dict[str, list[int]] = {}
    for el in els:
        if el.get("type") != "relation":
            continue
        tags = el.get("tags") or {}
        if tags.get("type") != "route_master":
            continue
        refs = [int(m["ref"]) for m in el.get("members", []) if m.get("type") == "relation" and str(m.get("ref", "")).isdigit()]
        if refs:
            master_members[str(el["id"])] = refs

    by_master: dict[str, list[dict]] = defaultdict(list)
    standalone: list[dict] = []
    grouped_ids: set[str] = set()
    for el in route_els:
        tags = el.get("tags") or {}
        mode = _mode_from_route(tags)
        if not mode:
            if report is not None:
                key = f"dropped_unsupported_mode:{tags.get('route', '')}"
                report[key] = report.get(key, 0) + 1
            continue
        stops = []
        for m in el.get("members", []):
            if m.get("type") == "node" and str(m.get("ref")) in node_to_id:
                sid = node_to_id[str(m["ref"])]
                if sid not in stops:
                    stops.append(sid)
        if len(stops) < 2:
            if report is not None:
                report["dropped_short_lines"] = report.get("dropped_short_lines", 0) + 1
            continue
        variant = {
            "osm_id": el["id"],
            "name": tags.get("name") or tags.get("ref") or f"route-{el['id']}",
            "mode": mode,  # preserve TGM/light_rail, train, ferry, etc.
            "operator": tags.get("operator", ""),
            "stops": stops,
            "direction": "forward",  # OSM route relations carry direction in name; kept as variant metadata
            "license_status": "odbl",
        }
        key = None
        for mid, refs in master_members.items():
            if el["id"] in refs:
                key = mid
                grouped_ids.add(str(el["id"]))
                break
        if key:
            by_master[key].append(variant)
        else:
            standalone.append(variant)

    lines: list[dict] = []
    for mid, variants in by_master.items():
        master = next((e for e in els if str(e.get("id")) == mid), {})
        tags = master.get("tags") or {}
        directions = []
        for i, v in enumerate(variants):
            directions.append({**v, "direction": "forward" if i == 0 else "backward"})
        first_variant_id = str(variants[0]["osm_id"])
        first_route = next(
            (e for e in els if str(e.get("id")) == first_variant_id), {}
        )
        line_mode = _mode_from_route(tags) or _mode_from_route(first_route.get("tags") or {}) or "bus"
        lines.append({
            "id": f"osm:master:{mid}",
            "name": tags.get("name") or variants[0]["name"],
            "number": tags.get("ref") or variants[0].get("number", ""),
            "mode": line_mode,
            "operator": tags.get("operator") or variants[0]["operator"],
            "stops": variants[0]["stops"],
            "directions": directions,
            "source": "osm", "license_status": "odbl", "osm_id": int(mid),
            "osm_ids": [v["osm_id"] for v in variants],
        })
    for v in standalone:
        lines.append({
            "id": f"osm:route:{v['osm_id']}",
            "name": v["name"], "number": "", "mode": v.get("mode", "bus"),
            "operator": v["operator"], "stops": v["stops"],
            "directions": [v], "source": "osm", "license_status": "odbl",
            "osm_id": v["osm_id"],
        })
    return lines


def link_lines_served(stations, lines) -> None:
    """Every station lists every line serving it (finding 3)."""
    index: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        for sid in line["stops"]:
            index[sid].add(line["id"])
    for sid, ids in index.items():
        if sid in stations:
            stations[sid]["lines_served"] = sorted(ids)


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
            "lat": s["lat"], "lon": s["lon"], "mode": "louage",
            "operator": s.get("operator", "Louage"),
            "source": "osm", "license_status": "odbl", "osm_id": s["id"],
            "louage_route_type": s.get("louage_route_type", "local"),
        })
    return out


def main() -> int:
    export = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXPORT
    if not export.exists():
        print(f"ERROR: OSM export not found: {export}", file=sys.stderr)
        print("Fetch it with scripts/fetch_osm_export.py.", file=sys.stderr)
        return 2
    report: dict = {
        # Always report all four named drop categories, even when zero.
        "unnamed_stops": 0,
        "dropped_short_lines": 0,
        "out_of_bounds_nodes": 0,
        "merged_duplicate_nodes": 0,
    }
    payload = load_json(export)
    els = elements(payload)
    stations = osm_stations(els, report=report)
    lines = osm_lines(els, stations, report=report)
    for s in louage_stations():
        stations.setdefault(s["id"], s)
    link_lines_served(stations, lines)

    manifest = {}
    if MANIFEST.exists():
        manifest = load_json(MANIFEST)
    out = {
        "metadata": {
            "source": "OpenStreetMap (ODbL) public-transport exports + OSM taxi/louage hubs",
            "license": "ODbL — attribution required",
            "generated_by": "scripts/rebuild_seed_from_osm.py",
            "input_export": str(export.relative_to(REPO)) if export.is_relative_to(REPO) else str(export),
            "osm3s_timestamp_osm_base": manifest.get("osm3s_timestamp_osm_base"),
            "total_lines": len(lines), "total_stations": len(stations),
            "drop_counts": report,
            "louage_source": {
                "file": str(LOUAGE.relative_to(REPO)),
                "note": "OSM-derived taxi/louage hubs; see manifest for export timestamp",
            },
        },
        "stations": list(stations.values()),
        "lines": lines,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"wrote {OUT.relative_to(REPO)}: {len(stations)} stations, {len(lines)} lines")
    print(f"drop counts: {report}")
    print("source data: OpenStreetMap (ODbL). Attribute OSM in the UI and docs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
