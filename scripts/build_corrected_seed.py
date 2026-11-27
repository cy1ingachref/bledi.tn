#!/usr/bin/env python3
"""Rebuild the corrected seed from the canonical tagged seed, applying the user's corrections:

  1. Stack pairs (28):
     - DROP only the text-parsing duplicate (sabra_amp_chatila).
     - MERGE the 22 SNTRI "local hub" pairs (intercity bus + city bus share a
       platform -> unified hub node).
     - KEEP (route_nationale_7 + mateur_est) and (srtgn_elghorfa +
       dl_srtgn_croisement_ghorfa_76199) - physical reality / resolved orphan.
  2. Bounding box: pad western limit to 7.50 -> keeps Hazoua.
  3. Ain Drahem: replace bad Tunis placeholder (36.827, 10.350) with the real
     Louage & Regional Bus Station footprint (36.77803, 8.68783).

Output: data/seed_all_tunisia_routes.CLEANED.corrected.json
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SEED = BASE / "data" / "seed_all_tunisia_routes.tagged.json"
OUT  = BASE / "data" / "seed_all_tunisia_routes.CLEANED.corrected.json"

BOX_WEST = 7.50
AIN_DRAHEM = (36.77803, 8.68783)
DROP = {"sabra_amp_chatila"}
KEEP_FIRST = {"route_nationale_7", "mateur_est",
              "srtgn_elghorfa_6bd75e405a", "dl_srtgn_croisement_ghorfa_76199"}


def main():
    tagged = json.loads(SEED.read_text(encoding="utf-8"))
    stations = tagged.get("stations", [])

    # stack analysis from tagged seed
    g = defaultdict(list)
    for s in stations:
        if s.get("lat") and s.get("lon"):
            g[(round(s["lat"], 5), round(s["lon"], 5))].append(s["id"])

    keep = {s["id"] for s in stations}  # keep everything by default
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
            # physical reality / resolved orphan: keep the whole pair
            keep.update(ids)
            continue
        # SNTRI local-hub merge: drop the local-name row, keep the SNTRI id
        dropped.append((first, coord, second, "merged into SNTRI local hub"))
        merged_hubs.append((first, second, coord))

    cleaned = []
    for s in stations:
        sid = s.get("id")
        if sid in DROP or sid in [d[0] for d in dropped]:
            continue
        if sid in keep:
            cleaned.append(dict(s))

    # fix Ain Drahem coords
    for s in cleaned:
        if s.get("id") == "ain_drahem":
            s["lat"], s["lon"] = AIN_DRAHEM
            s["corrected_from"] = {"lat": 36.827, "lon": 10.350,
                                   "note": "real Louage & Regional Bus Station footprint"}

    cleaned.sort(key=lambda s: (s.get("id") or ""))

    bad = [s for s in cleaned if s.get("lat") and s.get("lon")
           and not (30.23 <= s["lat"] <= 37.56 and 7.50 <= s["lon"] <= 11.65)]
    haz = [s for s in cleaned if s.get("id") == "sntri_hazoua_7cfe222ed7"]
    print("out of padded box (west<7.50):", [(b["id"], b["lat"], b["lon"]) for b in bad])
    print("Hazoua kept:", [(h["id"], h["lat"], h["lon"]) for h in haz])

    tagged["stations"] = cleaned
    tagged["metadata"] = {
        "seed": "seed_all_tunisia_routes.tagged.json (corrected)",
        "stations": len(cleaned),
        "lines": len(tagged.get("lines", [])),
        "box_west_deg": BOX_WEST,
        "ain_drahem_corrected": AIN_DRAHEM,
        "dropped_rows": dropped,
        "merged_sntri_hubs": merged_hubs,
    }
    OUT.write_text(json.dumps(tagged, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", OUT)

    print("=" * 70)
    print("CORRECTED SEED SUMMARY")
    print("=" * 70)
    print("stations:", len(cleaned), "| lines:", len(tagged.get("lines", [])))
    print("dup ids:", [k for k, v in Counter(s["id"] for s in cleaned).items() if v > 1])
    print("stations w/o coords:", sum(1 for s in cleaned if not s.get("lat") or not s.get("lon")))
    g2 = defaultdict(list)
    for s in cleaned:
        if s.get("lat") and s.get("lon"):
            g2[(round(s["lat"], 5), round(s["lon"], 5))].append(s["id"])
    print("stack pairs:", len([(k, v) for k, v in g2.items() if len(v) > 1]))
    print("out of padded box:", len(bad))
    print("dropped rows:", [(d[0], d[3]) for d in dropped])


if __name__ == "__main__":
    main()
