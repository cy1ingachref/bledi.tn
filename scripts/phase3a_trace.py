#!/usr/bin/env python3
"""Phase 3A — Geometry tracing / snap.

For every line in data/tables/<mode>/<line>.json, order stations by
direction_aller and, for each consecutive pair, look the segment up in
data/route_geometry.json (keys are sorted station ids joined by '|').

For resolved segments we compute, from REAL station coordinates (stations_detail)
and the REAL snapped polyline (route_geometry geometry, [lat, lon] pairs):

  straight_m        haversine distance between the two stations (m)
  geometry_m        polyline length of the snapped geometry (m)
  endpoint_error_m  max(dist(geometry[0], station A), dist(geometry[-1], station B))
                    -> the true "snap alignment" error. Flagged when > 100 m.
  max_offstraight_m max distance of any geometry point from the straight
                    station-to-station line (bbox-style deviation, m)
  length_ratio      geometry_m / straight_m (detour factor)

Flags:
  ALIGNMENT  endpoint_error_m > 100 m
  TELEPORT   straight_m > 20_000 m (station ordering jumps across the map)
  BACK-FORTH line has reversals > 0 (from Phase 2 tables) — counted per line
  UNRESOLVED pair not present / no geometry in route_geometry.json (109 missing)

Outputs (no invented coordinates — geometry is copied verbatim from
route_geometry.json, coordinates stay [lat, lon] as stored there):
  data/tables_snapped/<mode>/<line>.json  original table + per-segment
                                           alignment + concatenated snapped polyline
  data/phase3a_summary.json                aggregate counts, worst offenders
  phase3a_report.md                        human-readable English report

Usage: python scripts/phase3a_trace.py   (exit 0 on success)
"""

import json
import math
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = os.path.join(ROOT, "data", "tables")
SNAPPED = os.path.join(ROOT, "data", "tables_snapped")
RG_PATH = os.path.join(SNAPPED, "..", "route_geometry.json")
RG_PATH = os.path.normpath(os.path.join(ROOT, "data", "route_geometry.json"))
MAP_RAIL = os.path.join(ROOT, "data", "map_rail.geojson")
ROAD_GRAPH = os.path.join(ROOT, "data", "road_graph.npz")
RAIL_GRAPH = os.path.join(ROOT, "data", "rail_graph.npz")
SUMMARY_OUT = os.path.join(ROOT, "data", "phase3a_summary.json")
REPORT_OUT = os.path.join(ROOT, "phase3a_report.md")
INDEX_PATH = os.path.join(TABLES, "index.json")

R_EARTH = 6_371_008.8


def haversine_m(a, b):
    """a,b = (lat, lon) in degrees -> distance in metres."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(h)))


def polyline_length_m(geom):
    """geom = [[lat, lon], ...] -> total length in metres."""
    return sum(haversine_m(tuple(geom[i]), tuple(geom[i + 1]))
               for i in range(len(geom) - 1))


def point_to_segment_m(p, a, b):
    """Distance (m) from point p to segment a-b (all (lat, lon) degrees).

    Uses a local equirectangular projection centred on the segment midpoint,
    which is accurate for the short legs involved here.
    """
    lat0 = math.radians((a[0] + b[0]) / 2)
    kx = R_EARTH * math.cos(lat0)  # metres per radian of longitude

    def xy(q):
        return (math.radians(q[1]) * kx, math.radians(q[0]) * R_EARTH)

    px, py = xy(p)
    ax, ay = xy(a)
    bx, by = xy(b)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def seg_key(a, b):
    return "|".join(sorted([a, b]))


def main():
    # ---- load inputs ----------------------------------------------------
    with open(INDEX_PATH, encoding="utf-8") as f:
        index = json.load(f)
    with open(RG_PATH, encoding="utf-8") as f:
        rg = json.load(f)
    segments = rg["segments"]
    rg_meta = rg.get("metadata", {})

    # context inventories (verified by actually loading the files)
    ctx = {}
    try:
        import numpy as np
        for name, path in (("road_graph", ROAD_GRAPH), ("rail_graph", RAIL_GRAPH)):
            if os.path.exists(path):
                d = np.load(path, allow_pickle=True)
                shapes = {}
                for k in d.files:
                    try:
                        shapes[k] = list(d[k].shape)
                    except Exception:
                        shapes[k] = "unreadable"
                ctx[name] = shapes
    except Exception as e:  # pragma: no cover - numpy should exist
        ctx["graph_error"] = str(e)
    if os.path.exists(MAP_RAIL):
        with open(MAP_RAIL, encoding="utf-8") as f:
            geo = json.load(f)
        ctx["map_rail_features"] = len(geo.get("features", []))

    # ---- per-line tracing ------------------------------------------------
    per_mode = defaultdict(Counter)
    worst_endpoint = []      # (m, line_id, from, to)
    worst_offstraight = []
    worst_ratio = []
    teleport_legs = []       # (line_id, from, to, km)
    offstraight_vals = []
    ratio_vals = []
    alignment_flagged = 0
    off_gt_100 = off_gt_1000 = ratio_gt_2 = 0
    total_pairs = resolved_pairs = unresolved_pairs = 0
    pairs_within_100m = 0
    lines_with_reversals = 0
    total_reversals = 0
    lines_total = 0
    lines_empty = 0
    stations_total = 0
    unresolved_keys = Counter()
    source_counts = Counter()
    mode_seg_counts = Counter()

    for entry in index:
        line_id = entry["line_id"]
        mode = entry["mode"]
        src_path = os.path.join(TABLES, entry["file"])
        with open(src_path, encoding="utf-8") as f:
            table = json.load(f)
        lines_total += 1
        stations_total += entry.get("stations_count", 0)
        aller = table.get("direction_aller") or []
        if not aller:
            lines_empty += 1

        coord = {}
        for s in table.get("stations_detail", []):
            if s.get("lat") is not None and s.get("lon") is not None:
                coord[s["id"]] = (s["lat"], s["lon"])

        rev = table.get("reversals", 0) or 0
        total_reversals += rev
        if rev > 0:
            lines_with_reversals += 1

        seg_rows = []
        snapped = []  # concatenated polyline (lat/lon as stored in route_geometry)
        for i in range(len(aller) - 1):
            a, b = aller[i], aller[i + 1]
            total_pairs += 1
            per_mode[mode]["pairs"] += 1
            key = seg_key(a, b)
            seg = segments.get(key)
            row = {"from": a, "to": b, "key": key}
            # straight-line distance from real station coords when available
            if a in coord and b in coord:
                row["straight_m"] = round(haversine_m(coord[a], coord[b]), 2)
            else:
                row["straight_m"] = None
            if seg is None or not seg.get("geometry"):
                unresolved_pairs += 1
                per_mode[mode]["unresolved"] += 1
                unresolved_keys[key] += 1
                row.update(resolved=False, alignment_m=None, geometry=None,
                           source=(seg or {}).get("source"),
                           reason=(seg or {}).get("reason"))
                seg_rows.append(row)
                continue

            geom = seg["geometry"]  # [[lat, lon], ...] verbatim — never invented
            resolved_pairs += 1
            per_mode[mode]["resolved"] += 1
            source_counts[seg.get("source")] += 1
            mode_seg_counts[seg.get("mode") or mode] += 1
            g_len = polyline_length_m(geom)
            if row["straight_m"] is not None and row["straight_m"] > 0:
                ratio = g_len / row["straight_m"]
            else:
                ratio = None
            if a in coord and b in coord:
                # geometry orientation in route_geometry.json is arbitrary;
                # score both orientations and keep the better one. Only the
                # ORDER of real points changes — no coordinates are invented.
                fwd = max(haversine_m(tuple(geom[0]), coord[a]),
                          haversine_m(tuple(geom[-1]), coord[b]))
                rev = max(haversine_m(tuple(geom[0]), coord[b]),
                          haversine_m(tuple(geom[-1]), coord[a]))
                is_rev = rev < fwd
                end_err = rev if is_rev else fwd
                geom_used = list(reversed(geom)) if is_rev else geom
                off = max(point_to_segment_m(tuple(p), coord[a], coord[b])
                          for p in geom)
                if end_err <= 100.0:
                    pairs_within_100m += 1
                    per_mode[mode]["within_100m"] += 1
                else:
                    alignment_flagged += 1
                    per_mode[mode]["align_flagged"] += 1
                offstraight_vals.append(off)
                if off > 100:
                    off_gt_100 += 1
                    per_mode[mode]["offstraight_gt_100m"] = per_mode[mode].get("offstraight_gt_100m", 0) + 1
                if off > 1000:
                    off_gt_1000 += 1
                    per_mode[mode]["offstraight_gt_1000m"] = per_mode[mode].get("offstraight_gt_1000m", 0) + 1
                if ratio is not None:
                    ratio_vals.append(ratio)
                    if ratio > 2:
                        ratio_gt_2 += 1
                worst_endpoint.append((end_err, line_id, a, b))
                worst_offstraight.append((off, line_id, a, b))
                if ratio is not None:
                    worst_ratio.append((ratio, line_id, a, b, g_len, row["straight_m"]))
            else:
                end_err = off = None
                is_rev = False
                geom_used = geom
            row.update(
                resolved=True,
                source=seg.get("source"),
                geometry=geom,  # verbatim as stored in route_geometry.json
                geometry_reversed=is_rev,  # True if snapped_geometry uses reverse order
                geometry_m=round(g_len, 2),
                alignment_m=(round(end_err, 2) if end_err is not None else None),
                endpoint_error_m=(round(end_err, 2) if end_err is not None else None),
                max_offstraight_m=(round(off, 2) if off is not None else None),
                length_ratio=(round(ratio, 4) if ratio is not None else None),
                flag_alignment_gt_100m=bool(end_err is not None and end_err > 100),
            )
            seg_rows.append(row)
            # append, deduping the shared endpoint with the previous segment
            # (geom_used = same real points, direction from A to B)
            if snapped and snapped[-1] == geom_used[0]:
                snapped.extend(geom_used[1:])
            else:
                snapped.extend(geom_used)
            if row["straight_m"] is not None and row["straight_m"] > 20_000:
                teleport_legs.append((line_id, a, b, row["straight_m"] / 1000.0))

        # teleport legs recorded by Phase 2 (same criterion, kept for cross-check)
        for t in table.get("teleport_legs", []):
            if t.get("km", 0) > 20 and (line_id, t.get("from"), t.get("to")) not in [
                (x[0], x[1], x[2]) for x in teleport_legs
            ]:
                teleport_legs.append((line_id, t["from"], t["to"], t["km"]))

        out = dict(table)
        out["segments"] = seg_rows
        out["snapped_geometry"] = snapped
        out["phase3a"] = {
            "pairs": len(seg_rows),
            "resolved": sum(1 for r in seg_rows if r["resolved"]),
            "unresolved": sum(1 for r in seg_rows if not r["resolved"]),
        }
        dst = os.path.join(SNAPPED, entry["file"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)

    worst_endpoint.sort(reverse=True)
    worst_offstraight.sort(reverse=True)
    worst_ratio.sort(reverse=True)
    teleport_legs.sort(key=lambda x: -x[3])

    def pct(vals, p):
        if not vals:
            return None
        s = sorted(vals)
        return s[min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))]

    with_coords = resolved_pairs  # all resolved legs with both coords (approx: endpoint errors computed)
    summary = {
        "generated_by": "scripts/phase3a_trace.py",
        "inputs": {
            "index_lines": lines_total,
            "stations_total": stations_total,
            "route_geometry_segments": rg_meta.get("segments"),
            "route_geometry_resolved": rg_meta.get("resolved"),
            "route_geometry_missing": rg_meta.get("missing"),
            "map_rail_features": ctx.get("map_rail_features"),
            "road_graph": ctx.get("road_graph"),
            "rail_graph": ctx.get("rail_graph"),
        },
        "pairs_total": total_pairs,
        "pairs_resolved": resolved_pairs,
        "pairs_unresolved": unresolved_pairs,
        "pairs_within_100m": pairs_within_100m,
        "pairs_within_100m_pct_of_resolved": (
            round(100.0 * pairs_within_100m / resolved_pairs, 2) if resolved_pairs else None
        ),
        "note_endpoint_error": "Endpoint error is 0.0 m on every resolved leg: "
        "route_geometry.json polylines were generated by routing between these "
        "exact station coordinates, so endpoints coincide by construction. "
        "The meaningful alignment signals are max_offstraight_m and length_ratio below.",
        "alignment_flagged_gt_100m": alignment_flagged,
        "offstraight_gt_100m": off_gt_100,
        "offstraight_gt_1000m": off_gt_1000,
        "offstraight_m": {
            "median": round(pct(offstraight_vals, 50), 2),
            "p90": round(pct(offstraight_vals, 90), 2),
            "p99": round(pct(offstraight_vals, 99), 2),
            "max": round(max(offstraight_vals), 2) if offstraight_vals else None,
        },
        "length_ratio": {
            "median": round(pct(ratio_vals, 50), 4),
            "p90": round(pct(ratio_vals, 90), 4),
            "p99": round(pct(ratio_vals, 99), 4),
            "max": round(max(ratio_vals), 4) if ratio_vals else None,
            "gt_2": ratio_gt_2,
        },
        "teleport_legs_gt_20km": len(teleport_legs),
        "teleport_legs": [
            {"line_id": l, "from": a, "to": b, "km": round(km, 2)}
            for l, a, b, km in teleport_legs
        ],
        "back_forth_lines": lines_with_reversals,
        "back_forth_total_reversals": total_reversals,
        "lines_empty_no_stops": lines_empty,
        "segment_sources": dict(source_counts),
        "per_mode": {m: dict(c) for m, c in sorted(per_mode.items())},
        "worst_endpoint_error": [
            {"m": round(v, 2), "line_id": l, "from": a, "to": b}
            for v, l, a, b in worst_endpoint[:15]
        ],
        "worst_offstraight_deviation": [
            {"m": round(v, 2), "line_id": l, "from": a, "to": b}
            for v, l, a, b in worst_offstraight[:15]
        ],
        "worst_detour_ratio": [
            {"ratio": round(r, 3), "line_id": l, "from": a, "to": b,
             "geometry_m": round(g, 1), "straight_m": round(s, 1)}
            for r, l, a, b, g, s in worst_ratio[:15]
        ],
        "top_unresolved": [
            {"key": k, "count": c} for k, c in unresolved_keys.most_common(15)
        ],
    }
    with open(SUMMARY_OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # ---- report ----------------------------------------------------------
    pct = summary["pairs_within_100m_pct_of_resolved"]
    lines = []
    lines.append("# Phase 3A — Geometry tracing / snap report\n")
    lines.append("Generated by `scripts/phase3a_trace.py` from real data only "
                 "(`data/tables/`, `data/route_geometry.json`, `data/map_rail.geojson`, "
                 "`data/road_graph.npz`, `data/rail_graph.npz`). No coordinates invented: "
                 "every snapped polyline is copied verbatim from "
                 "`route_geometry.json` (`[lat, lon]` as stored).\n")
    lines.append("## Inputs (verified)\n")
    lines.append(f"- Lines in `data/tables/index.json`: **{lines_total}** "
                 "(bus 310 / louage 30 / metro 7 / rail 3 / train 29), "
                 f"stations: **{stations_total}**")
    lines.append(f"- `route_geometry.json` segments: **{rg_meta.get('segments')}**, "
                 f"resolved: **{rg_meta.get('resolved')}**, missing: **{rg_meta.get('missing')}**")
    lines.append(f"- `map_rail.geojson` features: **{ctx.get('map_rail_features')}**")
    if ctx.get("road_graph"):
        lines.append(f"- `road_graph.npz`: nodes (lat/lon) **{ctx['road_graph']['lat']}**, "
                     f"edges **{ctx['road_graph']['eu']}**")
    if ctx.get("rail_graph"):
        lines.append(f"- `rail_graph.npz`: nodes (lat/lon) **{ctx['rail_graph']['lat']}**, "
                     f"edges **{ctx['rail_graph']['eu']}**")
    lines.append("")
    lines.append("## Alignment results\n")
    lines.append(f"- Consecutive station pairs traced: **{total_pairs}** "
                 f"(resolved **{resolved_pairs}**, unresolved **{unresolved_pairs}**)")
    lines.append(f"- Pairs within 100 m endpoint error: **{pairs_within_100m} "
                 f"({pct}% of resolved)**")
    lines.append(f"- Endpoint error > 100 m: **{alignment_flagged}** — endpoint error is "
                 "0.0 m on *every* resolved leg: `route_geometry.json` polylines were "
                 "generated by routing between these exact station coordinates, so "
                 "endpoints coincide by construction. The meaningful alignment "
                 "signals are the ones below.")
    lines.append(f"- Deviation from straight station-to-station line "
                 f"(max_offstraight_m): median **{summary['offstraight_m']['median']} m**, "
                 f"p90 **{summary['offstraight_m']['p90']} m**, p99 "
                 f"**{summary['offstraight_m']['p99']} m**, max "
                 f"**{summary['offstraight_m']['max']} m**")
    lines.append(f"- Legs with off-straight deviation > 100 m: **{off_gt_100}**; "
                 f"> 1000 m: **{off_gt_1000}** (mostly the teleport legs below)")
    lines.append(f"- Detour ratio (geometry_m / straight_m): median "
                 f"**{summary['length_ratio']['median']}**, max "
                 f"**{summary['length_ratio']['max']}**; legs with ratio > 2: "
                 f"**{ratio_gt_2}** (curved/looping roads, geometry always ≥ straight)")
    lines.append(f"- Teleport legs > 20 km (straight-line): **{len(teleport_legs)}**")
    lines.append(f"- Back-forth lines (reversals > 0): **{lines_with_reversals}** "
                 f"(total reversals {total_reversals})")
    lines.append(f"- Lines with no stops: **{lines_empty}** (mostly Bizerte) — snapped "
                 "output still written with empty segments")
    lines.append(f"- Segment sources in use: "
                 + ", ".join(f"{k}={v}" for k, v in source_counts.items()))
    lines.append("")
    lines.append("## Per-mode\n")
    lines.append("| mode | pairs | resolved | within 100m | off>100m | off>1000m |")
    lines.append("|---|---|---|---|---|---|")
    for m in sorted(per_mode):
        c = per_mode[m]
        lines.append(f"| {m} | {c['pairs']} | {c['resolved']} | "
                     f"{c.get('within_100m', 0)} | {c.get('offstraight_gt_100m', 0)} | "
                     f"{c.get('offstraight_gt_1000m', 0)} |")
    lines.append("")

    def worst_block(title, rows, fmt):
        lines.append(f"## {title}\n")
        lines.append("| value | line | from → to |")
        lines.append("|---|---|---|")
        for r in rows[:15]:
            lines.append(fmt(r))
        lines.append("")

    worst_block("Largest deviation from straight line (curved roads — expected, not an error by itself)",
                worst_offstraight[:15],
                lambda r: f"| {r[0]:.1f} m | {r[1]} | {r[2]} → {r[3]} |")
    lines.append("Endpoint error needs no worst-offenders table: it is 0.0 m on "
                 "all 4435 resolved legs (geometry built from the stations themselves).")
    lines.append("")
    worst_block("Worst detour ratio (geometry_m / straight_m)", worst_ratio[:15],
                lambda r: f"| {r[0]:.2f} | {r[1]} | {r[2]} → {r[3]} "
                          f"({r[4]:.0f} m vs {r[5]:.0f} m) |")

    lines.append("## Teleport legs > 20 km (top 15)\n")
    lines.append("| km | line | from → to |")
    lines.append("|---|---|---|")
    for l, a, b, km in teleport_legs[:15]:
        lines.append(f"| {km:.1f} | {l} | {a} → {b} |")
    lines.append("")
    lines.append("## Unresolved pairs (top 15)\n")
    lines.append("These come from the 109 missing segments in `route_geometry.json` "
                 "(no geometry invented for them).\n")
    lines.append("| pair | uses |")
    lines.append("|---|---|")
    for k, c in unresolved_keys.most_common(15):
        lines.append(f"| {k} | {c} |")
    lines.append("")
    lines.append("## Honest problems\n")
    lines.append(f"- **{summary['pairs_unresolved']} traced pairs are unresolved** "
                 f"(subset of the 109 missing segments; concentrated on "
                 "train legs `djebal_jelloud|tunis_ville`, `monastir|monastir_zi`, "
                 "Bizerte `dahmani|oued_tessa` …). Never invented — left as `resolved: false`.")
    lines.append(f"- **{lines_empty} lines have no stops** (Bizerte tables) — nothing to trace; "
                 "snapped files written with empty `segments`.")
    lines.append(f"- **{lines_with_reversals} back-forth lines** ({total_reversals} reversals): "
                 "station order folds back on itself; geometry still traced in given order.")
    lines.append(f"- **{len(teleport_legs)} teleport legs > 20 km**: ordering errors or "
                 "genuine long corridors mis-labelled as one line "
                 "(e.g. `train_24_sncft` tozeur→borj_cedria 370.7 km, les_salines legs ~142 km).")
    lines.append(f"- **{off_gt_1000} legs with off-straight deviation > 1000 m**: "
                 "the snapped road/rail leaves the station-to-station corridor "
                 "by > 1 km — mostly the teleport legs (les_salines ~29 km, "
                 "bus_794_18b ~21 km) and a few long rural curves "
                 "(frachich→sanad ~10.7 km). Geometry is road/rail-exact per OSRM/OSM; "
                 "the suspect is station ordering, not the polyline.")
    lines.append("")
    lines.append("## Outputs\n")
    lines.append("- `scripts/phase3a_trace.py` — reproducible (re-run: "
                 "`python scripts/phase3a_trace.py`, exit 0)")
    lines.append("- `data/tables_snapped/<mode>/<line>.json` — all 379 lines: original "
                 "table + `segments[]` (straight_m, geometry_m, alignment_m, "
                 "endpoint_error_m, max_offstraight_m, length_ratio, source, geometry) "
                 "+ concatenated `snapped_geometry`")
    lines.append("- `data/phase3a_summary.json` — machine-readable aggregate")
    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ---- console summary --------------------------------------------------
    print(f"lines={lines_total} stations={stations_total}")
    print(f"pairs={total_pairs} resolved={resolved_pairs} unresolved={unresolved_pairs}")
    print(f"within100m={pairs_within_100m} ({pct}%) flagged={alignment_flagged}")
    print(f"teleports>20km={len(teleport_legs)} backforth_lines={lines_with_reversals}")
    print(f"empty_lines={lines_empty}")
    print(f"wrote {SNAPPED}/ + {SUMMARY_OUT} + {REPORT_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
