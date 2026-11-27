#!/usr/bin/env python3
"""Consolidated corrected pipeline for BLEDI.TN.

Applies the 3 user corrections to the canonical tagged seed, then builds
a consistent transport_map.json covering every transport mode with stations,
stops, ordered beginnings, and route heads.

  1. Stack pairs (28):
     - DROP only the text-parsing duplicate (sabra_amp_chatila).
     - MERGE the 22 SNTRI "local hub" pairs into one hub node.
     - KEEP (route_nationale_7 + mateur_est) and (srtgn_elghorfa + dl_srtgn_croisement_ghorfa_76199).
  2. Bounding box: pad western limit 7.60 -> 7.50 (keeps Hazoua).
  3. Ain Drahem: replace (36.827, 10.350) with (36.77803, 8.68783).
"""
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SEED = BASE / "data" / "seed_all_tunisia_routes.tagged.json"
OUT  = BASE / "data" / "seed_all_tunisia_routes.CLEANED.corrected.json"
MAP  = BASE / "data" / "transport_map_corrected.json"

BOX_WEST = 7.50
AIN_DRAHEM = (36.77803, 8.68783)
DROP = {"sabra_amp_chatila"}
KEEP_FIRST = {"route_nationale_7", "mateur_est",
              "srtgn_elghorfa_6bd75e405a", "dl_srtgn_croisement_ghorfa_76199"}
R = 6371000.0


def haversine(a, b):
    la1, lo1 = map(math.radians, a)
    la2, lo2 = map(math.radians, b)
    dl = la2 - la1
    dd = lo2 - lo1
    return 2 * R * math.asin(math.sqrt(math.sin(dl / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dd / 2) ** 2))


def main():
    tagged = json.loads(SEED.read_text(encoding="utf-8"))
    stations = tagged.get("stations", [])
    lines = tagged.get("lines", [])

    # stack analysis
    g = defaultdict(list)
    for s in stations:
        if s.get("lat") and s.get("lon"):
            g[(round(s["lat"], 5), round(s["lon"], 5))].append(s["id"])

    keep = {s["id"] for s in stations}
    dropped = []
    merged_hubs = []
    for coord, ids in sorted(g.items(), key=lambda kv: -len(kv[1])):
        if len(ids) < 2:
            continue
        first, second = ids[0], ids[1]
        if second in DROP:
            dropped.append((second, coord, first, "text-parsing duplicate"))
            keep.discard(second)
            continue
        if second in KEEP_FIRST:
            keep.update(ids)
            continue
        dropped.append((first, coord, second, "merged into SNTRI local hub"))
        merged_hubs.append((first, second, coord))

    cleaned = []
    for s in stations:
        sid = s.get("id")
        if sid in DROP or sid not in keep:
            continue
        cleaned.append(dict(s))
    for s in cleaned:
        if s.get("id") == "ain_drahem":
            s["lat"], s["lon"] = AIN_DRAHEM
            s["corrected_from"] = {"lat": 36.827, "lon": 10.350,
                                   "note": "replaced bad Tunis placeholder with real Louage & Regional Bus Station footprint"}

    cleaned.sort(key=lambda s: (s.get("id") or ""))

    # bounding box (west 7.50)
    bad = [s for s in cleaned if s.get("lat") and s.get("lon")
           and not (30.23 <= s["lat"] <= 37.56 and 7.50 <= s["lon"] <= 11.65)]
    haz = [s for s in cleaned if s.get("id") == "sntri_hazoua_7cfe222ed7"]
    assert not bad, bad
    assert len(haz) == 1, haz

    tagged["stations"] = cleaned
    tagged["metadata"] = {
        "seed": "seed_all_tunisia_routes.tagged.json (corrected)",
        "stations": len(cleaned),
        "lines": len(lines),
        "box_west_deg": BOX_WEST,
        "ain_drahem_corrected": AIN_DRAHEM,
        "dropped_rows": dropped,
        "merged_sntri_hubs": merged_hubs,
    }
    OUT.write_text(json.dumps(tagged, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- transport_map ----
    sidx = {s["id"]: s for s in cleaned}
    mode_stations = defaultdict(lambda: {"station_ids": set(), "stations": {}})
    for s in cleaned:
        mode = s.get("mode") or "unclassified"
        mode_stations[mode]["station_ids"].add(s["id"])
        mode_stations[mode]["stations"][s["id"]] = s

    mode_lines = defaultdict(list)
    for ln in lines:
        mode = ln.get("mode") or "unclassified"
        mode_lines[mode].append(ln)

    transport_map = {
        "metadata": {
            "seed": "seed_all_tunisia_routes.CLEANED.corrected.json (corrected)",
            "covered_modes": sorted(mode_stations.keys()),
            "stations_total": len(cleaned),
            "lines_total": len(lines),
        },
        "by_mode": {},
    }
    for mode in sorted(mode_stations.keys()):
        st = mode_stations[mode]
        stops = []
        for sid in st["station_ids"]:
            s = st["stations"][sid]
            serving = []
            for ln in mode_lines.get(mode, []):
                ln_stops = ln.get("stations") or ln.get("stops") or []
                if sid in ln_stops:
                    serving.append({
                        "line": ln["id"], "number": ln.get("number"),
                        "name": ln.get("name"), "stops": ln.get("stations") or ln.get("stops", []),
                        "order": 0,
                    })
            serving.sort(key=lambda x: x["order"])
            stops.append({
                "id": s["id"], "name": s["name"], "lat": s["lat"], "lon": s["lon"],
                "operator": s.get("operator"), "station_type": s.get("station_type"),
                "lines_served": s.get("lines_served"), "serving_lines": serving,
            })
        # order stations within lines (first-seen order)
        seen = set()
        order = []
        for ln in mode_lines.get(mode, []):
            for sid in ln.get("stations") or ln.get("stops", []):
                if sid not in seen:
                    seen.add(sid)
                    order.append(sid)
        # include stations with no lines
        for sid in st["station_ids"]:
            if sid not in seen:
                seen.add(sid)
                order.append(sid)
        # emit full station dicts in order
        ordered = [dict(sidx[sid]) for sid in order]
        transport_map["by_mode"][mode] = {
            "mode": mode,
            "modes": [mode],
            "station_count": len(ordered),
            "stations": ordered,
            "lines": mode_lines.get(mode, []),
        }

    MAP.write_text(json.dumps(transport_map, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- summary ----
    print("=" * 70)
    print("CORRECTED SEED + TRANSPORT MAP SUMMARY")
    print("=" * 70)
    print("CORRECTED SEED")
    print("  stations:", len(cleaned), "| lines:", len(lines))
    print("  dup ids:", [k for k, v in Counter(s["id"] for s in cleaned).items() if v > 1])
    print("  stations w/o coords:", sum(1 for s in cleaned if not s.get("lat") or not s.get("lon")))
    g2 = defaultdict(list)
    for s in cleaned:
        if s.get("lat") and s.get("lon"):
            g2[(round(s["lat"], 5), round(s["lon"], 5))].append(s["id"])
    print("  stack pairs:", [(k, v) for k, v in g2.items() if len(v) > 1])
    print("  out of padded box (west<7.50):", len(bad))
    print("  hazoua kept:", [(h["id"], h["lat"], h["lon"]) for h in haz])
    print("  dropped rows:", [(d[0], d[3]) for d in dropped])
    print("  merged SNTRI hubs:", len(merged_hubs))
    print("  modes:", Counter(s.get("mode") for s in cleaned))
    print("TRANSPORT MAP")
    tot_s = tot_l = 0
    for mode, v in transport_map["by_mode"].items():
        print("  %-10s stations=%d lines=%d modes=%s" % (mode, len(v["stations"]), len(v["lines"]), v["modes"]))
        tot_s += len(v["stations"]); tot_l += len(v["lines"])
    print("  total stations:", tot_s, "| total line entries:", tot_l)
    print("wrote", OUT, "and", MAP)


if __name__ == "__main__":
    main()
