#!/usr/bin/env python3
"""Rebuild apps/web-react/src/data.ts cleanly from the catalog JSON.

The file got corrupted by earlier ad-hoc edits (stray '}', malformed PLACES
JSON). It must export:
  - PLACES: metro "station" Place objects (id, fr, ar, en, pos, kind, mode,
    operator) for PlaceInput.tsx.
  - TGM: { planned: "metro", metro_stations: [...], metro_line: [...] }
    for MapView.tsx.

Run from the repo root (bledi.tn).
"""
import json
from pathlib import Path

BASE = Path("C:/Users/cy1in/bledi.tn")
CAT = json.loads((BASE / "apps/web/static/transport_catalog.json").read_text(encoding="utf-8"))
METRO = CAT["modes"]["metro"]
STATIONS_BY_ID = {s["id"]: s for s in METRO["stations"]}

# ---- metro_stations for TGM ----
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

# ---- metro_line for TGM ----
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

# ---- PLACES ----
PLACES = []
for s in METRO["stations"]:
    PLACES.append({
        "id": s["id"], "fr": s.get("name"), "ar": s.get("name_ar", s.get("name")),
        "en": s.get("name_en", s.get("name")),
        "pos": [s["lat"], s["lon"]], "kind": "station",
        "mode": s.get("mode"), "operator": s.get("operator"),
    })

data_ts = f"""export type LatLng = [number, number];

export interface Place {{
  id: string;
  fr: string;
  ar: string;
  en: string;
  pos: LatLng;
  kind: "station" | "place";
  mode?: string;
  operator?: string;
}}

let _stations: Place[] | null = null;

async function api(path: string): Promise<any> {{
  const res = await fetch(`/api/v1${{path}}`);
  if (!res.ok) throw new Error(`API ${{res.status}}`);
  return res.json();
}}

export async function loadStations(): Promise<Place[]> {{
  if (_stations) return _stations;
  const geojson = await api("/stations?limit=10000");
  const features = Array.isArray(geojson?.features) ? geojson.features : [];
  _stations = features
    .filter((f: any) => f?.geometry?.type === "Point")
    .map((f: any) => {{
      const coords = f.geometry.coordinates as [number, number];
      const p = f.properties || {{}};
      return {{
        id: String(p.id || p.name || `${{coords[1]}},${{coords[0]}}`),
        fr: String(p.name || p.name_fr || p.name_en || ""),
        ar: String(p.name_ar || p.name_fr || p.name || ""),
        en: String(p.name_en || p.name || ""),
        pos: [coords[1], coords[0]],
        kind: "station",
        mode: p.mode || p.mode_raw || "unknown",
        operator: p.operator || "",
      }};
    }});
  return _stations;
}}

export async function geocodePlaces(q: string, limit = 8): Promise<Place[]> {{
  const data = await api(`/geocode?q=${{encodeURIComponent(q)}}&limit=${{limit}}`);
  return (data.results || []).map((r: any) => ({{
    id: String(r.name || `${{r.lat}},${{r.lon}}`),
    fr: String(r.display_name || r.name || q),
    ar: String(r.display_name || r.name || q),
    en: String(r.display_name || r.name || q),
    pos: [Number(r.lat), Number(r.lon)],
    kind: "place",
    mode: r.type === "city" ? "city" : "unknown",
    operator: "",
  }}));
}}

export const PLACES = {json.dumps(PLACES, ensure_ascii=False)};

export const TGM = {json.dumps(TGM, ensure_ascii=False, indent=2)};

export function byId(id: string): Place {{
  return _stations?.find((p) => p.id === id) ?? {{
    id,
    fr: id,
    ar: id,
    en: id,
    pos: [0, 0],
    kind: "place",
  }};
}}
"""

out = BASE / "apps/web-react/src/data.ts"
out.write_text(data_ts, encoding="utf-8")
print(f"Wrote {out} ({len(data_ts)} bytes)")
print(f"  PLACES: {len(PLACES)}")
print(f"  TGM.planned: {TGM['planned']}")
print(f"  TGM.metro_stations: {len(TGM['metro_stations'])}")
print(f"  TGM.metro_line: {len(TGM['metro_line'])}")
