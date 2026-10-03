#!/usr/bin/env python3
"""Verify the export readers and the station import, end to end.

Lives in the repo rather than a temp directory on purpose. Every other check
written for this data has been a throwaway script deleted after its run, which
left no artefact and made "verified" indistinguishable from "not re-checked
since". This one is committed, so it can be re-run by anyone at any time:

    python tool/verify_import.py                     # summary only
    python tool/verify_import.py --api http://localhost:8000
    python tool/verify_import.py --skip-backend

What it asserts, against the source export rather than any cached artefact:

  1. encoding    — cp1252 files decode; the utf-16 misread that silently
                   dropped ~900 stations cannot come back
  2. read_geolocated — per-operator record counts, all coordinates inside
                   Tunisia, one record per physical place
  3. determinism — two runs produce an identical record set
  4. import      — idempotent, no duplicate ids, no invented line membership,
                   and every geolocated place is either placed or deduplicated
  5. Bizerte     — publishes station names but no coordinates anywhere, which
                   is why ~381 of its 426 stops cannot be mapped

Requires openpyxl (for the .xlsx sources) and the portal export directory.
Writes nothing outside a temp dir it removes itself.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from osm_common import norm  # noqa: E402
from parse_official_data import sniff, to_float  # noqa: E402

# Expected per-operator counts from the 2026-10-03 export. A change here means
# the portal data moved, not that the parser broke — re-read before "fixing".
EXPECTED = {
    "TRANSTU": 2183, "SORETRAS": 795, "SRTGN": 515, "SNCFT": 222,
    "SNTRI": 215, "SRTJ": 180, "SRTM": 119, "TGM": 79, "RFR": 1,
}
EXPECTED_TOTAL = 4309
BIZERTE_DIRS = (
    "La liste des stations des bus de la SRT Bizerte",
    "Les horaires des voyages des bus de la SRT Bizerte",
    "Le calendrier Hebdomadaire des voyages de la SRT Bizerte",
    "Les lignes d'exploitation de la SRTB",
)
COORD = re.compile(r"\d{1,3}[.,]\d{4,}")
# TRANSTU marks direction on stop names; collapsing those is the point of
# read_geolocated, so any surviving pair here is a bug.
DIRECTION = re.compile(r"[-–—]\s*[arr]{1,2}\s*[-–—]\s*$|\s+[arr]{1,2}\s*$", re.I)


class Checks:
    def __init__(self) -> None:
        self.failed: list[str] = []
        self.skipped: list[str] = []

    def __call__(self, label: str, ok: bool, detail: object = "") -> None:
        print(f"  {'OK  ' if ok else 'FAIL'} {label}{(' — ' + str(detail)) if detail else ''}")
        if not ok:
            self.failed.append(label)

    def report(self) -> int:
        print()
        for reason in self.skipped:
            print(f"SKIPPED: {reason}")
        if self.failed:
            print(f"FAILED {len(self.failed)}: {self.failed}")
            return 1
        if self.skipped:
            print(f"{len(self.skipped)} section(s) skipped — not a clean run")
            return 1
        print("all checks passed")
        return 0


def haversine(a: float, b: float, c: float, d: float) -> float:
    p1, p2 = math.radians(a), math.radians(c)
    x = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(math.sqrt(x))


def digest(records: list[dict]) -> str:
    rows = sorted((r["operator"], r["name"], round(r["lat"], 6), round(r["lon"], 6))
                  for r in records)
    return hashlib.sha256(
        json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def run(script: str, *args: str, timeout: int = 550) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HERE / script), *args],
                          capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, "PYTHONPATH": str(HERE)})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=r"C:\Users\cy1in\Downloads\transport",
                    help="root of the portal export")
    ap.add_argument("--seed", default=None,
                    help="defaults to the seed above src/mobile in this repo")
    ap.add_argument("--workbook", default=r"C:\Users\cy1in\Downloads\bizerte_mateur_transport.xlsx",
                    help="the Google Places Bizerte/Mateur workbook, if present")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--skip-backend", action="store_true")
    args = ap.parse_args()

    src = Path(args.src)
    seed_default = next(
        (p / "data" / "seed_all_tunisia_routes.tagged.json"
         for p in HERE.parents if (p / "data").is_dir()),
        None,
    )
    if args.seed is None:
        args.seed = str(seed_default) if seed_default else ""
    check = Checks()
    if not src.is_dir():
        print(f"source export not found: {src}")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="bledi-verify-"))
    try:
        # 1. Encoding ---------------------------------------------------------
        print("encoding")
        biz = next((src / BIZERTE_DIRS[0]).glob("*.csv"))
        text, delim = sniff(biz)
        check("cp1252 file decodes readably",
              len(text.splitlines()) > 400 and "janv" in text)
        check("no mojibake",
              not any(0xE000 <= ord(c) <= 0xF8FF or 0x50000 <= ord(c) <= 0x10FFFD
                      for c in text[:800]))
        check("426 Bizerte station names recovered",
              len(text.splitlines()) - 1 == 426, len(text.splitlines()) - 1)
        check("';' detected as the delimiter", delim == ";", repr(delim))
        check("to_float handles a dot decimal", to_float("36.8097") == 36.8097)
        check("to_float handles a comma decimal", to_float("36,8097") == 36.8097)
        check("to_float rejects a name", to_float("BAB SAADOUN") is None)

        # 2. read_geolocated --------------------------------------------------
        print("read_geolocated")
        geo_path = tmp / "geo.json"
        proc = run("read_geolocated.py", "--src", str(src), "--out", str(geo_path))
        check("exits 0", proc.returncode == 0, proc.stderr.strip()[-80:] if proc.returncode else "")
        if proc.returncode != 0:
            return check.report()
        geo = json.loads(geo_path.read_text(encoding="utf-8"))

        check(f"{EXPECTED_TOTAL} distinct places", len(geo) == EXPECTED_TOTAL, len(geo))
        for op, want in EXPECTED.items():
            n = sum(1 for r in geo if r["operator"] == op)
            check(f"  {op:9s} = {want}", n == want, n)
        check("every record has a name", all(r["name"] for r in geo))
        check("all coordinates inside Tunisia",
              all(30.0 <= r["lat"] <= 38.0 and 6.5 <= r["lon"] <= 12.5 for r in geo))
        places = collections.Counter(
            (r["operator"], norm(DIRECTION.sub("", r["name"]))) for r in geo)
        check("one record per place per operator", max(places.values()) == 1,
              f"a place appears {max(places.values())}x")

        print("determinism")
        again = tmp / "geo2.json"
        run("read_geolocated.py", "--src", str(src), "--out", str(again))
        geo_b = json.loads(again.read_text(encoding="utf-8"))
        check("two runs agree", digest(geo) == digest(geo_b), digest(geo))

        # 3. Import -----------------------------------------------------------
        print("import")
        seed_path = Path(args.seed)
        check("seed found", seed_path.is_file(), seed_path)
        if seed_path.is_file():
            committed = json.loads(seed_path.read_text(encoding="utf-8"))
            official = [s for s in committed["stations"]
                        if s.get("source") == "official-open-data"]
            check(f"seed holds {len(committed['stations'])} stations",
                  len(committed["stations"]) > 4000, len(committed["stations"]))
            check("no duplicate ids",
                  len({s["id"] for s in committed["stations"]})
                  == len(committed["stations"]))
            check("official records carry name and coordinates",
                  all(s.get("name") and s.get("lat") and s.get("lon")
                      for s in official), len(official))
            check("no invented line membership on imported stops",
                  all(not s.get("lines_served") for s in official))

            pre = tmp / "seed.json"
            pre.write_text(json.dumps(committed, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            out = tmp / "reimport.json"
            proc = run("import_official_stops.py", "--seed", str(pre),
                       "--official", str(geo_path), "--out", str(out))
            check("re-import exits 0", proc.returncode == 0,
                  proc.stderr.strip()[-80:] if proc.returncode else "")
            if proc.returncode == 0:
                again_seed = json.loads(out.read_text(encoding="utf-8"))
                check("idempotent — re-import adds nothing",
                      len(again_seed["stations"]) == len(committed["stations"]),
                      f"{len(committed['stations'])} -> {len(again_seed['stations'])}")

            # Every geolocated place is either present by name or sits within
            # the importer's 120 m tolerance of an existing station.
            cell = 120 / 111320
            grid = collections.defaultdict(list)
            for s in committed["stations"]:
                grid[(int(s["lat"] // cell), int(s["lon"] // cell))].append(s)

            def near(la: float, lo: float) -> float:
                ky, kx = int(la // cell), int(lo // cell)
                best = math.inf
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        for c in grid.get((ky + dy, kx + dx), []):
                            best = min(best, haversine(la, lo, c["lat"], c["lon"]))
                return best

            names = {norm(s["name"]) for s in committed["stations"]}
            gaps = [g for g in geo
                    if norm(g["name"]) not in names and near(g["lat"], g["lon"]) > 120]
            check("every geolocated place placed or deduplicated", not gaps,
                  f"{len(gaps)} genuine gaps")

        # 4. Bizerte ----------------------------------------------------------
        print("Bizerte")
        scanned = 0
        with_coords: list[str] = []
        for d in BIZERTE_DIRS:
            for f in (src / d).glob("*"):
                if f.suffix.lower() == ".xlsx":
                    try:
                        zf = zipfile.ZipFile(f)
                        # xl/ only: docProps/app.xml carries "12.0000" (the
                        # Excel version), which matches a coordinate pattern.
                        blob = "".join(
                            zf.read(n).decode("utf-8", "replace")
                            for n in zf.namelist()
                            if n.startswith("xl/") and n.endswith(".xml"))
                    except Exception:  # noqa: BLE001
                        continue
                elif f.suffix.lower() in {".csv", ".txt"}:
                    blob, _ = sniff(f)
                else:
                    continue
                scanned += 1
                if COORD.search(blob):
                    with_coords.append(f"{d}/{f.name}")
        check(f"no coordinates in any of {scanned} Bizerte files", not with_coords,
              with_coords[:2])
        check("all four Bizerte datasets were readable", scanned >= 6, scanned)
        if seed_path.is_file():
            area = [s for s in committed["stations"]
                    if 36.85 < s["lat"] < 37.45 and 9.55 < s["lon"] < 10.15]
            check("Bizerte area has stations", len(area) > 200, len(area))
            halts = {s["name"] for s in area if s["mode"] == "train"}
            check("SNCFT halts present", {"Ain Ghelal", "Mateur", "Tinja"} <= halts,
                  sorted(halts)[:8])

        # 5. Google Places workbook -------------------------------------------
        print("google places workbook")
        wb_path = Path(args.workbook) if args.workbook else None
        if wb_path is None or not wb_path.is_file():
            print(f"  (skipped: workbook not found at {wb_path})")
        else:
            gp_path = tmp / "gp.json"
            proc = run("parse_google_places.py", "--xlsx", str(wb_path),
                       "--out", str(gp_path))
            check("parse exits 0", proc.returncode == 0,
                  proc.stderr.strip()[-80:] if proc.returncode else "")
            if proc.returncode == 0:
                gp = json.loads(gp_path.read_text(encoding="utf-8"))
                check("27 records read", len(gp) == 27, len(gp))
                modes = collections.Counter(r["mode"] for r in gp)
                check("  11 bus", modes.get("bus", 0) == 11, modes.get("bus", 0))
                check("  7 louage", modes.get("louage", 0) == 7, modes.get("louage", 0))
                check("  7 taxi", modes.get("taxi", 0) == 7, modes.get("taxi", 0))
                check("  2 train", modes.get("train", 0) == 2, modes.get("train", 0))
                check("every record has a Place ID",
                      all(r["place_id"] for r in gp))
                check("every record keeps its raw Type wording",
                      all(r["type_raw"] for r in gp))
                check("no record left unclassified",
                      not [r for r in gp if r["mode"] == "unknown"])
                check("all coordinates inside Tunisia",
                      all(30.0 <= r["lat"] <= 38.0 and 6.5 <= r["lon"] <= 12.5
                          for r in gp))
                sheets = collections.Counter(r["source_sheet"] for r in gp)
                check("  19 Bizerte, 6 Mateur, 2 Ras Jebel",
                      (sheets.get("Bizerte"), sheets.get("Mateur"),
                       sheets.get("Ras Jebel")) == (19, 6, 2), dict(sheets))

                # Import must keep co-located siblings: the Zarzouna cluster
                # has four distinct listings within 150 m of each other, and an
                # earlier version of the importer dropped all but the first.
                seed_now = json.loads(seed_path.read_text(encoding="utf-8"))
                in_seed = [s for s in seed_now["stations"]
                           if s.get("source") == "google-places-workbook"]
                check("26 google records already in the seed", len(in_seed) == 26,
                      len(in_seed))
                check("  each keeps its Place ID",
                      all(s.get("place_id") for s in in_seed))
                check("  each keeps its raw Type", all(s.get("type_raw") for s in in_seed))
                check("  all 27 workbook rows accounted for "
                      "(26 imported, Gare SNCFT Mateur deduplicated)",
                      len(in_seed) + 1 == len(gp), f"{len(in_seed)}+1 vs {len(gp)}")
                modes_in = collections.Counter(s["mode"] for s in in_seed)
                check("  louage and taxi both present on the map",
                      modes_in.get("louage", 0) >= 7 and modes_in.get("taxi", 0) >= 7,
                      dict(modes_in))

                # To exercise the co-located-sibling fix, strip them out first:
                # importing into a seed that already holds them is a no-op and
                # would pass even if the dedup bug had returned.
                before = {"stations": [s for s in seed_now["stations"]
                                       if s.get("source") != "google-places-workbook"],
                          "metadata": dict(seed_now.get("metadata", {}))}
                n_before = len(before["stations"])
                staged = tmp / "seed_gp.json"
                staged.write_text(json.dumps(before, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
                added_out = tmp / "added_gp.json"
                proc = run("import_official_stops.py", "--seed", str(staged),
                           "--official", str(gp_path), "--out", str(added_out))
                check("import exits 0", proc.returncode == 0,
                      proc.stderr.strip()[-80:] if proc.returncode else "")
                if proc.returncode == 0:
                    after = json.loads(added_out.read_text(encoding="utf-8"))
                    added = after["stations"][n_before:]
                    check("26 of 27 added (Gare SNCFT Mateur is 25 m from ours)",
                          len(added) == 26, len(added))
                    check("co-located siblings all survive",
                          len({norm(r["name"]) for r in added}) == len(added),
                          f"{len({norm(r['name']) for r in added})} distinct")
                    check("Place IDs preserved through the import",
                          all(r.get("place_id") for r in added))
                    check("raw Type preserved through the import",
                          all(r.get("type_raw") for r in added))
                    check("source recorded as google-places-workbook",
                          all(r["source"] == "google-places-workbook" for r in added))
                    check("both louage and taxi imported",
                          {r["mode"] for r in added} >= {"louage", "taxi"},
                          sorted({r["mode"] for r in added}))
                    check("existing stations untouched",
                          all(before["stations"][i] == after["stations"][i]
                              for i in range(n_before)))
                    check("re-import reproduces the seed's own google set",
                          {norm(r["name"]) for r in added}
                          == {norm(s["name"]) for s in in_seed},
                          f"{len(added)} vs {len(in_seed)}")
                    # Idempotent.
                    again_gp = tmp / "again_gp.json"
                    run("import_official_stops.py", "--seed", str(added_out),
                        "--official", str(gp_path), "--out", str(again_gp))
                    pass2 = json.loads(again_gp.read_text(encoding="utf-8"))["stations"]
                    check("google import is idempotent",
                          len(pass2) == len(after["stations"]),
                          f"{len(after['stations'])} -> {len(pass2)}")

        # 6. Unknown-mode resolution -------------------------------------------
        print("unknown mode resolution")
        if not seed_path.is_file():
            print("  (skipped: no seed)")
        else:
            seed_now = json.loads(seed_path.read_text(encoding="utf-8"))
            n_train = sum(1 for s in seed_now["stations"] if s["mode"] == "train")
            n_unknown = sum(1 for s in seed_now["stations"] if s["mode"] == "unknown")
            resolved = [s for s in seed_now["stations"]
                        if s.get("mode_source") == "official-sncft-rail-export"]
            check("54 stations classified from the SNCFT rail export",
                  len(resolved) == 54, len(resolved))
            check("unknown reduced 130 -> 76", n_unknown == 76, n_unknown)
            check("every resolved record cites its evidence",
                  all(s.get("mode_evidence") for s in resolved))
            check("every resolved record is now train",
                  all(s["mode"] == "train" for s in resolved))
            check("Mateur Sud resolved (SNCFT lists it as a rail halt)",
                  any(s["name"] == "Mateur Sud" for s in resolved))

            # Idempotent: a second resolution pass must change nothing.
            res_out = tmp / "resolved.json"
            proc = run("resolve_unknown_modes.py", "--seed", str(seed_path),
                       "--out", str(res_out), "--src", str(src))
            check("resolve exits 0", proc.returncode == 0,
                  proc.stderr.strip()[-80:] if proc.returncode else "")
            if proc.returncode == 0:
                again = json.loads(res_out.read_text(encoding="utf-8"))
                check("a second pass resolves nothing further",
                      not [s for s in again["stations"]
                           if s.get("mode_source") == "official-sncft-rail-export"
                           and norm(s["name"]) not in {norm(r["name"]) for r in resolved}],
                      "no new records classified")

        # 7. Backend ----------------------------------------------------------
        if not args.skip_backend:
            print("backend")
            try:
                with urllib.request.urlopen(f"{args.api}/api/v1/health",
                                            timeout=15) as r:
                    health = json.load(r)
                check("health ok", health.get("status") == "ok",
                      f"{health['stations_count']} stations")
                with urllib.request.urlopen(f"{args.api}/api/v1/stations",
                                        timeout=180) as r:
                    feats = json.load(r)["features"]
                check("no station missing mode or city",
                      not [f for f in feats if not f["properties"].get("mode")
                           or not f["properties"].get("city")])
                check("all coordinates inside Tunisia",
                      all(30.0 <= f["geometry"]["coordinates"][1] <= 37.7
                          and 6.5 <= f["geometry"]["coordinates"][0] <= 12.5
                          for f in feats), len(feats))
                with urllib.request.urlopen(f"{args.api}/api/v1/cities",
                                        timeout=60) as r:
                    cities = json.load(r)
                check("city totals reconcile",
                      sum(c["station_count"] for c in cities["cities"]) == len(feats))
            except Exception as exc:  # noqa: BLE001
                # A silent skip reads as a pass. Name the section and fail the
                # run unless the caller opted out with --skip-backend.
                check("backend reachable", False, f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return check.report()


if __name__ == "__main__":
    sys.exit(main())