#!/usr/bin/env python3
"""Disambiguate shared station ids that cause teleport legs.

Source: data/transport_map_corrected.json (by_mode) — the file the Rust router
loads. Detection:
  1. Teleport legs: consecutive stations on a line whose haversine distance
     (using the station coordinates from that line's own mode block) exceeds
     20 km. Corroborated against data/phase3a_summary.json teleport_legs.
  2. Multi-block ids: the same station id appearing in >1 mode block.

For every affected id, a per-mode copy is created:  <id>__<mode>  (e.g.
les_salines__bus, les_salines__train). Station entries are renamed inside
their own mode block and line station references are rewritten to the copy
belonging to the line's mode. Coordinates are copied unchanged from the
source block; when a copy's coordinate does not fit its line context
(neighbors >20 km away in every line using it) it is flagged
coord_status="coord_does_not_match_line_context" with a
suggested_coord_from_neighbors estimate (midpoint of the nearest in-context
neighbors) — that estimate is NOT applied to the output coordinates, it is
a geocoding TODO, not a fabricated fix.

Outputs (original seed is never overwritten):
  data/station_disambiguation.json  mapping + counts + teleport inventory
  data/seed_disambiguated.json      renamed variant (same by_mode shape)
"""
from __future__ import annotations
import copy, json, math, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/transport_map_corrected.json"
SUMMARY = ROOT / "data/phase3a_summary.json"
TELEPORT_KM = 20.0


def hav_km(a, b, c, d):
    R = 6371.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def main():
    data = json.loads(SRC.read_text())
    by_mode = data.get("by_mode", {})
    # station coords per (mode, id)
    coords = {}          # (mode, id) -> (lat, lon)
    blocks_of_id = defaultdict(set)  # id -> {mode}
    for mode, block in by_mode.items():
        for s in block.get("stations", []):
            if s.get("lat") is not None and s.get("lon") is not None:
                coords[(mode, s["id"])] = (float(s["lat"]), float(s["lon"]))
                blocks_of_id[s["id"]].add(mode)

    # 1) teleport legs from the data itself
    teleport_legs, affected = [], set()
    for mode, block in by_mode.items():
        cmap = {sid: c for (m, sid), c in coords.items() if m == mode}
        for ln in block.get("lines", []):
            st = ln.get("stations", [])
            for a, b in zip(st, st[1:]):
                if a in cmap and b in cmap:
                    km = hav_km(*cmap[a], *cmap[b])
                    if km > TELEPORT_KM:
                        teleport_legs.append({"line_id": ln["id"], "mode": mode,
                                              "from": a, "to": b, "km": round(km, 2)})
                        affected.update([a, b])
    # 2) multi-block ids
    multi = {sid for sid, ms in blocks_of_id.items() if len(ms) > 1}
    affected |= multi
    # corroboration with phase3a
    phase3a_teleports = []
    if SUMMARY.exists():
        phase3a_teleports = json.loads(SUMMARY.read_text()).get("teleport_legs", [])
        for t in phase3a_teleports:
            affected.update([t.get("from"), t.get("to")])
    affected.discard(None)

    # per-id: which modes actually reference it (station block OR a line in
    # that mode) and in which lines it participates in a teleport leg
    modes_for_id = defaultdict(set)
    for sid in affected:
        modes_for_id[sid] |= blocks_of_id.get(sid, set())
    for t in teleport_legs:
        modes_for_id[t["from"]].add(t["mode"])
        modes_for_id[t["to"]].add(t["mode"])

    # coordinate fit per (id, mode): nearest neighbor distance in its lines
    def coord_fit(sid, mode):
        c = coords.get((mode, sid))
        if c is None:
            return None, None
        best = None
        for ln in by_mode.get(mode, {}).get("lines", []):
            st = ln.get("stations", [])
            if sid not in st:
                continue
            for i, x in enumerate(st):
                if x != sid:
                    continue
                for j in (i - 1, i + 1):
                    if 0 <= j < len(st):
                        nb = coords.get((mode, st[j]))
                        if nb:
                            d = hav_km(*c, *nb)
                            if best is None or d < best[0]:
                                best = (d, nb)
        return (best[0] if best else None), (best[1] if best else None)

    mapping, renames = {}, {}
    for sid in sorted(affected):
        entries = []
        for mode in sorted(modes_for_id[sid]):
            new_id = f"{sid}__{mode}"
            renames[(mode, sid)] = new_id
            c = coords.get((mode, sid))
            nearest_km, neighbour = coord_fit(sid, mode)
            fits = nearest_km is not None and nearest_km <= TELEPORT_KM
            entry = {"new_id": new_id, "mode": mode,
                     "lat": c[0] if c else None, "lon": c[1] if c else None,
                     "coord_status": "ok" if fits else "coord_does_not_match_line_context",
                     "nearest_neighbor_km": round(nearest_km, 2) if nearest_km is not None else None}
            if not fits and neighbour is not None and c is not None:
                entry["suggested_coord_from_neighbors"] = {
                    "lat": neighbour[0], "lon": neighbour[1],
                    "note": "nearest in-context neighbor; re-geocode this stop, do not use blindly"}
            entries.append(entry)
        mapping[sid] = entries

    # apply renames to a copy, never to the original file
    out = copy.deepcopy(data)
    changed_stations = changed_refs = changed_lines = 0
    for mode, block in out.get("by_mode", {}).items():
        for s in block.get("stations", []):
            key = (mode, s.get("id"))
            if key in renames:
                s["id"] = renames[key]
                s["disambiguated_from"] = key[1]
                changed_stations += 1
        for ln in block.get("lines", []):
            before = list(ln.get("stations", []))
            after = [renames.get((mode, x), x) for x in before]
            if after != before:
                ln["stations"] = after
                changed_lines += 1
                changed_refs += sum(1 for a, b in zip(before, after) if a != b)
    out["metadata"] = {**out.get("metadata", {}),
                       "disambiguated_by": "scripts/fix_shared_ids.py",
                       "disambiguated_note": "Station ids renamed to <id>__<mode> where the id was shared or participated in a >20km teleport leg. Coordinates unchanged; see data/station_disambiguation.json for coord TODOs."}

    disamb = {"generated_by": "scripts/fix_shared_ids.py", "source": str(SRC.relative_to(ROOT)),
              "teleport_threshold_km": TELEPORT_KM,
              "counts": {"teleport_legs_found": len(teleport_legs),
                         "phase3a_teleport_legs": len(phase3a_teleports),
                         "affected_station_ids": len(affected),
                         "multi_mode_block_ids": len(multi),
                         "renamed_station_entries": changed_stations,
                         "renamed_line_references": changed_refs,
                         "lines_touched": changed_lines},
              "mapping": mapping, "teleport_legs": teleport_legs}
    (ROOT / "data/station_disambiguation.json").write_text(json.dumps(disamb, indent=2, ensure_ascii=False))
    (ROOT / "data/seed_disambiguated.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(disamb["counts"], indent=2))
    print("affected ids:", sorted(affected)[:60])
    print("wrote data/station_disambiguation.json + data/seed_disambiguated.json")


if __name__ == "__main__":
    sys.exit(main())
