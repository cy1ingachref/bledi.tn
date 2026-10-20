#!/usr/bin/env python3
"""BLEDI.TN CLEAN — connect every transport mode with stations/stops/beginning,
remove dupes, place each station exactly once, and mark unroutable lines."""
import json
import math
from collections import defaultdict
from pathlib import Path

SEED = "C:/Users/cy1in/bledi.tn/data/seed_all_tunisia_routes.tagged.json"
OUT  = "C:/Users/cy1in/bledi.tn/data/seed_all_tunisia_routes.CLEANED.json"
MAP  = "C:/Users/cy1in/bledi.tn/data/transport_map.json"

TUNISIA = dict(lat_min=30.23, lat_max=37.56, lon_min=7.60, lon_max=11.65)
HARD = dict(lat_min=30.0,  lat_max=39.0,  lon_min=7.0,  lon_max=12.0)
R = 6371000.0


def norm_key(name):
    return " ".join(str(name).lower().replace("&amp;", "&").split())


def haversine(a, b):
    la1, lo1 = map(math.radians, a)
    la2, lo2 = map(math.radians, b)
    dl = la2 - la1
    dd = lo2 - lo1
    return 2 * R * math.asin(math.sqrt(math.sin(dl/2)**2 + math.cos(la1)*math.cos(la2)*math.sin(dd/2)**2))


def in_window(lat, lon, box):
    return box["lat_min"] <= lat <= box["lat_max"] and box["lon_min"] <= lon <= box["lon_max"]


def canonical_mode(raw):
    if raw in (None, "", "unknown"):
        return "unclassified"
    r = str(raw).strip().lower()
    if r in ("rail",):
        return "train"
    if r.startswith("louage"):
        return "louaj"
    if r == "rfr":
        return "bus"
    if r in ("metro", "metro_lev"):
        return "metro"
    return r


def main():
    seed = json.loads(open(SEED, encoding="utf-8").read())
    stations = seed.get("stations", [])
    lines = seed.get("lines", [])

    print("loaded: %d stations, %d lines" % (len(stations), len(lines)))

    sidx = {s["id"]: s for s in stations if s.get("id")}
    by_name = defaultdict(list)
    for s in stations:
        if s.get("name"):
            by_name[norm_key(s["name"])].append(s["id"])
    name_alpha = {nk: ids for nk, ids in by_name.items() if len(ids) == 1}

    # 5. line stop resolution: id vs name
    name_refs = []
    for ln in lines:
        for sid in (ln.get("stations") or ln.get("stops") or []):
            if sid and sid not in sidx:
                name_refs.append((ln.get("id"), ln.get("number"), sid))
    print("line stop refs that are not ids: %d" % len(name_refs))

    resolved_lines = []
    unresolved = 0
    for ln in lines:
        stops = ln.get("stations") or ln.get("stops") or []
        new_stops = []
        for sid in stops:
            if sid and sid in sidx:
                new_stops.append(sid)
                continue
            if not sid:
                new_stops.append(None)
                continue
            nk = norm_key(sid)
            cands = by_name.get(nk, [])
            if len(cands) == 1:
                new_stops.append(cands[0])
            elif len(cands) > 1:
                existing = [i for i in cands if i in sidx]
                pick = existing[0] if existing else cands[0]
                if existing:
                    print("   ambiguous name %r resolved to %s" % (sid, pick))
                new_stops.append(pick)
            elif nk in name_alpha:
                new_stops.append(name_alpha[nk][0])
            else:
                unresolved += 1
                new_stops.append(None)
        ln = dict(ln)
        ln["stations"] = [s for s in new_stops if s]
        resolved_lines.append(ln)
    print("unresolved name-based stop refs: %d" % unresolved)

    # 1. station stack cleanup
    grp = defaultdict(list)
    for s in stations:
        if s.get("lat") is not None and s.get("lon") is not None:
            grp[(round(s["lat"], 6), round(s["lon"], 6))].append(s)
    stacked = {k: v for k, v in grp.items() if len(v) > 1}
    print("stacked coordinate groups: %d" % len(stacked))
    for k, v in sorted(stacked.items(), key=lambda kv: -len(kv[1]))[:15]:
        print("   %s -> %s" % (k, [x["id"] for x in v]))

    station_by_id = {}
    for (lat, lon), group in sorted(grp.items()):
        if len(group) == 1:
            s = group[0]
            s["lat"] = lat
            s["lon"] = lon
            station_by_id[s["id"]] = s
        else:
            keep = group[0]
            keep["lat"] = lat
            keep["lon"] = lon
            station_by_id[keep["id"]] = keep
    dropped = [s["id"] for g in stacked.values() for s in g[1:]]
    print("stacked stations dropped: %d" % len(dropped))

    sidx = station_by_id
    by_name = defaultdict(list)
    for s in station_by_id.values():
        if s.get("name"):
            by_name[norm_key(s["name"])].append(s["id"])
    name_alpha = {nk: ids for nk, ids in by_name.items() if len(ids) == 1}

    # 2. coordinate inspection
    out_hard = []
    for s in station_by_id.values():
        lat, lon = s.get("lat"), s.get("lon")
        if lat is None or lon is None or lat == 0 or lon == 0:
            continue
        if not in_window(lat, lon, HARD):
            out_hard.append((s["id"], lat, lon, s.get("name")))
    print("stations outside hard box: %d" % len(out_hard))
    for x in out_hard[:15]:
        print("   %s (%s, %s) %s" % x)

    # 3. quarantine user_reported_faulty entries
    for s in station_by_id.values():
        name = (s.get("name") or "").strip().lower()
        if "croisement ghorfa" in name or "croisement_ghorfa" in name:
            s["quarantined"] = True
            s["quarantine_reason"] = "user_reported_faulty"
            s["quarantined_from"] = {"lat": s.get("lat"), "lon": s.get("lon")}
            s["lat"] = None
            s["lon"] = None
            print("quarantined %r" % s["name"])

    mode_counts = defaultdict(int)
    for s in station_by_id.values():
        mode_counts[canonical_mode(s.get("mode"))] += 1
    print("station modes: %s" % dict(mode_counts))

    # 4. line routable markers
    routable_false = []
    for ln in resolved_lines:
        stops = ln.get("stations") or []
        valid = [sid for sid in stops if sid in station_by_id]
        ln["_valid_stops"] = len(valid)
        if len(valid) < 2:
            ln["routable"] = False
            routable_false.append(ln.get("id"))
    print("lines with <2 valid stops marked routable=false: %d" % len(routable_false))
    print("example routable-false ids: %s" % routable_false[:10])

    # metadata bookkeeping
    meta = seed.get("metadata", {})
    meta["stations"] = len(station_by_id)
    meta["lines"] = len(resolved_lines)
    meta["stacked_stations_dropped"] = len(dropped)
    meta["stations_outside_hard_box"] = len(out_hard)
    meta["unresolved_name_stop_refs"] = unresolved
    meta["lines_marked_routable_false"] = len(routable_false)
    meta["quarantined_stations"] = sum(1 for s in station_by_id.values() if s.get("quarantined"))
    meta["stations_by_mode"] = dict(mode_counts)
    seed["stations"] = list(station_by_id.values())
    seed["lines"] = resolved_lines
    seed["metadata"] = meta
    json.dump(seed, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("wrote %s" % OUT)

    build_transport_map(seed)
    print("wrote %s" % MAP)

    print("="*70)
    print("CLEANING SUMMARY")
    print("="*70)
    print("stations (post-stack): %d" % len(station_by_id))
    print("stacked dropped:        %d" % len(dropped))
    print("outside hard box:       %d" % len(out_hard))
    print("unresolved name refs:   %d" % unresolved)
    print("lines routable=false:   %d" % len(routable_false))
    print("quarantined:            %d" % sum(1 for s in station_by_id.values() if s.get("quarantined")))
    print("stacked groups:         %d" % len(stacked))


def build_transport_map(seed):
    stations = seed.get("stations", [])
    lines = seed.get("lines", [])
    sidx = {s["id"]: s for s in stations if s.get("id")}
    sname = {s["id"]: (s.get("name") or s["id"]) for s in stations}

    mode_stations = defaultdict(lambda: {"stations": {}, "station_ids": []})
    mode_lines = defaultdict(list)

    for s in stations:
        m = canonical_mode(s.get("mode"))
        entry = mode_stations[m]["stations"]
        entry[s["id"]] = {
            "id": s["id"], "name": s.get("name") or s["id"],
            "lat": s.get("lat"), "lon": s.get("lon"),
            "operator": s.get("operator"),
            "station_type": s.get("station_type") or s.get("mode"),
            "lines_served": [ls.get("route_short_name") or ls.get("direction")
                             for ls in s.get("lines_served", []) if ls.get("direction")],
        }
        mode_stations[m]["station_ids"].append(s["id"])

    for ln in lines:
        m = canonical_mode(ln.get("mode"))
        stops = ln.get("stations") or []
        valid = [sid for sid in stops if sid in sidx]
        if not valid:
            continue
        mode_lines[m].append({
            "id": ln.get("id"), "number": ln.get("number"),
            "name": ln.get("name") or ln.get("id"),
            "operator": ln.get("operator"), "type": ln.get("type"),
            "stops": valid,
            "departures": ln.get("departures") or [],
            "return_departures": ln.get("return_departures") or [],
            "routable": ln.get("routable", True),
        })

    transport_map = {
        "metadata": {
            "seed": "seed_all_tunisia_routes.tagged.json (cleaned)",
            "covered_modes": sorted(mode_stations.keys()),
            "stations_total": len(stations),
            "lines_total": len(lines),
        },
        "by_mode": {},
    }

    for m in sorted(mode_stations.keys()):
        st = mode_stations[m]
        stops_list = []
        for sid in st["station_ids"]:
            s = st["stations"][sid]
            serving_lines = []
            for ln in mode_lines.get(m, []):
                if sid in ln["stops"]:
                    serving_lines.append({
                        "line": ln["id"], "number": ln["number"],
                        "name": ln["name"], "stops": ln["stops"],
                        "order": ln["stops"].index(sid) + 1,
                    })
            serving_lines.sort(key=lambda x: x["order"])
            stops_list.append({
                "id": s["id"], "name": s["name"],
                "lat": s["lat"], "lon": s["lon"],
                "operator": s["operator"],
                "station_type": s["station_type"],
                "lines_served": s["lines_served"],
                "serving_lines": serving_lines,
            })

        ordered_stations = order_stations_within_lines(
            mode_lines.get(m, []), st["station_ids"], sidx, sname, st["stations"])
        transport_map["by_mode"][m] = {
            "mode": m, "modes": mode_options(m),
            "station_count": len(stops_list),
            "stations": ordered_stations,
            "lines": mode_lines.get(m, []),
        }
    json.dump(transport_map, open(MAP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def mode_options(mode):
    if mode == "louaj":
        return ["louage"]
    if mode == "unclassified":
        return ["bus", "train", "metro", "taxi"]
    return [mode]


def order_stations_within_lines(lines, station_ids, sidx, sname, stations_by_id):
    """Walk each line's ordered stops and emit each station exactly once.

    Returns a list of full station dicts (with lat/lon) in first-seen order.
    """
    if not lines:
        return sorted(
            ({"id": sid, "name": sname.get(sid, sid), "lat": stations_by_id[sid].get("lat"),
              "lon": stations_by_id[sid].get("lon")} for sid in station_ids),
            key=lambda x: x["name"])

    seen = set()
    order = []
    # seed with the head of each line (first stop)
    for ln in lines:
        for sid in ln["stops"]:
            if sid not in seen:
                seen.add(sid)
                order.append(sid)
                break
    # then collect the remaining stops in line order
    for ln in lines:
        for sid in ln["stops"]:
            if sid not in seen:
                seen.add(sid)
                order.append(sid)
    # include any station with no lines
    for sid in station_ids:
        if sid not in seen:
            seen.add(sid)
            order.append(sid)
    # emit full station dicts; track any reference missing from the table
    missing = [sid for sid in order if sid not in stations_by_id]
    if missing:
        print("   warning: %d station references in lines missing from table: %s" % (len(missing), missing))
    return [dict(stations_by_id[sid]) for sid in order if sid in stations_by_id]


if __name__ == "__main__":
    main()
