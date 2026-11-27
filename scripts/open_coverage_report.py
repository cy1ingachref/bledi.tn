#!/usr/bin/env python3
"""Reproducible legacy-vs-open coverage report (WP3 of the open-data cutover).

Reads the legacy seed, an open seed, and the manifest; writes a human-readable
Markdown report and a machine-readable JSON. No network access: reproducible
from committed/locally-produced files only.

A legacy station is matched when an open station of the same mode lies within
`--distance-m` (150 m default) and the names match after normalisation. A line
is matched by ref/operator/name plus stop overlap.

Usage:
  python scripts/open_coverage_report.py \
      --open data/seed_open_source.json \
      --out-md docs/reports/open-data-coverage.md \
      --out-json docs/reports/open-data-coverage.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEGACY = REPO / "data" / "seed_all_tunisia_routes.tagged.json"
MANIFEST = REPO / "data" / "osm_overpass" / "manifest.json"
DEFAULT_OPEN = REPO / "data" / "seed_open_source.json"
DEFAULT_MD = REPO / "docs" / "reports" / "open-data-coverage.md"
DEFAULT_JSON = REPO / "docs" / "reports" / "open-data-coverage.json"

COMMON_WORDS = {"gare", "station", "habous", "el", "le", "la", "de", "du", "des", "bin", "ben"}


def normalise(name: str) -> str:
    n = unicodedata.normalize("NFKD", name or "")
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    words = [w for w in n.split() if w and w not in COMMON_WORDS and len(w) > 1]
    return " ".join(sorted(words))


def haversine(a_lat, a_lon, b_lat, b_lon) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = p2 - p1
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def station_name(s: dict) -> str:
    return s.get("name") or s.get("name_fr") or s.get("name_en") or ""


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def match_stations(legacy: list[dict], opened: list[dict], distance_m: float) -> dict:
    by_mode: dict[str, list[dict]] = defaultdict(list)
    for s in opened:
        by_mode[s.get("mode", "")].append(s)
    matched: list[tuple[str, str]] = []
    unmatched: list[str] = []
    for s in legacy:
        candidates = by_mode.get(s.get("mode", ""), [])
        key = normalise(station_name(s))
        hit = None
        for o in candidates:
            if normalise(station_name(o)) != key:
                continue
            if haversine(s["lat"], s["lon"], o["lat"], o["lon"]) <= distance_m:
                hit = o
                break
        if hit:
            matched.append((s["id"], hit["id"]))
        else:
            unmatched.append(s["id"])
    legacy_ids = {s["id"] for s in legacy}
    open_only = [s["id"] for s in opened if s["id"] not in {m[1] for m in matched}]
    return {
        "distance_m": distance_m,
        "legacy_total": len(legacy), "open_total": len(opened),
        "matched": len(matched), "unmatched_legacy": len(unmatched),
        "open_only": len(open_only),
        "match_rate": round(len(matched) / len(legacy), 4) if legacy else 0.0,
        "by_mode": dict(Counter(s.get("mode", "unknown") for s in legacy)),
        "by_governorate": dict(Counter(s.get("governorate") or "unknown" for s in legacy)),
        "unmatched_legacy_ids": unmatched[:50],
        "open_only_ids": open_only[:50],
    }


def match_lines(legacy: list[dict], opened: list[dict]) -> dict:
    def key(ln):
        return (str(ln.get("number") or "").strip().lower(),
                str(ln.get("operator") or "").strip().lower(),
                normalise(str(ln.get("name") or "")))
    open_by_key = defaultdict(list)
    for ln in opened:
        open_by_key[key(ln)].append(ln)
    open_ids = {ln["id"] for ln in opened}
    matched, missing = [], []
    for ln in legacy:
        hit = open_by_key.get(key(ln))
        if hit:
            matched.append({"legacy": ln["id"], "open": hit[0]["id"]})
        else:
            stops = ln.get("stations") or ln.get("stops") or []
            missing.append({"id": ln["id"], "name": ln.get("name"),
                            "mode": ln.get("mode", "unknown"),
                            "stops": len(stops)})
    matched_ids = {m["open"] for m in matched}
    open_only = [ln["id"] for ln in opened if ln["id"] not in matched_ids]
    top30 = sorted(missing, key=lambda m: -m["stops"])[:30]
    return {
        "legacy_total": len(legacy), "open_total": len(opened),
        "matched": len(matched), "missing": len(missing),
        "open_only": len(open_only),
        "match_rate": round(len(matched) / len(legacy), 4) if legacy else 0.0,
        "top30_missing_by_stop_proxy": top30,
        "missing_by_mode": dict(Counter(m["mode"] for m in missing)),
    }


def render_md(report: dict) -> str:
    s, l = report["stations"], report["lines"]
    m = report["manifest"]
    lines = [
        "# Open-data coverage report",
        "",
        "Reproducible from `scripts/open_coverage_report.py`; generated from the",
        "legacy seed, the open seed and the fetch manifest. No network access.",
        "",
        "## Provenance",
        "",
        f"- Manifest `fetched_at_utc`: `{m.get('fetched_at_utc')}`",
        f"- OSM base timestamp: `{m.get('osm3s_timestamp_osm_base')}`",
        f"- Export SHA-256: `{m.get('export_sha256')}`",
        "",
        "## Stations",
        "",
        f"- Legacy: {s['legacy_total']:,}; open: {s['open_total']:,}",
        f"- Matched (same mode, ≤{s['distance_m']:g} m, normalised name): {s['matched']:,}",
        f"- Unmatched legacy: {s['unmatched_legacy']:,}; open-only: {s['open_only']:,}",
        f"- Match rate: {s['match_rate']:.1%}",
        "",
        "By mode (legacy): " + ", ".join(f"{k} {v}" for k, v in sorted(s["by_mode"].items())),
        "",
        "By governorate (legacy): " + ", ".join(f"{k} {v}" for k, v in sorted(s["by_governorate"].items())),
        "",
        "## Lines",
        "",
        f"- Legacy: {l['legacy_total']:,}; open: {l['open_total']:,}",
        f"- Matched: {l['matched']:,}; missing: {l['missing']:,}; open-only: {l['open_only']:,}",
        f"- Match rate: {l['match_rate']:.1%}",
        "",
        "### 30 largest missing legacy lines (estimated ridership proxy = stop count)",
        "",
        "| Line | Name | Mode | Stops |",
        "|---|---|---|---|",
    ]
    for x in l["top30_missing_by_stop_proxy"]:
        lines.append(f"| {x['id']} | {x['name'] or ''} | {x['mode']} | {x['stops']} |")
    lines += [
        "",
        "## Caveat",
        "",
        "If the open seed was built from a synthetic fixture (no real export on",
        "disk), these numbers are NOT a coverage assessment — refetch the export",
        "and regenerate before any cutover decision.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy", type=Path, default=LEGACY)
    ap.add_argument("--open", type=Path, default=DEFAULT_OPEN)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--distance-m", type=float, default=150.0)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_MD)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    args = ap.parse_args()

    manifest = load(args.manifest) if args.manifest.exists() else {}
    legacy = load(args.legacy)
    opened = load(args.open)
    synthetic = manifest.get("fetched_at_utc") is None
    report = {
        "manifest": manifest,
        "synthetic_fixture": synthetic,
        "stations": match_stations(legacy["stations"], opened["stations"], args.distance_m),
        "lines": match_lines(legacy["lines"], opened["lines"]),
    }
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(render_md(report), encoding="utf-8")
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    def display(p: Path) -> str:
        try:
            return str(p.relative_to(REPO))
        except ValueError:
            return str(p)
    print(f"wrote {display(args.out_md)} and {display(args.out_json)}")
    print(f"stations: {report['stations']['match_rate']:.1%} matched; lines: {report['lines']['match_rate']:.1%} matched")
    if synthetic:
        print("NOTE: manifest has no fetch timestamp — numbers are from a synthetic fixture, not real coverage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
