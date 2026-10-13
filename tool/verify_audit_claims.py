#!/usr/bin/env python3
"""Verify the station audit's claims, from scratch, and pin its fixed bugs.

This is the audit's own gate. It re-derives every headline number from the seed
rather than trusting `out/audit.json`, and it asserts the specific defects that
were found and fixed so none can silently return.

    python tool/verify_audit_claims.py
    python tool/verify_audit_claims.py --no-water   # skip the 7 MB index

Exit 0 = every claim holds. Exit 1 = at least one does not, and the failures are
printed. Nothing here mutates the seed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))

from audit_station_placement import (  # noqa: E402
    LOUAGE,
    SEED,
    TUNISIA_BBOX,
    WaterIndex,
    canonical,
    clip_ring_to_window,
    haversine_m,
    in_bbox,
    point_in_ring,
)

FAILS: list[str] = []
N = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global N
    N += 1
    if not ok:
        FAILS.append(label)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  -> {detail}" if detail and not ok else ""))


def load_stations() -> list[dict]:
    rows = json.loads(SEED.read_text(encoding="utf-8"))["stations"]
    if LOUAGE.is_file():
        for s in json.loads(LOUAGE.read_text(encoding="utf-8")).get("stations", []):
            loc = s.get("location") or {}
            rows.append({
                "id": f"louage_{s.get('id')}",
                "name": s.get("name_fr") or s.get("name"),
                "lat": loc.get("lat"),
                "lon": loc.get("lon"),
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-water", action="store_true", help="skip the water index tests")
    args = ap.parse_args()

    # ── 1. distances ─────────────────────────────────────────────────────
    print("\n1. haversine (a double sqrt once inflated every distance 10.5x)")
    for label, got, want, tol in [
        ("Tunis->Sousse", haversine_m(36.8065, 10.1815, 35.8256, 10.6084) / 1000, 115.6, 2),
        ("Tunis->Sfax", haversine_m(36.8065, 10.1815, 34.7406, 10.7603) / 1000, 235.6, 3),
        ("1 deg lat", haversine_m(36.0, 10.0, 37.0, 10.0) / 1000, 111.2, 1),
    ]:
        check(f"{label} = {want} km", abs(got - want) < tol, f"got {got:.1f}")
    check("identical points are 0 m", haversine_m(36.8, 10.18, 36.8, 10.18) < 0.001)
    check("distance is symmetric",
          abs(haversine_m(36.8, 10.18, 37.2, 9.87) - haversine_m(37.2, 9.87, 36.8, 10.18)) < 1e-6)

    # ── 2. geometry ──────────────────────────────────────────────────────
    print("\n2. geometry primitives")
    sq = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    check("point_in_ring: inside", point_in_ring(1.0, 1.0, sq))
    check("point_in_ring: outside", not point_in_ring(3.0, 1.0, sq))
    cl = clip_ring_to_window([(-5.0, 1.0), (10.0, 1.0), (10.0, 3.0), (-5.0, 3.0)], 0, 0, 4, 4)
    check("clip confines to the window", len(cl) >= 3 and all(0 <= x <= 4 for x, _ in cl))
    check("clip of an outside ring is empty",
          clip_ring_to_window([(10.0, 10.0), (11.0, 10.0), (11.0, 11.0)], 0, 0, 4, 4) == [])

    # ── 3. bounds ────────────────────────────────────────────────────────
    print("\n3. Tunisia bounds (the network-coverage box once rejected these)")
    for name, lat, lon in [("Remada", 32.31528, 10.39870), ("Dhehiba", 32.01067, 10.70022),
                           ("Borj el Khadra", 30.24, 11.0), ("Bizerte", 37.274, 9.874)]:
        check(f"{name} is inside Tunisia", in_bbox(lat, lon, TUNISIA_BBOX))
    check("a point in the Mediterranean is outside", not in_bbox(38.5, 10.0, TUNISIA_BBOX))

    # ── 4. placement claims ──────────────────────────────────────────────
    print("\n4. placement (re-derived from the seed)")
    stations = load_stations()
    placed = [s for s in stations if s.get("lat") and s.get("lon")]
    unplaced = [s for s in stations if not (s.get("lat") and s.get("lon"))]
    print(f"     {len(stations)} stops, {len(placed)} placed, {len(unplaced)} not")
    check("stop count is 7 470", len(stations) == 7470, f"{len(stations)}")
    check("exactly 5 stops have no coordinates", len(unplaced) == 5, f"{len(unplaced)}")
    check("every unplaced stop is marked quarantined",
          all(s.get("quarantined") for s in unplaced),
          f"{[s['name'] for s in unplaced if not s.get('quarantined')]}")
    outside = [s for s in placed if not in_bbox(s["lat"], s["lon"], TUNISIA_BBOX)]
    check("0 stops outside Tunisia", not outside, f"{[s['name'] for s in outside[:5]]}")

    # Duplicate rows: a point where some name appears twice. That is the audit's
    # definition — a repeated name at one coordinate means the same physical
    # place is recorded twice, even if a differently-named row shares the spot.
    # Keying on the whole (name, lat, lon) tuple instead undercounts, because it
    # misses groups like [X, X, Y] where the duplicate sits beside another name.
    def norm(n: str) -> str:
        return " ".join((n or "").lower().replace("&amp;", "&").split())

    by_pos: dict[tuple, list[dict]] = {}
    for s in placed:
        by_pos.setdefault((round(s["lat"], 5), round(s["lon"], 5)), []).append(s)
    dup_groups = 0
    for group in by_pos.values():
        if len(group) < 2:
            continue
        names = [norm(g.get("name")) for g in group]
        if max(names.count(n) for n in set(names)) > 1:
            dup_groups += 1
    check("40 duplicate rows (a name repeated at one point)", dup_groups == 40, f"{dup_groups}")

    # ── 5. the quarantine defect must still be reproducible ──────────────
    print("\n5. the quarantine defect (the headline finding)")
    quar = [s for s in stations if s.get("quarantined")]
    check("5 rows quarantined", len(quar) == 5, f"{len(quar)}")
    check("quarantined rows have null coords",
          all(s.get("lat") is None and s.get("lon") is None for s in quar))
    leaked = []
    for q in quar:
        name = (q.get("name") or "").strip().lower()
        orig = q.get("quarantined_from") or {}
        for s in placed:
            if (s.get("name") or "").strip().lower() != name:
                continue
            if orig.get("lat") is not None and abs(s["lat"] - orig["lat"]) < 1e-4 \
                    and abs(s["lon"] - orig["lon"]) < 1e-4:
                leaked.append((q["name"], s["id"]))
    check("each quarantined name still has a live row at the same bad coordinate",
          len({n for n, _ in leaked}) == 5, f"{sorted({n for n, _ in leaked})}")
    check("Ajim also has a row at the CORRECT Djerba position",
          any(s.get("id") == "dl_sntri_ajim_85358" and abs(s["lat"] - 33.7249) < 0.01
              and abs(s["lon"] - 10.7483) < 0.01 for s in placed))

    # ── 6. backend city seats ────────────────────────────────────────────
    print("\n6. backend CITY_SEATS (both bugs were ~100 km off)")
    src = (ROOT / "src" / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    block = re.search(r"CITY_SEATS[^=]*=\s*\[(.*?)\n\]", src, re.S)
    seats = {m[0]: (float(m[1]), float(m[2]))
             for m in re.findall(r'\(\s*"([^"]+)"\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)', block.group(1))}
    check("CITY_SEATS parsed", len(seats) >= 20, f"{len(seats)}")
    for city, want_lat, want_lon in [("Tozeur", 33.9197, 8.1339), ("Ghorbel", 34.7484, 10.7369)]:
        lat, lon = seats.get(city, (0.0, 0.0))
        check(f"{city} seat is in Tunisia", lon > 7.4, f"{lat}, {lon}")
        check(f"{city} seat is at the real town",
              abs(lat - want_lat) < 0.01 and abs(lon - want_lon) < 0.01, f"{lat}, {lon}")
    check("no seat falls outside Tunisia's bounds",
          not [c for c, (la, lo) in seats.items() if not in_bbox(la, lo, TUNISIA_BBOX)],
          f"{[c for c, (la, lo) in seats.items() if not in_bbox(la, lo, TUNISIA_BBOX)]}")

    # ── 7. water index ───────────────────────────────────────────────────
    wpath = ROOT / "data" / "water_polys.json"
    if args.no_water or not wpath.is_file():
        print("\n7. water index  SKIPPED (--no-water or no water_polys.json)")
    else:
        print("\n7. water index")
        idx = WaterIndex(json.loads(wpath.read_text(encoding="utf-8"))["elements"])
        check("masks are populated (self.w once collided with the raster width)",
              idx.water_mask.sum() > 0 and idx.land_mask.sum() > 0,
              f"water={idx.water_mask.sum()} land={idx.land_mask.sum()}")
        for lat, lon, wet, desc in [
            (36.8065, 10.1815, False, "Tunis centre"),
            (36.8530, 10.3230, False, "La Marsa"),
            (37.2740, 9.8740, False, "Bizerte"),
            (36.8783, 10.3247, False, "Carthage"),
            (34.7406, 10.7603, False, "Sfax"),
            (33.9197, 8.1339, False, "Tozeur (real town; a chott is land)"),
            (35.2211, 10.0335, False, "ECHATT (on a chott)"),
            (37.1000, 10.6000, True, "Gulf of Tunis"),
            (34.0000, 11.0000, True, "Gulf of Gabes"),
            (33.7000, 8.4000, True, "Chott el Djerid (open salt flat)"),
        ]:
            got = idx.contains(lat, lon) is not None
            check(f"{desc}: {'water' if wet else 'dry'}", got == wet, f"got {'water' if got else 'dry'}")
        check("a chott is classified LAND, not water (saltmarsh reclassified)",
              idx.contains(35.2211, 10.0335) is None)

        rpath = ROOT / "out" / "audit.json"
        if rpath.is_file():
            rep = json.loads(rpath.read_text(encoding="utf-8"))
            flagged = rep.get("in_water", [])
            check("report lists in-water findings", len(flagged) > 0, f"{len(flagged)}")
            check("summary count matches the list", rep["summary"]["in_water"] == len(flagged))
            fp = [f["name"] for f in flagged if idx.contains_exact(f["lat"], f["lon"]) is None]
            check("every in-water finding survives the exact test", not fp, f"false positives: {fp[:5]}")
            # A miss is only possible where the raster/geometry is near an edge,
            # so the reverse direction is bounded to those stops.
            flagged_ids = {(round(f["lat"], 6), round(f["lon"], 6)) for f in flagged}
            suspect = []
            for s in placed:
                if (round(s["lat"], 6), round(s["lon"], 6)) in flagged_ids:
                    continue
                rc = idx._idx(s["lat"], s["lon"])
                if rc is None:
                    continue
                row, col = rc
                if idx.water_mask[row, col]:
                    continue
                r0, r1 = max(0, row - 2), min(idx.nrows, row + 3)
                c0, c1 = max(0, col - 2), min(idx.ncols, col + 3)
                if idx.water_mask[r0:r1, c0:c1].any():
                    suspect.append((s["lat"], s["lon"], s.get("name")))
            missed = [n for la, lo, n in suspect if idx.contains_exact(la, lo) is not None]
            check(f"no wet stop missed near a water edge ({len(suspect)} candidates)",
                  not missed, f"missed: {missed[:5]}")
        else:
            print("     (out/audit.json absent — run the audit to check its findings)")

    # ── 8. canonical modes ───────────────────────────────────────────────
    print("\n8. canonical mode mapping")
    for raw, want in [("rail", "train"), ("louage_red", "louaj"), ("louage_green", "louaj"),
                      ("unknown", "unclassified"), ("rfr", "bus"), ("", "unclassified")]:
        check(f"{raw!r} -> {want}", canonical(raw) == want, f"got {canonical(raw)!r}")

    print("\n" + "=" * 64)
    if FAILS:
        print(f"FAILED {len(FAILS)} of {N}: {FAILS}")
        return 1
    print(f"all {N} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
