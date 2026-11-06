#!/usr/bin/env python
"""Phase 2: ordered stop tables per line (aller/retour, single-direction).

Reads data/seed_all_tunisia_routes.tagged.json (379 lines, stations in order),
data/phase1_names.json (trilingual, provenance-tagged), data/station_reference.json
(proximity mode resolution), data/station_name_mapping.json, data/phase1_audit.json
(water-flagged 14), data/phase1_missing_coords.csv (131 BizerteConnect lines),
data/bizerteconnect_geocoded.json (9 cached places).

Writes:
  data/tables/<mode>/<line_id>.json  per line (original order preserved)
  data/tables/index.json             summary index of all tables
  data/phase2_summary.json           computed counts (valid JSON)
  data/bizerte_endpoints.json        endpoint geocoding results / blocked note
  data/water_corrections.json        confirmed-sea corrections w/ backups (no seed overwrite)

Network (Overpass water verify + Nominatim Bizerte endpoints) is attempted with
a proper User-Agent, 1.1s Nominatim spacing, and short timeouts. Set
PHASE2_OFFLINE=1 to skip all network calls (marks items needs_osm_verify / blocked).
No invented names/coords: unknown stays unknown, unconfirmed water stays uncorrected.
Python 3.11, stdlib only. Run: python scripts/phase2_build_tables.py
"""
import csv
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TABLES = DATA / "tables"
OFFLINE = os.environ.get("PHASE2_OFFLINE", "") == "1"
UA = {"User-Agent": "bledi.tn-phase2/1.0 (research; contact via repo)"}
R_EARTH_M = 6371000.0


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH_M * math.asin(min(1.0, math.sqrt(a)))


def load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def dedup(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def path_length_m(coords):
    return sum(haversine_m(*coords[i], *coords[i + 1]) for i in range(len(coords) - 1))


def count_reversals(coords):
    """Count sharp back-forth turns: cos(angle between consecutive legs) < -0.8
    with both legs > 200 m. 0 = clean single-direction progression."""
    rev = 0
    for i in range(1, len(coords) - 1):
        a, b, c = coords[i - 1], coords[i], coords[i + 1]
        d1 = haversine_m(*a, *b)
        d2 = haversine_m(*b, *c)
        if d1 < 200 or d2 < 200:
            continue
        # vectors in local ENU approximation
        def vec(p, q):
            return ((q[1] - p[1]) * 111320 * math.cos(math.radians(p[0])),
                    (q[0] - p[0]) * 110540)
        v1, v2 = vec(a, b), vec(b, c)
        n1 = math.hypot(*v1) or 1.0
        n2 = math.hypot(*v2) or 1.0
        if (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2) < -0.8:
            rev += 1
    return rev


def greedy_reorder(station_ids, coords_by_id):
    """Nearest-neighbour reorder keeping first station fixed (origin preserved).
    Returns (reordered_ids, new_length_m). Only used as a *separate* corrected
    candidate; original order is never destroyed."""
    remaining = [s for s in station_ids if s != station_ids[0]]
    order = [station_ids[0]]
    cur = coords_by_id.get(station_ids[0])
    while remaining:
        if cur is None:
            order.extend(remaining)
            break
        nxt = min(remaining, key=lambda s: haversine_m(*cur, *coords_by_id[s])
                  if coords_by_id.get(s) else float("inf"))
        order.append(nxt)
        remaining.remove(nxt)
        cur = coords_by_id.get(nxt)
    return order, path_length_m([coords_by_id[s] for s in order if coords_by_id.get(s)])


def main():
    seed = load("seed_all_tunisia_routes.tagged.json")
    stations_list = seed["stations"]
    stations = {s["id"]: s for s in stations_list}
    lines = seed["lines"]
    names_doc = load("phase1_names.json")
    names = {m["id"]: m for m in names_doc.get("mappings", [])}
    ref = load("station_reference.json")["stations"]
    name_map = load("station_name_mapping.json").get("stations", {})
    audit = load("phase1_audit.json")
    water_sample = audit["geolocation"]["transport_map_corrected"]["in_water_sample"]

    # --- spatial grid over reference stations that DO have a mode (150 m tol) ---
    ref_with_mode = [s for s in ref if s.get("mode") and s.get("mode") != "unknown"
                     and s.get("lat") is not None and s.get("lon") is not None]
    cell = 0.002  # ~200 m in degrees lat
    grid = defaultdict(list)
    for s in ref_with_mode:
        grid[(int(s["lat"] / cell), int(s["lon"] / cell))].append(s)

    def nearest_ref_mode(lat, lon, tol_m=150.0):
        best, best_d = None, tol_m
        ci, cj = int(lat / cell), int(lon / cell)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for s in grid.get((ci + di, cj + dj), []):
                    d = haversine_m(lat, lon, s["lat"], s["lon"])
                    if d < best_d:
                        best, best_d = s, d
        return (best["mode"], best_d) if best else (None, None)

    def norm(name):
        return "".join(ch for ch in (name or "").lower() if ch.isalnum())

    # lines serving each station (for cross-check; most unknowns serve none)
    line_modes = defaultdict(set)
    for l in lines:
        for sid in l["stations"]:
            line_modes[sid].add(l["mode"])

    # --- unknown-mode resolution (seed unknowns; transport_map has 77, seed 76) ---
    unknown_resolution = {}
    unk_modes = Counter(s.get("mode") for s in stations_list)
    for s in stations_list:
        if s.get("mode") != "unknown":
            continue
        sid = s["id"]
        resolved, method, dist = None, None, None
        modes = {m for m in line_modes.get(sid, set()) if m != "unknown"}
        if len(modes) == 1:
            resolved, method = modes.pop(), "single_line_mode"
        if resolved is None and s.get("lat") is not None and s.get("lon") is not None:
            resolved, dist = nearest_ref_mode(s["lat"], s["lon"])
            if resolved:
                method = f"station_reference_proximity_{dist:.0f}m"
        if resolved is None:
            # name-mapping fallback: exact normalized-name hit whose mapping
            # entry co-locates within 150 m of a known-mode reference station
            key = norm(s.get("name"))
            entry = name_map.get(key)
            if entry and s.get("lat") is not None:
                dmap = haversine_m(s["lat"], s["lon"], entry["lat"], entry["lon"])
                if dmap <= 150.0:
                    m2, d2 = nearest_ref_mode(entry["lat"], entry["lon"])
                    if m2:
                        resolved, method, dist = m2, "name_mapping_proximity", d2
        unknown_resolution[sid] = {"resolved_mode": resolved, "method": method,
                                    "distance_m": dist,
                                    "name": s.get("name")}
    unk_resolved = {k: v for k, v in unknown_resolution.items() if v["resolved_mode"]}
    unk_left = {k: v for k, v in unknown_resolution.items() if not v["resolved_mode"]}

    def station_mode(sid):
        s = stations.get(sid, {})
        if s.get("mode") and s["mode"] != "unknown":
            return s["mode"]
        r = unknown_resolution.get(sid, {})
        return r.get("resolved_mode") or s.get("mode", "unknown")

    # --- build per-line tables ---
    TABLES.mkdir(parents=True, exist_ok=True)
    per_mode = Counter()
    loop_lines, dup_lines, backforth_lines, corrected_lines = [], [], [], []
    total_dup_removed = 0
    total_stations_ordered = 0
    tables_written = 0
    index = []

    for l in lines:
        lid = l["id"]
        mode = l.get("mode", "unknown")
        original = list(l.get("stations", []))
        deduped = dedup(original)
        dups_removed = len(original) - len(deduped)
        coords = {sid: (stations[sid]["lat"], stations[sid]["lon"])
                  for sid in deduped
                  if stations.get(sid, {}).get("lat") is not None
                  and stations.get(sid, {}).get("lon") is not None}
        ordered_coords = [coords[s] for s in deduped if s in coords]
        reversals = count_reversals(ordered_coords) if len(ordered_coords) >= 3 else 0
        has_loop = dups_removed > 0 or (len(deduped) >= 2 and deduped[0] == deduped[-1])
        is_single = reversals == 0
        if has_loop:
            loop_lines.append(lid)
        if dups_removed:
            dup_lines.append({"line_id": lid, "duplicates_removed": dups_removed})
            total_dup_removed += dups_removed
        if not is_single:
            backforth_lines.append({"line_id": lid, "reversals": reversals})
        total_stations_ordered += len(deduped)

        corrected = None
        # Teleport legs (>20 km between consecutive stops) indicate a shared-id
        # coord error or a return-terminus appended at the end, NOT necessarily
        # an unordered list. Record them as anomalies.
        teleport_legs = []
        pairs = [(sid, coords[sid]) for sid in deduped if sid in coords]
        for i in range(len(pairs) - 1):
            dleg = haversine_m(*pairs[i][1], *pairs[i + 1][1])
            if dleg > 20000:
                teleport_legs.append({"from": pairs[i][0], "to": pairs[i + 1][0],
                                      "km": round(dleg / 1000, 1)})
        if not is_single and len(ordered_coords) >= 3:
            cand, cand_len = greedy_reorder(deduped, coords)
            orig_len = path_length_m(ordered_coords)
            cand_coords = [coords[s] for s in cand if s in coords]
            cand_rev = count_reversals(cand_coords)
            # Strict gate: greedy NN is only offered as a corrected candidate when
            # it removes ALL reversals AND halves the path length. This avoids
            # scrambling legitimate out-and-back / loop routes whose sharp turns
            # are real street geometry, and train lines whose reversal comes from
            # a single wrong-coord shared station (see teleport_legs).
            if cand_rev == 0 and cand_len < orig_len * 0.5:
                corrected = {"direction_aller_corrected": cand,
                             "direction_retour_corrected": list(reversed(cand)),
                             "original_path_m": round(orig_len, 1),
                             "corrected_path_m": round(cand_len, 1),
                             "original_reversals": reversals,
                             "corrected_reversals": cand_rev,
                             "note": "greedy nearest-neighbour from origin; original preserved"}
                corrected_lines.append(lid)

        detail = []
        for sid in deduped:
            st = stations.get(sid, {})
            nm = names.get(sid, {})
            detail.append({"id": sid, "name_en": st.get("name") or nm.get("name_en"),
                           "name_ar": nm.get("name_ar"), "name_fr": nm.get("name_fr"),
                           "name_ar_fr_source": nm.get("source"),
                           "lat": st.get("lat"), "lon": st.get("lon"),
                           "mode": station_mode(sid),
                           "mode_resolution": unknown_resolution.get(sid, {}).get("method")})
        start_id = deduped[0] if deduped else None
        end_id = deduped[-1] if deduped else None
        table = {
            "line_id": lid,
            "number": l.get("number"),
            "mode": mode,
            "operator": l.get("operator"),
            "name": l.get("name"),
            "direction_aller": deduped,
            "direction_retour": list(reversed(deduped)),
            "stations_count": len(deduped),
            "start": {"id": start_id, "name": stations.get(start_id, {}).get("name")} if start_id else None,
            "end": {"id": end_id, "name": stations.get(end_id, {}).get("name")} if end_id else None,
            "has_loop": has_loop,
            "duplicates_removed": dups_removed,
            "is_single_direction": is_single,
            "reversals": reversals,
            "teleport_legs": teleport_legs,
            "original_stations": original,
            "stations_detail": detail,
            "corrected_order": corrected,
            "source": l.get("source"),
        }
        out_dir = TABLES / mode
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in lid)
        with open(out_dir / f"{safe}.json", "w", encoding="utf-8") as f:
            json.dump(table, f, ensure_ascii=False, indent=1)
        tables_written += 1
        per_mode[mode] += 1
        index.append({"line_id": lid, "mode": mode, "file": f"{mode}/{safe}.json",
                      "stations_count": len(deduped), "has_loop": has_loop,
                      "is_single_direction": is_single})

    with open(TABLES / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)

    # --- water verification via Overpass is_in (attempt; else needs_osm_verify) ---
    water_results, water_network = [], "not_attempted"
    corrections = []
    if OFFLINE:
        water_network = "offline_flag"
        for w in water_sample:
            water_results.append({**w, "status": "needs_osm_verify", "reason": "PHASE2_OFFLINE=1"})
    else:
        water_network = "attempted"
        for w in water_sample:
            rec = {**w, "status": "needs_osm_verify"}
            try:
                q = (f"[out:json];is_in({w['lat']},{w['lon']});out tags;")
                raw = http_get("https://overpass-api.de/api/interpreter?data=" +
                               urllib.parse.quote(q), timeout=25)
                els = json.loads(raw).get("elements", [])
                areas = [e.get("tags", {}) for e in els]
                rec["overpass_is_in"] = areas
                water_names = [t.get("name", "") for t in areas]
                natural_water = any(t.get("natural") in ("water", "bay", "coastline")
                                    or t.get("waterway") for t in areas)
                land_use = any(t.get("landuse") or t.get("boundary") == "administrative"
                               or t.get("place") in ("suburb", "village", "town", "city",
                                                     "neighbourhood", "quarter")
                               for t in areas)
                if natural_water and not land_use:
                    rec["status"] = "confirmed_sea"
                    corrections.append({"station_id": w["id"], "name": w["name"],
                                        "backup_lat": w["lat"], "backup_lon": w["lon"],
                                        "status": "confirmed_sea_needs_relocation",
                                        "note": "coords NOT overwritten in seed; relocate via OSM/OsmAnd in Phase 3",
                                        "overpass_is_in": areas})
                elif land_use:
                    rec["status"] = "confirmed_land"
                else:
                    rec["status"] = "inconclusive_needs_osm_verify"
            except Exception as e:  # timeout / 406 / blocked
                rec["reason"] = f"overpass_failed: {type(e).__name__}: {e}"
            water_results.append(rec)
            time.sleep(0.5)
    with open(DATA / "water_corrections.json", "w", encoding="utf-8") as f:
        json.dump({"generated_by": "scripts/phase2_build_tables.py",
                   "network": water_network, "corrections": corrections,
                   "results": water_results}, f, ensure_ascii=False, indent=1)

    # --- BizerteConnect endpoint geocoding (Nominatim, 1.1 s spacing, cached) ---
    missing_rows = list(csv.DictReader(open(DATA / "phase1_missing_coords.csv", encoding="utf-8")))
    bc_rows = [r for r in missing_rows if r["status"] == "line_no_stops_no_coords"]
    cached = {}
    cache_path = DATA / "bizerteconnect_geocoded.json"
    if cache_path.exists():
        try:
            cached = load("bizerteconnect_geocoded.json")
        except Exception:
            cached = {}
    # seed bc lines carry origin/destination
    seed_bc = {l["id"]: l for l in lines if l.get("source") == "bizerteconnect-api"}
    endpoints = {"generated_by": "scripts/phase2_build_tables.py", "network": None,
                 "note": "cached bizerteconnect_geocoded.json reused first; Nominatim 1.1s spacing",
                 "cached_places": cached, "lines": []}
    geocoded_ok, geocoded_fail, blocked = 0, 0, False
    seen_names = {}
    if OFFLINE:
        endpoints["network"] = "offline_flag"
        blocked = True
    else:
        endpoints["network"] = "nominatim_attempted"
        for r in bc_rows:
            # match csv row to seed bc line by external_id/name fragment
            line = None
            for l in seed_bc.values():
                if l.get("external_id") and l["external_id"] in r["station_id"]:
                    line = l
                    break
            if line is None:
                # fallback: match by destination token in csv name
                endpoints["lines"].append({"csv_id": r["station_id"], "name": r["name"],
                                           "status": "no_seed_line_match"})
                blocked = blocked or False
                continue
            entry = {"line_id": line["id"], "name": line.get("name"),
                     "origin": line.get("origin"), "destination": line.get("destination"),
                     "origin_ar": line.get("origin_ar"), "destination_ar": line.get("destination_ar")}
            for role in ("origin", "destination"):
                pname = line.get(role)
                if not pname:
                    entry[f"{role}_coords"] = None
                    continue
                if pname in seen_names:
                    entry[f"{role}_coords"] = seen_names[pname]
                    continue
                q = urllib.parse.quote(f"{pname}, Tunisia")
                try:
                    raw = http_get(f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1",
                                   timeout=15)
                    hits = json.loads(raw)
                    if hits:
                        entry[f"{role}_coords"] = [float(hits[0]["lat"]), float(hits[0]["lon"])]
                        entry[f"{role}_source"] = "nominatim"
                        geocoded_ok += 1
                    else:
                        entry[f"{role}_coords"] = None
                        entry[f"{role}_source"] = "nominatim_no_hit"
                        geocoded_fail += 1
                except Exception as e:
                    entry[f"{role}_coords"] = None
                    entry[f"{role}_source"] = f"blocked:{type(e).__name__}"
                    blocked = True
                    geocoded_fail += 1
                seen_names[pname] = entry[f"{role}_coords"]
                time.sleep(1.1)
            endpoints["lines"].append(entry)
    endpoints["summary"] = {"csv_bizerte_lines": len(bc_rows),
                            "seed_bizerteconnect_lines": len(seed_bc),
                            "geocoded_ok": geocoded_ok, "geocoded_fail_or_blocked": geocoded_fail,
                            "blocked": blocked}
    with open(DATA / "bizerte_endpoints.json", "w", encoding="utf-8") as f:
        json.dump(endpoints, f, ensure_ascii=False, indent=1)

    # --- trilingual coverage in tables ---
    names_in_tables = 0
    names_ar = 0
    for idx in index:
        t = json.load(open(TABLES / idx["file"], encoding="utf-8"))
        for d in t["stations_detail"]:
            names_in_tables += 1
            if d.get("name_ar"):
                names_ar += 1

    summary = {
        "generated_by": "scripts/phase2_build_tables.py",
        "offline": OFFLINE,
        "lines_processed": len(lines),
        "tables_written": tables_written,
        "per_mode": dict(sorted(per_mode.items())),
        "stations_ordered_total": total_stations_ordered,
        "loop_lines": loop_lines,
        "duplicate_lines": dup_lines,
        "duplicates_removed_total": total_dup_removed,
        "backforth_lines": backforth_lines,
        "corrected_order_lines": corrected_lines,
        "unknown_mode": {
            "seed_unknown_total": len(unknown_resolution),
            "resolved": len(unk_resolved),
            "left_unknown": len(unk_left),
            "resolved_detail": unk_resolved,
            "left_unknown_ids": sorted(unk_left),
            "note": ("seed has 76 unknown (transport_map_corrected has 77); "
                     "resolution = single-line-mode, else station_reference proximity <=150m, "
                     "else name_mapping proximity; remainder stay unknown (no invented mode)"),
        },
        "water_verification": {
            "flagged": len(water_sample),
            "network": water_network,
            "outcomes": Counter(r["status"] for r in water_results),
            "confirmations_written_to": "data/water_corrections.json",
            "results": water_results,
        },
        "bizerte_endpoints": endpoints["summary"],
        "trilingual_in_tables": {"station_rows": names_in_tables,
                                 "with_name_ar": names_ar,
                                 "source": "data/phase1_names.json (provenance-tagged; null = no source)"},
        "remaining_for_phase3": [
            "relocate confirmed-sea water stations (see data/water_corrections.json); inconclusive/needs_osm_verify need manual OSM check",
            "BizerteConnect lines have endpoints only (no intermediate stops) — stops must come from SRT Bizerte source, not geocoding",
            "unknown-mode stations left unknown need operator source (Transtu/SRTM) — do not guess",
            "commune-centroid >30km check still impossible (no centroid dataset)",
            "stale seed metadata (coordinate_coverage: 1534) untouched",
            "trilingual names embedded in data/tables/* only; backend catalog rebuild (build_transport_catalog.py) not rerun",
        ],
    }
    with open(DATA / "phase2_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: summary[k] for k in
                      ("lines_processed", "tables_written", "per_mode",
                       "stations_ordered_total", "loop_lines", "duplicate_lines",
                       "backforth_lines", "corrected_order_lines")}, indent=1))
    print("unknown:", summary["unknown_mode"]["resolved"], "resolved /",
          summary["unknown_mode"]["left_unknown"], "left")
    print("water:", dict(summary["water_verification"]["outcomes"]))
    print("bizerte:", summary["bizerte_endpoints"])


if __name__ == "__main__":
    sys.exit(main())
