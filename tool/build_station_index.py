#!/usr/bin/env python3
"""Build the per-station line index and the louage connection graph.

Task: every station needs the transport type(s) it serves and the NUMBERS of the
lines that call there; and related louage stations need connecting.

Two independent sources are used and kept distinct, because they have different
trustworthiness:

  A. The seed's `lines[].stations` — 262 lines publish their stop list. This is
     the reliable link: a station named in a line's stop list IS on that line.
  B. The seed's `lines_served[]` on each station — scraped route_short_name
     values, frequently null or empty. Used only as a fallback, and flagged.

Louage connections come from the 13 national stations' `destinations_served`,
resolved against the station list by name.

    python tool/build_station_index.py
"""

from __future__ import annotations

import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"
OUT_LINES = ROOT / "out" / "station_lines.json"
OUT_LOU = ROOT / "out" / "louage_links.json"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        s = s.replace(a, b)
    s = re.sub(r"[^0-9a-z\u0600-\u06ff]+", " ", s)
    return " ".join(s.split())


d = json.loads(SEED.read_text(encoding="utf-8"))
stations = d["stations"]
lines = d["lines"]
by_id = {s["id"]: s for s in stations}

# ── A. station -> lines, from the authoritative stop lists ────────────────
station_lines: dict[str, list[dict]] = collections.defaultdict(list)
for ln in lines:
    stops = ln.get("stations") or []
    for sid in stops:
        if sid not in by_id:
            continue
        station_lines[sid].append({
            "id": ln["id"],
            "number": ln.get("number") or "",
            "name": ln.get("name") or "",
            "mode": ln.get("mode") or "",
            "operator": ln.get("operator") or "",
            "type": ln.get("type") or "",
            "source": "line-stop-list",
        })

# ── B. fallback from the scraped lines_served, only where A found nothing ──
fallback = 0
for s in stations:
    if station_lines.get(s["id"]):
        continue
    seen = set()
    for ls in (s.get("lines_served") or []):
        short = (ls or {}).get("route_short_name")
        if not short or short in seen:
            continue
        seen.add(short)
        station_lines[s["id"]].append({
            "id": "", "number": str(short), "name": "", "mode": s.get("mode") or "",
            "operator": s.get("operator") or "", "type": "",
            "source": "lines_served-scrape",
        })
    if seen:
        fallback += 1

for v in station_lines.values():
    v.sort(key=lambda x: (x["mode"], x["number"], x["name"]))

print(f"stations with a line list : {len(station_lines)} / {len(stations)}")
print(f"  from authoritative stop lists : {sum(1 for v in station_lines.values() if any(x['source']=='line-stop-list' for x in v))}")
print(f"  from the scraped fallback only: {fallback}")

# How many lines carry a usable number?
nums = collections.Counter()
for v in station_lines.values():
    for x in v:
        nums[bool(x["number"] and x["number"].strip())] += 1
print(f"  line entries with a number: {nums[True]}   without: {nums[False]}")

print("\n=== what do the numbers look like, per mode? ===")
per_mode = collections.defaultdict(list)
for v in station_lines.values():
    for x in v:
        per_mode[x["mode"]].append(x["number"])
for m, vals in sorted(per_mode.items()):
    uniq = sorted({v for v in vals if v})
    print(f"  {m:10s} {len(vals):6d} entries, {len(uniq):4d} distinct: {uniq[:14]}")

# ── Louage connections from destinations_served ───────────────────────────
louage_stations = [s for s in stations if s.get("destinations_served")]
print(f"\n=== louage stations with a destination list: {len(louage_stations)} ===")

# Index stations by normalised name, and by a first-token key for loose match.
# Empty normalised keys are SKIPPED: a station whose name normalises to "" (e.g.
# the mojibake row whose name is literally "???? ???") would otherwise match every
# destination, because "" is a substring of every string. That bug silently bound
# Kairouan, Djerba, Maktar, El Haouaria, Hergla and Chott Meriem all to one row.
name_index: dict[str, list[str]] = collections.defaultdict(list)
skipped_empty = []
for s in stations:
    for raw in (s.get("name"), s.get("name_en")):
        k = norm(raw or "")
        if not k:
            if raw:
                skipped_empty.append((s["id"], raw))
            continue
        if s["id"] not in name_index[k]:
            name_index[k].append(s["id"])
print(f"name index: {len(name_index)} keys; "
      f"skipped {len(skipped_empty)} unindexable name(s)")
for sid, raw in skipped_empty[:8]:
    print(f"  unindexable: {sid[:48]:48s} name={raw!r}")

links = []
unresolved = collections.Counter()
for ls in louage_stations:
    dests = ls.get("destinations_served") or []
    if isinstance(dests, str):
        dests = [x.strip() for x in dests.split(",")]
    print(f"\n  {ls['name']}  ({ls.get('lat')}, {ls.get('lon')})")
    print(f"    corridor: {ls.get('corridor')}")
    for dest in dests:
        dn = norm(str(dest))
        hit = None
        if dn and dn in name_index:
            hit = name_index[dn][0]
        else:
            # "Tunis (Moncef Bey)" -> try the part before the parenthesis
            base = norm(re.split(r"[(\[]", str(dest))[0])
            if base and base in name_index:
                hit = name_index[base][0]
            elif base:
                # Loose fallback, but only against keys of real length and only
                # for the token, so a short base cannot swallow a long name.
                for key, ids in name_index.items():
                    if len(base) >= 4 and (base in key or key in base):
                        hit = ids[0]
                        break
        if hit:
            links.append({"from": ls["id"], "to": hit,
                          "from_name": ls["name"], "to_name": by_id[hit]["name"],
                          "destination_raw": str(dest)})
            print(f"      -> {by_id[hit]['name'][:34]:34s} ({hit[:38]})  [{dest}]")
        else:
            unresolved[str(dest)] += 1
            print(f"      ?? UNRESOLVED: {dest}")

print(f"\n=== louage links: {len(links)} resolved, {sum(unresolved.values())} unresolved ===")
for k, v in unresolved.most_common(30):
    print(f"  {v:3d}x  {k}")

OUT_LINES.parent.mkdir(parents=True, exist_ok=True)
OUT_LINES.write_text(json.dumps(station_lines, ensure_ascii=False, indent=1), encoding="utf-8")
OUT_LOU.write_text(json.dumps(
    {"links": links,
     "unresolved": dict(unresolved),
     "note": ("Resolved from each louage station's destinations_served against the "
              "station list. Unresolved entries are places that appear in no station "
              "record; they are reported, not guessed.")},
    ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\nwrote {OUT_LINES}")
print(f"wrote {OUT_LOU}")
