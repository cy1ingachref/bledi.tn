#!/usr/bin/env python3
"""Tag every station and line in data/seed_all_tunisia_routes.json with
`source` and `license_status`, writing a NEW file
data/seed_all_tunisia_routes.tagged.json. The original is left untouched.

source values:
- "tunismapper" for records derived from tunismapper
- "transtu" for records from transtu.com.tn PDF
- "official-public" for official/public sources (SNCFT, OSM where verified, etc.)
- "unknown" where we cannot determine the source

license_status values (pick from the allow-list above):
- "unknown-third-party" — sourced from a third party whose terms we have not verified
- "official-public" — from an official/public source (state rail, public agency, etc.)
- "osm-odbl" — OpenStreetMap-derived, ODbL obligations apply
- "own-field-data" — collected by us in the field
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEED_IN = REPO / "data" / "seed_all_tunisia_routes.json"
SEED_OUT = REPO / "data" / "seed_all_tunisia_routes.tagged.json"

# Tunisia bounding box (approx) for sanity-check reporting
TUNISIA_LAT_MIN = 30.0
TUNISIA_LAT_MAX = 37.5
TUNISIA_LON_MIN = 7.5
TUNISIA_LON_MAX = 12.0

MODE_TO_SOURCE: dict[str, str] = {
    "train": "official-public",     # SNCFT/ONCF
    "metro": "official-public",     # metro tunis / TGM
    "rfr": "official-public",       # RFR state buses
    "bus": "tunismapper",           # bus routes scraped from tunismapper
    "rail": "official-public",      # rail lines (SNCFT/ONCF)
    "tram": "official-public",      # tram (TGM)
    "louage": "unknown",            # louage data is sparse/metadata-only
    "taxi": "unknown",
    "walk": "own-field-data",
}

SOURCE_TO_LICENSE: dict[str, str] = {
    "tunismapper": "unknown-third-party",
    "transtu": "unknown-third-party",
    "official-public": "official-public",
    "osm-odbl": "osm-odbl",
    "own-field-data": "own-field-data",
    "unknown": "unknown-third-party",
}


def classify_line_source(line: dict) -> str:
    # If the line already has a source field, keep it.
    if "source" in line and line["source"]:
        return line["source"]
    mode = line.get("mode", "")
    return MODE_TO_SOURCE.get(mode, "unknown")


def tag_stations(stations: list[dict], lines: list[dict]) -> list[dict]:
    """Tag stations with source + license_status.

    Station source heuristic (majority vote over lines_served):
    - If the station already has a source field, keep it.
    - Otherwise look at the modes of the lines that serve this station
      (from the `lines_served` field, if present). For each distinct mode,
      map to a source via MODE_TO_SOURCE. Use the most frequent non-"unknown"
      source as the station source.
    - If no lines_served or no majority, fall back to the station's own mode
      mapped through MODE_TO_SOURCE (default "unknown").
    """
    # Build a quick lookup: line number -> mode (for stations that reference
    # lines by number in `lines_served`).
    line_mode_by_num: dict[str, str] = {}
    for ln in lines:
        num = ln.get("num") or ln.get("line_num") or ""
        mode = ln.get("mode", "")
        if num and mode:
            line_mode_by_num[str(num)] = mode

    tagged: list[dict] = []
    for s in stations:
        src = s.get("source")
        if not src:
            # Majority vote over lines_served modes.
            served = s.get("lines_served")
            sources: list[str] = []
            if isinstance(served, list):
                for ref in served:
                    mode: str = ""
                    if isinstance(ref, dict):
                        mode = ref.get("mode", "") or ref.get("mode", "")
                    elif isinstance(ref, str):
                        mode = line_mode_by_num.get(ref, "")
                    if mode:
                        sources.append(mode)
            if sources:
                vote: Counter[str] = Counter()
                for mode in sources:
                    src_cand = MODE_TO_SOURCE.get(mode, "unknown")
                    if src_cand != "unknown":
                        vote[src_cand] += 1
                if vote:
                    src = vote.most_common(1)[0][0]
                else:
                    src = "unknown"
            else:
                src = MODE_TO_SOURCE.get(s.get("mode", ""), "unknown")
        lic = SOURCE_TO_LICENSE.get(src, "unknown-third-party")
        tagged.append({**s, "source": src, "license_status": lic})
    return tagged


def tag_lines(lines: list[dict]) -> list[dict]:
    tagged = []
    for ln in lines:
        src = classify_line_source(ln)
        lic = SOURCE_TO_LICENSE.get(src, "unknown-third-party")
        tagged.append({**ln, "source": src, "license_status": lic})
    return tagged


def sanity_report(stations: list[dict], lines: list[dict]) -> str:
    out: list[str] = []
    out.append("## Station source counts")
    out.append("")
    for src, n in Counter(s.get("source") for s in stations).most_common():
        out.append(f"- **{src}**: {n}")
    out.append("")
    out.append("## Line source counts")
    out.append("")
    for src, n in Counter(l.get("source") for l in lines).most_common():
        out.append(f"- **{src}**: {n}")
    out.append("")
    out.append("## Stations without coordinates")
    out.append("")
    no_coord = [s for s in stations if not s.get("lat") or not s.get("lon")]
    out.append(f"{len(no_coord)} stations have no lat/lon.")
    out.append("")
    out.append("## Stations with unknown mode")
    out.append("")
    unknown_mode = [s for s in stations if s.get("mode") in (None, "", "unknown")]
    out.append(f"{len(unknown_mode)} stations have mode unknown/missing.")
    out.append("")
    out.append("## Lines by mode and source")
    out.append("")
    table = [["mode", "count", "sources"]]
    by_mode: dict[str, list[str]] = {}
    for ln in lines:
        m = ln.get("mode", "unknown")
        by_mode.setdefault(m, []).append(ln.get("source", "?"))
    for m, srcs in sorted(by_mode.items()):
        table.append([m, str(len(srcs)), ", ".join(sorted(set(srcs)))])
    out.append("| mode | count | sources |")
    out.append("|------|------:|---------|")
    for row in table[1:]:
        out.append(f"| {row[0]} | {row[1]} | {row[2]} |")
    out.append("")
    out.append("## Notes")
    out.append("")
    out.append(
        "- Most bus routes were derived from Tunismapper and are tagged "
        "`unknown-third-party` until their terms are verified."
    )
    out.append(
        "- Train, metro and RFR lines are tagged `official-public` as the most "
        "likely public-source case; this should be confirmed against the actual "
        "SNCFT/ONCF/RFR publications before relying on it legally."
    )
    out.append(
        "- Louage routes are sparse/metadata-only and tagged `unknown`."
    )
    return "\n".join(out)


def main() -> None:
    data = json.loads(SEED_IN.read_text(encoding="utf-8"))
    stations = data.get("stations", [])
    lines = data.get("lines", [])
    tagged_stations = tag_stations(stations, lines)
    tagged_lines = tag_lines(lines)

    tagged = {**data, "stations": tagged_stations, "lines": tagged_lines}
    SEED_OUT.write_text(json.dumps(tagged, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {SEED_OUT}")
    print(f"Stations: {len(stations)} -> {len(tagged_stations)}")
    print(f"Lines: {len(lines)} -> {len(tagged_lines)}")
    print()
    print("== counts ==")
    print("Station source counts:")
    for src, n in Counter(s.get("source") for s in tagged_stations).most_common():
        print(f"  {src}: {n}")
    print("Line source counts:")
    for src, n in Counter(l.get("source") for l in tagged_lines).most_common():
        print(f"  {src}: {n}")
    print()
    missing_coord = [s for s in tagged_stations if not s.get("lat") or not s.get("lon")]
    unknown_mode = [s for s in tagged_stations if s.get("mode") in (None, "", "unknown")]
    print(f"Stations without coordinates: {len(missing_coord)}")
    print(f"Stations with unknown mode: {len(unknown_mode)}")


if __name__ == "__main__":
    main()
