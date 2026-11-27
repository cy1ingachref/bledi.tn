#!/usr/bin/env python3
"""Fix the geocodePlaces arrow-function syntax error in data.ts.

The block body arrow `((r: any) => ({` returns an object literal; the closing is
`}))`  (object body `}` + paren-around-object `)` + map call `)`).
The file had an extra `)`, i.e. `})));` -> `}))`.

Run from the repo root (bledi.tn).
"""
from pathlib import Path

BASE = Path("C:/Users/cy1in/bledi.tn")
f = BASE / "apps" / "web-react" / "src" / "data.ts"
ts = f.read_text(encoding="utf-8")

old_block = """export async function geocodePlaces(q: string, limit = 8): Promise<Place[]> {
  const data = await api(`/geocode?q=${encodeURIComponent(q)}&limit=${limit}`);
  return (data.results || []).map((r: any) => ({
    id: String(r.name || `${r.lat},${r.lon}`),
    fr: String(r.display_name || r.name || q),
    ar: String(r.display_name || r.name || q),
    en: String(r.display_name || r.name || q),
    pos: [Number(r.lat), Number(r.lon)],
    kind: "place",
    mode: r.type === "city" ? "city" : "unknown",
    operator: "",
  })));
}
"""

new_block = """export async function geocodePlaces(q: string, limit = 8): Promise<Place[]> {
  const data = await api(`/geocode?q=${encodeURIComponent(q)}&limit=${limit}`);
  return (data.results || []).map((r: any) => ({
    id: String(r.name || `${r.lat},${r.lon}`),
    fr: String(r.display_name || r.name || q),
    ar: String(r.display_name || r.name || q),
    en: String(r.display_name || r.name || q),
    pos: [Number(r.lat), Number(r.lon)],
    kind: "place",
    mode: r.type === "city" ? "city" : "unknown",
    operator: "",
  })));
}
"""

if old_block in ts:
    ts = ts.replace(old_block, new_block, 1)
    f.write_text(ts, encoding="utf-8")
    print("Fixed geocodePlaces closing parens.")
else:
    print("ERROR: old_block not found in data.ts")
    # show the region around line 45-58
    lines = ts.splitlines()
    for i in range(44, min(60, len(lines))):
        print(f"{i+1}| {lines[i]}")
    raise SystemExit(1)

print("geocodePlaces arrow now:", "map((r: any) => ({")
print("File size:", len(ts), "bytes")
