#!/usr/bin/env python3
"""Diff route-relation ids between a bbox GeoJSON and the Tunisia export.

Read-only: matches on OSM relation id. The GeoJSON id looks like
"relation/1714965"; Overpass JSON relations use a plain integer id. The
export's route memberships are read from each stop's @relations list.

Writes a small JSON summary and a Markdown report. Does not modify either
input and does not make any data/cutover decision.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Same padded Tunisia box as scripts/verify_open_seed.py.
BOX = (30.23, 37.56, 7.50, 11.65)  # min_lat, max_lat, min_lon, max_lon
DEFAULT_BBOX = Path.home() / "Downloads" / "67.geojson"
DEFAULT_EXPORT = REPO / "data" / "osm_overpass" / "tunisia_pt.json"
DEFAULT_OUT_JSON = REPO / "docs" / "reports" / "osm-bbox-route-diff.json"
DEFAULT_OUT_MD = REPO / "docs" / "reports" / "osm-bbox-route-diff.md"


def _rel_id(value) -> int | None:
    text = str(value or "")
    if text.startswith("relation/"):
        text = text.split("/", 1)[1]
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def in_box(lat, lon) -> bool:
    return (isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            and BOX[0] <= lat <= BOX[1] and BOX[2] <= lon <= BOX[3])


def _load_geojson_routes(path: Path) -> dict[int, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    routes: dict[int, dict] = {}
    for f in data.get("features", []):
        props = f.get("properties") or {}
        rid = _rel_id(props.get("@id"))
        if rid is None or (props.get("type") or "") != "route":
            continue
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates") or []
        lat = lon = None
        if geom.get("type") == "Point" and len(coords) >= 2:
            lon, lat = float(coords[0]), float(coords[1])
        elif isinstance(coords, list) and coords and isinstance(coords[0], list):
            # Polygon/MultiLine centre fallback: average the first ring's points.
            pts = [c for c in coords[0] if isinstance(c, list) and len(c) >= 2]
            if pts:
                lon = sum(float(c[0]) for c in pts) / len(pts)
                lat = sum(float(c[1]) for c in pts) / len(pts)
        routes[rid] = {
            "id": rid,
            "name": props.get("name", ""),
            "name_fr": props.get("name:fr", ""),
            "ref": props.get("ref", ""),
            "operator": props.get("operator", ""),
            "route": props.get("route", ""),
            "center_lat": lat, "center_lon": lon,
            "center_in_tunisia_box": in_box(lat, lon),
        }
    return routes


def _load_export_routes(path: Path) -> dict[int, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    routes: dict[int, dict] = {}
    if isinstance(data, dict) and "elements" in data:
        for el in data["elements"]:
            if el.get("type") == "relation" and "route" in (el.get("tags") or {}):
                routes[int(el["id"])] = {"id": int(el["id"]),
                                         "route": (el.get("tags") or {}).get("route", "")}
    elif isinstance(data, dict) and isinstance(data.get("features"), list):
        # GeoJSON export: route ids live in each stop's @relations.
        for f in data["features"]:
            for rel in (f.get("properties") or {}).get("@relations") or []:
                tags = rel.get("reltags") or {}
                if tags.get("type") == "route":
                    rid = _rel_id(rel.get("rel"))
                    if rid is not None:
                        routes.setdefault(rid, {"id": rid, "route": tags.get("route", "")})
    return routes


def build_report(bbox_path: Path, export_path: Path) -> dict:
    bbox = _load_geojson_routes(bbox_path)
    exported = _load_export_routes(export_path)
    both = sorted(set(bbox) & set(exported))
    only_bbox = sorted(set(bbox) - set(exported))
    only_export = sorted(set(exported) - set(bbox))
    in_tn = [rid for rid in only_bbox if bbox[rid]["center_in_tunisia_box"]]
    return {
        "inputs": {
            "bbox_file": str(bbox_path) if not bbox_path.is_relative_to(Path.home()) else "<Downloads>/" + bbox_path.name,
            "export_file": str(export_path.relative_to(REPO)) if export_path.is_relative_to(REPO) else str(export_path),
            "tunisia_box": list(BOX),
        },
        "counts": {
            "bbox_relations": len(bbox), "export_relations": len(exported),
            "in_both": len(both), "only_in_bbox": len(only_bbox),
            "only_in_export": len(only_export),
            "only_in_bbox_inside_tunisia_box": len(in_tn),
            "only_in_bbox_outside_tunisia_box": len(only_bbox) - len(in_tn),
        },
        "by_route_type": {
            "bbox": dict(Counter(r["route"] for r in bbox.values())),
            "export": dict(Counter(r.get("route", "") for r in exported.values())),
            "only_in_bbox": dict(Counter(bbox[rid]["route"] for rid in only_bbox)),
            "only_in_bbox_inside_tunisia": dict(Counter(
                bbox[rid]["route"] for rid in only_bbox
                if bbox[rid]["center_in_tunisia_box"])),
        },
        "ids_in_both": [bbox[rid] for rid in both],
        "ids_only_in_bbox": [bbox[rid] for rid in only_bbox],
        "ids_only_in_export": [exported[rid] for rid in only_export],
    }


def _md(report: dict) -> str:
    c = report["counts"]
    lines = [
        "# OSM bbox vs export route-relation diff",
        "",
        "Read-only comparison of two OSM route-relation sources. No data was changed.",
        "",
        f"- bbox file: `{report['inputs']['bbox_file']}`",
        f"- export: `{report['inputs']['export_file']}`",
        f"- Tunisia box (same as `verify_open_seed.py`): {BOX}",
        "",
        "## Counts",
        "",
        f"- Relations in bbox file: **{c['bbox_relations']}**",
        f"- Relations in export: **{c['export_relations']}**",
        f"- In both: **{c['in_both']}**",
        f"- Only in bbox file: **{c['only_in_bbox']}**",
        f"  - centre inside Tunisia box: {c['only_in_bbox_inside_tunisia_box']}",
        f"  - centre outside Tunisia box: {c['only_in_bbox_outside_tunisia_box']}",
        f"- Only in export: **{c['only_in_export']}**",
        "",
        "## Counts by route type",
        "",
    ]
    for key, val in report["by_route_type"].items():
        lines.append(f"- {key}: {dict(sorted(val.items()))}")
    lines += ["", "## Ids in both", ""]
    for r in report["ids_in_both"]:
        lines.append(f"- {r['id']} — {r['name'] or '(unnamed)'} ({r['route']})")
    lines += ["", "## Ids only in bbox file", ""]
    lines += ["| id | name | name:fr | ref | operator | route | centre lat/lon | in TN box |",
              "|---|---|---|---|---|---|---|---|"]
    for r in report["ids_only_in_bbox"]:
        centre = f"{r['center_lat']}, {r['center_lon']}" if r["center_lat"] is not None else "?"
        lines.append(
            f"| {r['id']} | {r['name']} | {r['name_fr']} | {r['ref']} | {r['operator']} "
            f"| {r['route']} | {centre} | {'yes' if r['center_in_tunisia_box'] else 'NO'} |")
    lines += ["", "## Ids only in export", ""]
    for r in report["ids_only_in_export"]:
        lines.append(f"- {r['id']} ({r.get('route', '')})")
    lines += [
        "",
        "## Interpretation (owner decision)",
        "",
        "If **many Tunisian relations appear only in the bbox file**, the area-based "
        "query is losing relations and the query should change — that is the owner's "
        "decision, not this report's. If the bbox-only relations are **mostly outside "
        "Tunisia**, the current export's 35 relation count stands.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", type=Path, default=DEFAULT_BBOX)
    ap.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = ap.parse_args()
    if not args.bbox.is_file() or not args.export.is_file():
        print(f"ERROR: missing input: bbox={args.bbox} export={args.export}")
        return 2
    report = build_report(args.bbox, args.export)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out_md.write_text(_md(report), encoding="utf-8")
    c = report["counts"]
    print(f"wrote {args.out_json} and {args.out_md}")
    print(f"bbox={c['bbox_relations']} export={c['export_relations']} both={c['in_both']} "
          f"only_bbox={c['only_in_bbox']} only_export={c['only_in_export']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
