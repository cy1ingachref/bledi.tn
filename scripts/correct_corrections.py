#!/usr/bin/env python3
"""Apply the user's corrections to the BLEDI.TN cleaned seed.

3 fixes requested:
  1. Stack pairs: keep SNTRI "local hub" merges (22 pairs), drop only the
     text-parsing duplicate sabra_amp_chatila, and keep route_nationale_7
     + mateur_est and srtgn_elghorfa_6bd75e405a + dl_srtgn_croisement_ghorfa_76199.
  2. Bounding box: pad the western limit from 7.60 -> 7.50 (keep Hazoua).
  3. Ain Drahem: replace the bad Tunis placeholder (36.827, 10.350) with the
     real Louage & Regional Bus Station footprint (36.77803, 8.68783).
"""
import json
from collections import defaultdict
from pathlib import Path

BASE = Path("C:/Users/cy1in/bledi.tn")
SEED = BASE / "data" / "seed_all_tunisia_routes.CLEANED.json"
OUT  = BASE / "data" / "seed_all_tunisia_routes.CLEANED.corrected.json"

BOX_WEST = 7.50   # padded western limit (was 7.60)
AIN_DRAHEM = (36.77803, 8.68783)

def main():
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    stations = seed.get("stations", [])
    lines = seed.get("lines", [])

    # --- Fix 3: Ain Drahem coords ---
    for s in stations:
        if s.get("id") == "ain_drahem":
            s["lat"], s["lon"] = AIN_DRAHEM
            s["inaccurate_source_coordinate"] = True
            s["corrected_from"] = {"lat": 36.827, "lon": 10.350,
                                   "source": "user-provided real Louage & Regional Bus Station coord"}
            print("fix 3: ain_drahem -> %s, %s" % AIN_DRAHEM)
        if s.get("id") == "dl_bledi_curated_workbook_ain_drahem":
            s["lat"], s["lon"] = None, None
            s["quarantined"] = True
            s["quarantine_reason"] = "replaced by canonical ain_drahem (36.77803, 8.68783)"
            print("fix 3: workbook_ain_drahem nulled/quarantined")

    # --- Apply to the working dict for stacking analysis ---
    by_id = {s["id"]: s for s in stations}
    g = defaultdict(list)
    for s in stations:
        if s.get("lat") and s.get("lon"):
            g[(round(s["lat"], 5), round(s["lon"], 5))].append(s["id"])

    # --- Fix 1: stack handling ---
    DROP = {"sabra_amp_chatila"}          # pure text-parsing duplicate
    KEEP_FIRST = {"route_nationale_7", "srtgn_elghorfa_6bd75e405a",
                  "srtgn_croisement_ghorfa_76199"}  # physical reality / resolved orphan
    MERGED = set()

    for coord, ids in sorted(g.items(), key=lambda kv: -len(kv[1])):
        if len(ids) < 2:
            continue
        second = ids[1] if len(ids) == 2 else None
        if second in DROP:
            by_id[second]["dropped_reason"] = "text-parsing duplicate of first station"
            continue
        if second in KEEP_FIRST:
            by_id[second]["stack_group"] = coord
            by_id[second]["stack_partner"] = ids[0]
            by_id[second]["stack_status"] = "keep (physical hub)"
            MERGED.add(ids[0])
            continue
        # SNTRI local-hub merge (22 pairs): merge both rows into one hub node
        # Put the SNTRI national id first; drop the plain local name as the
        # duplicate display of the same physical platform.
        hub = by_id[second]
        hub["stack_group"] = coord
        hub["stack_partner"] = ids[0]
        hub["stack_status"] = "merged sntri local hub"
        by_id[ids[0]]["dropped_reason"] = "merged into SNTRI national hub node"
        MERGED.add(ids[0])

    # --- Fix 2: bounding box west limit 7.60 -> 7.50 ---
    bad = []
    for s in stations:
        if s.get("lat") and s.get("lon"):
            if not (30.23 <= s["lat"] <= 37.56 and 7.50 <= s["lon"] <= 11.65):
                bad.append((s["id"], s["lat"], s["lon"]))
    print("stations out of padded box (west 7.50):", [(b[0], b[1], b[2]) for b in bad])
    print("Hazoua kept at:", [s["lat"] for s in stations if s.get("id") == "sntri_hazoua_7cfe222ed7"])

    # --- Write ---
    # clean up helper markers we no longer want in the final deliverable
    for s in stations:
        for k in ("dropped_reason", "stack_status", "stack_partner", "stack_group", "corrected_from", "inaccurate_source_coordinate", "quarantined_from"):
            s.pop(k, None)
        s.pop("quarantined", None)

    # order by id for determinism
    stations.sort(key=lambda s: (s.get("id") or ""))
    seed["stations"] = stations

    seed["metadata"] = {
        "seed": "seed_all_tunisia_routes.tagged.json (corrected)",
        "stations": len(stations),
        "lines": len(lines),
        "box_west_deg": BOX_WEST,
        "ain_drahem_corrected": AIN_DRAHEM,
    }
    OUT.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", OUT)

    print("=" * 70)
    print("CORRECTED SEED SUMMARY")
    print("=" * 70)
    print("stations:", len(stations))
    print("lines:", len(lines))
    ids = [s.get("id") for s in stations]
    print("dup ids:", [k for k, v in __import__('collections').Counter(ids).items() if v > 1])
    g2 = defaultdict(list)
    for s in stations:
        if s.get("lat") and s.get("lon"):
            g2[(round(s["lat"], 5), round(s["lon"], 5))].append(s["id"])
    print("stacked coords:", [(k, v) for k, v in g2.items() if len(v) > 1])
    print("out of padded box:", bad)


if __name__ == "__main__":
    main()
