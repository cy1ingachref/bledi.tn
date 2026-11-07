#!/usr/bin/env python3
"""Phase 1 audit: inventory + geolocation + trilingual-name audit for bledi.tn.

Reads (never modifies) existing data files and writes:
  data/phase1_audit.json        counts + sample errors
  data/phase1_names.json        EN->AR/FR mapping (sourced only, no invention)
  data/phase1_missing_coords.csv top missing-coordinate stations to geocode

Tunisia bbox (task spec): lat 30.2-37.6, lon 7.3-11.7.
Water check: point-in-polygon against data/water_polys.json (GSHHG land
polygons, pure-python ray casting, no shapely dependency). A point inside
NO land polygon is flagged as sea/water. The crude bbox heuristic used by
data/water_stations.json is reported for contrast but NOT used as truth.

Commune >30km check: only partially computable. station_corrections.json
documents 5 corrections using that method, but no commune-centroid dataset
exists in the repo, so the full check is reported as a Phase 2 gap.

Usage:  python scripts/phase1_audit.py   (from repo root)
"""
import csv
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
LAT_MIN, LAT_MAX = 30.2, 37.6
LON_MIN, LON_MAX = 7.3, 11.7
AR_SCRIPT = re.compile(r"[\u0600-\u06FF]")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def has_arabic(s):
    return bool(s and AR_SCRIPT.search(s))


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def norm_name(s):
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- water check
def load_land_polys():
    """Return list of (minlon,maxlon,minlat,maxlat, [(lon,lat),...]) for land ways."""
    wp = load("water_polys.json")
    polys = []
    for el in wp.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) < 4:
            continue
        pts = [(g["lon"], g["lat"]) for g in geom]
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        polys.append((min(xs), max(xs), min(ys), max(ys), pts))
    return polys


def point_in_ring(lon, lat, pts):
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if ((yi > lat) != (yj > lat)):
            xint = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < xint:
                inside = not inside
        j = i
    return inside


def is_on_land(lon, lat, polys):
    for mnx, mxx, mny, mxy, pts in polys:
        if mnx <= lon <= mxx and mny <= lat <= mxy:
            if point_in_ring(lon, lat, pts):
                return True
    return False


# ------------------------------------------------------------------- audit
def main():
    tm = load("transport_map_corrected.json")
    seed = load("seed_all_tunisia_routes.tagged.json")
    ref = load("station_reference.json")
    naming = load("station_name_mapping.json")
    try:
        water_prev = load("water_stations.json")
        prev_water_ids = {w["id"] for w in water_prev.get("water_stations", [])}
        prev_water_meta = water_prev.get("metadata", {})
    except Exception:
        prev_water_ids, prev_water_meta = set(), {}

    # --- flatten transport_map_corrected stations
    tm_stations = []
    for mode, band in tm.get("by_mode", {}).items():
        for s in band.get("stations", []):
            tm_stations.append({**s, "_band": mode})
    seed_stations = seed.get("stations", [])
    ref_stations = ref.get("stations", [])

    audit = {"generated_by": "scripts/phase1_audit.py",
             "tunisia_bbox": {"lat": [LAT_MIN, LAT_MAX], "lon": [LON_MIN, LON_MAX]}}
    audit["inventory"] = {
        "transport_map_corrected": {
            "metadata": tm.get("metadata", {}),
            "stations_by_band": {m: len(b.get("stations", [])) for m, b in tm.get("by_mode", {}).items()},
            "total_stations_flattened": len(tm_stations)},
        "seed_tagged": {"metadata_total_stations": seed.get("metadata", {}).get("total_stations"),
                        "metadata_total_lines": seed.get("metadata", {}).get("total_lines"),
                        "metadata_coordinate_coverage_STALE": seed.get("metadata", {}).get("coordinate_coverage"),
                        "actual_with_coords": sum(1 for s in seed_stations if s.get("lat") and s.get("lon")),
                        "actual_missing_coords": sum(1 for s in seed_stations if not s.get("lat") or not s.get("lon")),
                        "modes": dict(Counter(s.get("mode") for s in seed_stations)),
                        "quarantined": sum(1 for s in seed_stations if s.get("quarantined"))},
        "station_reference": {"metadata": ref.get("metadata", {}),
                              "total_stations": len(ref_stations),
                              "with_name_ar_field": sum(1 for s in ref_stations if s.get("name_ar")),
                              "with_name_ar_arabic_script": sum(1 for s in ref_stations if has_arabic(s.get("name_ar"))),
                              "with_name_en_field": sum(1 for s in ref_stations if s.get("name_en")),
                              "raw_name_arabic_script": sum(1 for s in ref_stations if has_arabic(s.get("name"))),
                              "with_mode": sum(1 for s in ref_stations if s.get("mode")),
                              "with_gouvernorat": sum(1 for s in ref_stations if s.get("gouvernorat"))},
        "station_name_mapping_conflicts": naming.get("metadata", {}).get("total_conflicting_stations"),
        "station_name_mapping_entries": len(naming.get("stations", {})),
        "water_stations_prev_audit": prev_water_meta,
    }

    # --- coordinate audit over transport_map_corrected + seed
    polys = load_land_polys()
    audit["water_polys_land_polygons"] = len(polys)

    def coord_audit(stations, label):
        res = {"label": label, "total": len(stations), "missing": 0,
               "out_of_bbox": 0, "in_water": 0, "in_water_sample": [],
               "out_of_bbox_sample": [], "missing_sample": []}
        for s in stations:
            lat, lon = s.get("lat"), s.get("lon")
            if lat is None or lon is None:
                res["missing"] += 1
                if len(res["missing_sample"]) < 20:
                    res["missing_sample"].append({"id": s.get("id"), "name": s.get("name"),
                                                  "mode": s.get("mode"), "quarantined": s.get("quarantined"),
                                                  "quarantine_reason": s.get("quarantine_reason")})
                continue
            if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                res["out_of_bbox"] += 1
                if len(res["out_of_bbox_sample"]) < 20:
                    res["out_of_bbox_sample"].append({"id": s.get("id"), "name": s.get("name"),
                                                      "lat": lat, "lon": lon, "mode": s.get("mode")})
                continue
            if not is_on_land(lon, lat, polys):
                res["in_water"] += 1
                if len(res["in_water_sample"]) < 20:
                    res["in_water_sample"].append({"id": s.get("id"), "name": s.get("name"),
                                                   "lat": lat, "lon": lon, "mode": s.get("mode")})
        res["with_coords"] = res["total"] - res["missing"]
        return res

    audit["geolocation"] = {
        "transport_map_corrected": coord_audit(tm_stations, "transport_map_corrected"),
        "seed_tagged": coord_audit(seed_stations, "seed_tagged"),
        "note": "Water = point inside no GSHHG land polygon (pure-python ray casting). "
                "Commune >30km check NOT computable from repo data alone (no commune centroid "
                "dataset); only the 5 documented corrections in station_corrections.json use it.",
        "commune_gt30km": "uncomputable_in_repo",
    }

    # --- mode / icon mapping
    ICON_MAP = {"bus": "bus.svg", "metro": "metro.svg", "train": "train.svg",
                "rail": "train.svg", "louage": "louage.svg", "taxi": "taxi.svg",
                "unknown": "bus.svg", "rural": "louage.svg"}
    audit["icon_mapping"] = ICON_MAP
    audit["modes_present_tm"] = dict(Counter(s.get("mode") for s in tm_stations))
    audit["modes_missing_icon"] = [m for m in audit["modes_present_tm"] if m not in ICON_MAP]

    # --- overlap with previous water list (crude heuristic comparison)
    if prev_water_ids:
        current_water_ids = {s["id"] for s in audit["geolocation"]["transport_map_corrected"]["in_water_sample"]}
        tm_ids = {s.get("id") for s in tm_stations}
        audit["prev_water_overlap"] = {
            "prev_flagged_in_tm": len(prev_water_ids & tm_ids),
            "note": "Previous water_stations.json used bbox heuristics (lat>37.3 & lon>9.8 etc.) "
                    "and is known to false-positive on northern towns; do not treat the 772 count "
                    "as ground truth. Land-polygon result above is authoritative."}

    # --- trilingual names
    ref_by_norm = defaultdict(list)
    for s in ref_stations:
        for key in (s.get("name_en"), s.get("name")):
            if key:
                ref_by_norm[norm_name(key)].append(s)
    # grid index over ref stations for proximity fallback (0.02 deg cells)
    grid = defaultdict(list)
    for s in ref_stations:
        if s.get("lat") and s.get("lon"):
            grid[(round(s["lat"] / 0.02), round(s["lon"] / 0.02))].append(s)

    def nearby(ref_lat, ref_lon, lat, lon, max_m=250):
        best, best_d = None, max_m
        for dl_a in (-0.02, 0.0, 0.02):
            for dl_o in (-0.02, 0.0, 0.02):
                for s in grid.get((round(lat / 0.02) + dl_a, round(lon / 0.02) + dl_o), []):
                    d = haversine_m(lat, lon, s["lat"], s["lon"])
                    if d < best_d:
                        best, best_d = s, d
        return best, best_d

    names_out = {"note": "name_ar/name_fr taken ONLY from existing source fields; "
                         "blank means no source, not a guess. name_ar_fr_source records provenance.",
                 "mappings": [], "summary": {}}
    counts = Counter()
    for s in tm_stations:
        en = s.get("name_en") or s.get("name") or ""
        lat, lon = s.get("lat"), s.get("lon")
        name_ar, name_fr, source = None, None, []
        cand = ref_by_norm.get(norm_name(en), [])
        hit = None
        if cand:
            # prefer a candidate within 500 m if coords exist
            if lat and lon:
                hit = min(cand, key=lambda c: haversine_m(lat, lon, c["lat"], c["lon"]))
                if haversine_m(lat, lon, hit["lat"], hit["lon"]) > 500:
                    hit = None
            else:
                hit = cand[0]
        if hit is None and lat and lon:
            hit, d = nearby(0, 0, lat, lon, 250)
            if hit:
                source.append(f"station_reference_proximity_{int(d)}m")
        if hit is not None:
            if not source:
                source.append("station_reference_name_match")
            if has_arabic(hit.get("name_ar")):
                name_ar = hit["name_ar"]
            elif has_arabic(hit.get("name")):
                name_ar = hit["name"]
            if hit.get("name_en") and norm_name(hit["name_en"]) != norm_name(en):
                name_fr = hit["name_en"]  # French/Latin variant from source
            elif hit.get("name") and has_arabic(hit.get("name")):
                pass  # latin name already == en
        counts["en_only" if not name_ar and not name_fr else
               ("en_ar" if name_ar and not name_fr else
                ("en_fr" if name_fr and not name_ar else "en_ar_fr"))] += 1
        names_out["mappings"].append({"id": s.get("id"), "name_en": en, "name_ar": name_ar,
                                      "name_fr": name_fr, "mode": s.get("mode"),
                                      "icon": ICON_MAP.get(s.get("mode"), "bus.svg"),
                                      "source": source or ["no_source"]})
    names_out["summary"] = dict(counts)
    names_out["summary"]["total"] = len(tm_stations)

    # --- missing-coordinate geocode backlog
    missing_rows = []
    for s in seed_stations:
        if not s.get("lat") or not s.get("lon"):
            missing_rows.append({"station_id": s.get("id"), "name": s.get("name"),
                                 "mode": s.get("mode"), "operator": s.get("operator"),
                                 "status": "quarantined" if s.get("quarantined") else "missing",
                                 "note": s.get("quarantine_reason") or "",
                                 "geocode_hint": "verify place exists; do not reuse quarantined coords"})
    # BizerteConnect unroutable lines: lines with no stops/coords at all
    try:
        bc = load("bizerteconnect_network.json")
        bc_lines = bc.get("lines", [])
        bc_no_stops = [l for l in bc_lines if not l.get("stops")]
        for l in bc_no_stops[:200]:
            missing_rows.append({"station_id": f"bizerteconnect_line_{l.get('id', '?')}",
                                 "name": l.get("name") or l.get("line_name") or "?",
                                 "mode": "bus", "operator": "SRT Bizerte",
                                 "status": "line_no_stops_no_coords",
                                 "note": "BizerteConnect API publishes no stops endpoint; needs OSM/Nominatim",
                                 "geocode_hint": "Overpass/Nominatim by endpoint names"})
        audit["bizerteconnect"] = {"lines": len(bc_lines), "lines_no_stops": len(bc_no_stops)}
    except Exception as e:
        audit["bizerteconnect"] = {"error": str(e)}

    # --- write outputs
    with open(os.path.join(DATA, "phase1_audit.json"), "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA, "phase1_names.json"), "w", encoding="utf-8") as f:
        json.dump(names_out, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA, "phase1_missing_coords.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["station_id", "name", "mode", "operator", "status", "note", "geocode_hint"])
        w.writeheader()
        for r in missing_rows[:200]:
            w.writerow(r)

    print(json.dumps({"tm_modes": audit["modes_present_tm"],
                      "seed_missing": audit["inventory"]["seed_tagged"]["actual_missing_coords"],
                      "seed_with_coords": audit["inventory"]["seed_tagged"]["actual_with_coords"],
                      "tm_missing": audit["geolocation"]["transport_map_corrected"]["missing"],
                      "tm_out_of_bbox": audit["geolocation"]["transport_map_corrected"]["out_of_bbox"],
                      "tm_in_water": audit["geolocation"]["transport_map_corrected"]["in_water"],
                      "names_summary": names_out["summary"],
                      "missing_csv_rows": min(len(missing_rows), 200),
                      "land_polys": len(polys)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
