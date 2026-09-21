#!/usr/bin/env python3
"""Audit provenance of scraped web data in data/*.json.

Walks every .json file under data/ and, for each, counts:
- top-level list items or dict entries grouped by a "source" or "scraper" field
- items with no source field at all
- the file's rough schema (top-level type, top-level keys)
Writes a markdown summary to docs/provenance.md (overwrites each run).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
OUT = DOCS_DIR / "provenance.md"


def _first_text(v):
    if v is None:
        return "(missing)"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, dict):
        if "url" in v:
            return v["url"]
        if "name" in v:
            return v["name"]
        if "source" in v:
            return v["source"]
        keys = list(v.keys())
        return "{...}" + (f"({','.join(keys[:3])})" if keys else "")
    if isinstance(v, list):
        if not v:
            return "[]"
        return f"[{_first_text(v[0])}...]"
    s = str(v).strip()
    if len(s) > 90:
        s = s[:87] + "..."
    return s


def scan_json(path: Path) -> dict:
    """Return a provenance summary dict for one JSON file."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {
            "path": path.name,
            "error": f"cannot read: {e}",
            "top_type": None,
            "top_keys": [],
            "item_count": None,
            "by_source": {},
            "missing_source": None,
            "sample_missing_ids": [],
        }

    try:
        data = json.loads(raw)
    except Exception as e:
        return {
            "path": path.name,
            "error": f"invalid JSON: {e}",
            "top_type": None,
            "top_keys": [],
            "item_count": None,
            "by_source": {},
            "missing_source": None,
            "sample_missing_ids": [],
        }

    info: dict = {
        "path": path.name,
        "error": None,
        "top_type": type(data).__name__,
        "top_keys": list(data.keys())[:12] if isinstance(data, dict) else [],
        "item_count": None,
        "by_source": {},
        "missing_source": None,
        "sample_missing_ids": [],
        "notes": [],
    }

    if isinstance(data, dict):
        # Heuristic: if there's a "stations" or "lines" key, treat those as
        # the collections to audit. Otherwise fall back to top-level values.
        collections = {}
        for key in ("stations", "lines", "routes", "data", "results", "items"):
            if key in data and isinstance(data[key], list):
                collections[key] = data[key]
        if not collections:
            # maybe the dict itself is a single record
            collections = {"(top dict)": [data]}
        info["top_keys"] = list(data.keys())
        info["item_count"] = sum(len(v) for v in collections.values())
        by_src: Counter[str] = Counter()
        missing = 0
        missing_ids: list[str] = []
        for label, lst in collections.items():
            for item in lst:
                if not isinstance(item, dict):
                    continue
                src = item.get("source") or item.get("scraper") or item.get("provider")
                if src:
                    # Normalize: take the first 60 chars of the source string
                    s = str(src).strip()
                    by_src[s[:60]] += 1
                else:
                    missing += 1
                    mid = (item.get("id") or item.get("name") or item.get("station") or
                           item.get("line") or item.get("route_id") or "?")
                    if len(missing_ids) < 5:
                        missing_ids.append(str(mid))
        info["by_source"] = dict(by_src)
        info["missing_source"] = missing
        info["sample_missing_ids"] = missing_ids
    elif isinstance(data, list):
        info["item_count"] = len(data)
        by_src: Counter[str] = Counter()
        missing = 0
        missing_ids: list[str] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            src = item.get("source") or item.get("scraper") or item.get("provider")
            if src:
                s = str(src).strip()
                by_src[s[:60]] += 1
            else:
                missing += 1
                mid = (item.get("id") or item.get("name") or item.get("station") or
                       item.get("line") or item.get("route_id") or "?")
                if len(missing_ids) < 5:
                    missing_ids.append(str(mid))
        info["by_source"] = dict(by_src)
        info["missing_source"] = missing
        info["sample_missing_ids"] = missing_ids
    else:
        info["notes"].append(f"Unexpected JSON root type: {type(data).__name__}")

    return info


def build_markdown(summaries: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# Provenance report — scraped web data under data/")
    lines.append("")
    lines.append(
        "Auto-generated by `scripts/provenance_report.py`. "
        "Counts records by their `source` / `scraper` / `provider` field and "
        "flags records with no such field."
    )
    lines.append("")
    lines.append(f"Generated: {__import__('datetime').datetime.now().isoformat()}")
    lines.append("")
    lines.append("## Files scanned")
    lines.append("")
    lines.append(f"{len(summaries)} JSON file(s) under `data/`.")
    lines.append("")

    for info in summaries:
        lines.append(f"### {info['path']}")
        lines.append("")
        if info["error"]:
            lines.append(f"- **Error:** {info['error']}")
            lines.append("")
            continue

        lines.append(f"- **Root type:** {info['top_type']}")
        if info["top_keys"]:
            lines.append(f"- **Top-level keys:** {', '.join(info['top_keys'])}")
        lines.append(f"- **Item count:** {info['item_count']}")
        lines.append("")

        if info["by_source"]:
            lines.append("| source field value | count |")
            lines.append("|-------------------|------:|")
            for src, n in sorted(info["by_source"].items(), key=lambda x: -x[1]):
                src_disp = src if len(src) <= 90 else src[:87] + "..."
                lines.append(f"| `{src_disp}` | {n} |")
            lines.append("")

        if info["missing_source"] is not None:
            lines.append(f"- **Records with no source field:** {info['missing_source']}")
            if info["sample_missing_ids"]:
                lines.append("")
                lines.append("  Example missing-source ids (first 5):")
                for mid in info["sample_missing_ids"]:
                    lines.append(f"  - `{mid}`")
                lines.append("")

        if info["notes"]:
            for n in info["notes"]:
                lines.append(f"- {n}")
            lines.append("")

    # Summary table across all files
    lines.append("## Combined summary")
    lines.append("")
    lines.append("| file | root type | items | distinct sources | missing-source records |")
    lines.append("|-----|-----------|------:|-----------------:|----------------------:|")
    for info in summaries:
        if info["error"]:
            continue
        src_count = len(info["by_source"])
        src_cnt_str = str(src_count)
        miss = info["missing_source"] or 0
        items = info["item_count"] or 0
        root = info["top_type"] or "?"
        lines.append(
            f"| {info['path']} | {root} | {items} | {src_count} | {miss} |"
        )
    lines.append("")

    # Overall missing-source totals
    total_missing = sum((info["missing_source"] or 0) for info in summaries if not info["error"])
    total_items = sum((info["item_count"] or 0) for info in summaries if not info["error"])
    lines.append(f"Total records with a source field: {total_items - total_missing}.")
    lines.append(f"Total records with **no** source field: {total_missing}.")
    lines.append("")

    # Observations
    lines.append("## Observations")
    lines.append("")
    obs: list[str] = []
    seed = next((i for i in summaries if i["path"] == "seed_all_tunisia_routes.json"), None)
    if seed:
        lines_by_src = seed["by_source"]
        tunismapper_lines = lines_by_src.get("tunismapper", 0)
        tunismapper_variant = sum(
            n for k, n in lines_by_src.items() if k and "tunismapper" in k.lower()
        )
        transtu = sum(
            n for k, n in lines_by_src.items() if k and "transtu" in k.lower()
        )
        obs.append(
            f"- In `seed_all_tunisia_routes.json`, {tunismapper_variant} of "
            f"{seed['item_count']} lines are sourced from tunismapper (including "
            f"variants such as `tunismapper.com ...`), and {transtu} from transtu PDFs."
        )
        if seed["missing_source"] is not None and seed["missing_source"] > 0:
            obs.append(
                f"- In `seed_all_tunisia_routes.json`, {seed['missing_source']} records "
                f"have no source field. These are mostly stations (the seed carries a "
                f"`source` field on lines but not on stations)."
            )
    obs.append(
        "- No file in `data/` currently declares its own overall provenance or license "
        "at the file level; provenance lives only in per-record fields where present."
    )
    for o in obs:
        lines.append(o)
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    json_files = sorted(DATA_DIR.rglob("*.json"))
    if not json_files:
        print("No JSON files found under data/", file=sys.stderr)
        sys.exit(1)

    summaries = []
    for path in json_files:
        info = scan_json(path)
        summaries.append(info)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_markdown(summaries), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Scanned {len(summaries)} JSON files:")
    for info in summaries:
        err = info["error"] or ""
        print(f"  - {info['path']}: {info['top_type']} "
              f"({info['item_count']} items, {len(info['by_source'])} source values"
              f"{', ' + err if err else ''})")


if __name__ == "__main__":
    main()
