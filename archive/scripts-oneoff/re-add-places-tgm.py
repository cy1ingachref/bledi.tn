#!/usr/bin/env python3
"""Re-add TGM + PLACES metro data to apps/web-react/src/data.ts so the React
bottom-sheet search (PlaceInput) and MapView render instead of 404ing.

Covers the Backend-side defect found via Playwright MCP:
  - data.ts exports PLACES (metro station Place objects) for
    PlaceInput.tsx's `import { PLACES, type Place } from "../data"`.
  - data.ts exports TGM (planned: "metro" + metro_stations + metro_line) for
    MapView.tsx's `import { TGM, type Place } from "../data"`.
"""
import json
from pathlib import Path

BASE = Path("C:/Users/cy1in/bledi.tn")
CAT = json.loads((BASE / "apps" / "web" / "static" / "transport_catalog.json").read_text(encoding="utf-8"))
METRO = CAT["modes"]["metro"]
STATIONS_BY_ID = {s["id"]: s for s in METRO["stations"]}

# metro_stations
metro_stations = []
seen = set()
station_ids = set()
for ln in METRO["lines"]:
    for sid in ln.get("stations", []):
        station_ids.add(sid)
for st in METRO["stations"]:
    station_ids.add(st["id"])
for sid in sorted(station_ids):
    st = STATIONS_BY_ID.get(sid)
    if st and sid not in seen:
        seen.add(sid)
        metro_stations.append({
            "id": st["id"], "fr": st["name"], "ar": st.get("name_ar", st["name"]),
            "en": st.get("name_en", st["name"]), "lat": st["lat"], "lon": st["lon"],
            "kind": "station", "mode": "metro", "operator": st.get("operator", "Transtu"),
        })

# metro_line
metro_lines = []
for ln in METRO["lines"]:
    metro_lines.append({
        "id": ln["id"], "number": ln.get("number"),
        "planned": "metro", "stops": ln.get("stations", []),
    })

TGM = {
    "planned": "metro",
    "metro_stations": metro_stations,
    "metro_line": metro_lines,
}

# PLACES = metro stations as Place objects (for PlaceInput)
PLACES = []
for s in METRO["stations"]:
    PLACES.append({
        "id": s["id"], "fr": s.get("name"), "ar": s.get("name_ar", s.get("name")),
        "en": s.get("name_en", s.get("name")),
        "pos": [s["lat"], s["lon"]], "kind": "station",
        "mode": s.get("mode"), "operator": s.get("operator"),
    })

data_ts = (BASE / "apps" / "web-react" / "src" / "data.ts").read_text(encoding="utf-8")

# Attach PLACES before byId()
if "export const PLACES" not in data_ts:
    anchor = "export function byId(id: string): Place {"
    if anchor in data_ts:
        data_ts = data_ts.replace(
            anchor,
            f"""export const PLACES = {json.dumps(PLACES, ensure_ascii=False)}
export const TGM = {json.dumps(TGM, ensure_ascii=False, indent=2)}

{anchor}""",
            1,
        )
        (BASE / "apps" / "web-react" / "src" / "data.ts").write_text(data_ts, encoding="utf-8")
        print("Wrote PLACES + TGM to data.ts")
        print(f"  PLACES: {len(PLACES)}")
        print(f"  TGM.planned: {TGM['planned']}")
        print(f"  TGM.metro_stations: {len(TGM['metro_stations'])}")
        print(f"  TGM.metro_line: {len(TGM['metro_line'])}")
    else:
        print("ERROR: anchor not found in data.ts")
