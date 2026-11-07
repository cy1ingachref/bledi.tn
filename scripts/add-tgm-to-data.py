#!/usr/bin/env python3
"""Re-add the TGM metro data to apps/web-react/src/data.ts (the prior edit was
lost when the user re-sent the task). The React page body was empty because
data.ts doesn't export TGM. This writes a planned: "metro" array + metro_stations
+ metro_line data so that data.ts exports a TGM constant matching what
MapView.tsx uses: TGM.map((s) => s.pos), TGM.filter(...).forEach(...).

Run from the bledi.tn repo root.
"""
import json
from pathlib import Path

BASE = Path("C:/Users/cy1in/bledi.tn")
CAT = json.loads((BASE / "apps" / "web" / "static" / "transport_catalog.json").read_text(encoding="utf-8"))
METRO = CAT["modes"]["metro"]
STATIONS_BY_ID = {s["id"]: s for s in METRO["stations"]}

metro_stations = []
seen = set()
# collect station ids: from all metro_line stops + all metro station ids
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
            "mode": "metro", "operator": st.get("operator", "Transtu"),
        })

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

data_ts = (BASE / "apps" / "web-react" / "src" / "data.ts").read_text(encoding="utf-8")

if "export const TGM" in data_ts:
    print("TGM already present; leaving data.ts as-is.")
else:
    anchor = "export function byId(id: string): Place {"
    if anchor in data_ts:
        data_ts = data_ts.replace(anchor, f"""export const TGM = {json.dumps(TGM, ensure_ascii=False, indent=2)}

{anchor}""", 1)
    else:
        print("ERROR: anchor not found in data.ts")
        raise SystemExit(1)
    (BASE / "apps" / "web-react" / "src" / "data.ts").write_text(data_ts, encoding="utf-8")
    print("Wrote TGM to data.ts")
    print(f"  metro_stations: {len(metro_stations)}")
    print(f"  metro_lines: {len(metro_lines)}")
