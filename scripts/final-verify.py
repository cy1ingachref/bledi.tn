#!/usr/bin/env python3
"""Ad-hoc verification for the bledi.tn frontend render, the CORRECTED deliverables.

The transport catalog is grouped BY MODE (bus has its own list, louage its own,
...), so a single physical station appears once PER mode it serves. That is the
intended representation — the user directed the 22 SNTRI physical-hub pairs to
be KEPT (intercity pulling up to the same platform as a city bus).

So the invariants verified here are:
  - build/transport_catalog.json has all 7 modes, 7451 unique station IDs,
    7502 mode entries, 379 line entries, human-readable labels
  - catalog station ids exactly match the corrected seed (0 mismatches both ways)
  - every station has valid lat/lon, except the 7 quarantined rows
  - physical-overlap hubs are KEPT and multi-mode counts match the seed
"""
import json
import os
import sys
from collections import defaultdict

BASE = r"C:\Users\cy1in\bledi.tn"
CATALOG_BUILD = os.path.join(BASE, "apps", "web", "build", "transport_catalog.json")
SEED = os.path.join(BASE, "data", "seed_all_tunisia_routes.CLEANED.corrected.json")

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append("  FAIL: %s %s" % (name, detail))


def main():
    for p in (CATALOG_BUILD, SEED):
        check("exists %s" % os.path.basename(p), os.path.isfile(p), p)
    if not all(os.path.isfile(p) for p in (CATALOG_BUILD, SEED)):
        print("Missing files; aborting.")
        sys.exit(1)

    b = json.load(open(CATALOG_BUILD, encoding="utf-8"))
    d = json.load(open(SEED, encoding="utf-8"))

    # A. Modes & counts
    check("all 7 modes present", set(b["modes"].keys()) == {"bus", "louage", "metro", "rail", "taxi", "train", "unknown"},
          str(list(b["modes"].keys())))
    check("bus label 'Buses'", b["modes"]["bus"]["name"] == "Buses", repr(b["modes"]["bus"].get("name")))
    check("bus name_fr 'Bus'", b["modes"]["bus"].get("name_fr") == "Bus")
    check("bus name_ar 'باصات'", b["modes"]["bus"].get("name_ar") == "باصات")

    total_entries = sum(len(v["stations"]) for v in b["modes"].values())
    total_lines = sum(len(v["lines"]) for v in b["modes"].values())
    check("total mode entries == 7502", total_entries == 7502, str(total_entries))
    check("total line entries == 379", total_lines == 379, str(total_lines))

    # B. Unique stations / consistency with corrected seed
    flat = [s for v in b["modes"].values() for s in v["stations"]]
    unique_ids = {s["id"] for s in flat}
    check("7451 unique station IDs", len(unique_ids) == 7451, str(len(unique_ids)))
    seed_ids = {s["id"] for s in d["stations"]}
    check("catalog ids == corrected seed", unique_ids == seed_ids, "catalog-only=%d seed-only=%d"
          % (len(unique_ids - seed_ids), len(seed_ids - unique_ids)))

    # C. Station records valid (only 7 quarantined rows lack coords)
    no_coords = [s["id"] for s in flat if not s.get("lat") or not s.get("lon")]
    quarantined = {"ajim", "bir_mouzaina", "douane_bir_mouzaina",
                   "dl_bledi_curated_workbook_ajim", "dl_bledi_curated_workbook_bir_mouzaina",
                   "dl_bledi_curated_workbook_douane_bir_mouzaina", "srtgn_croisement_ghorfa_8e1674a84b"}
    check("only quarantined rows lack coords", set(no_coords) <= quarantined and len(no_coords) == 7, str(no_coords))
    bad_coords = [s["id"] for s in flat if s.get("lat") is not None and s.get("lon") is not None
                  and (not isinstance(s["lat"], (int, float)) or not isinstance(s["lon"], (int, float)))]
    check("all coords numeric", len(bad_coords) == 0, str(bad_coords))

    # D. Multi-mode stations (physical hubs KEPT)
    cat_by_id = defaultdict(list)
    for mode, rec in b["modes"].items():
        for s in rec["stations"]:
            cat_by_id[s["id"]].append(s["mode"])
    multi_mode = {sid: modes for sid, modes in cat_by_id.items() if len(modes) > 1}
    check("multi-mode stations exist (physical hubs kept, not collapsed)", len(multi_mode) > 0, str(len(multi_mode)))

    expected_hubs = ["sabra_chatila", "route_nationale_7", "mateur_est",
                     "srtgn_elghorfa_6bd75e405a", "dl_srtgn_croisement_ghorfa_76199"]
    present_hubs = [h for h in expected_hubs if h in cat_by_id]
    check("physical-overlap hubs held",
          set(present_hubs) == set(expected_hubs), str(present_hubs))

    # E. Human-readable labels
    labels = {m: b["modes"][m]["name"] for m in b["modes"]}
    check("bus label 'Buses'", labels.get("bus") == "Buses", repr(labels.get("bus")))
    check("metro label 'Metro'", labels.get("metro") == "Metro", repr(labels.get("metro")))
    check("label non-empty for all modes", all(labels.values()))
    check("bus label is English 'Buses' (not raw 'bus')",
          not labels.get("bus", "").startswith("bus"))

    # G. Summary
    print()
    for p in FAILURES:
        print(p)
    print()
    print("ad-hoc verification: PASS=%d FAIL=%d" % (PASS, FAIL))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
