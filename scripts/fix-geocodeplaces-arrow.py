#!/usr/bin/env python3
"""Fix the geocodePlaces arrow function syntax error in data.ts.

The arrow function `((r: any) => {` with a block body is invalid when it returns
an object literal. It must be `((r: any) => ({` and the closing must be `})));`
(3 closing parens: map's, arrow's, and object's).

Old broken block (lines 47-56):
  return (data.results || []).map((r: any) => {
    id: String(r.name || `${r.lat},${r.lon}`),
    ... operator: "",
  })));

Fixed:
  return (data.results || []).map((r: any) => ({
    id: String(r.name || `${r.lat},${r.lon}`),
    ... operator: "",
  })));
"""
from pathlib import Path

BASE = Path("C:/Users/cy1in/bledi.tn")
f = BASE / "apps" / "web-react" / "src" / "data.ts"
ts = f.read_text(encoding="utf-8")

old = """export async function geocodePlaces(q: string, limit = 8): Promise<Place[]> {
  const data = await api(`/geocode?q=${encodeURIComponent(q)}&limit=${limit}`);
  return (data.results || []).map((r: any) => {
    id: String(r.name || `${r.lat},${r.lon}`),
    fr: String(r.display_name || r.name || q),
    ar: String(r.display_name || r.name || q),
    en: String(r.display_name || r.name || q),
    pos: [Number(r.lat), Number(r.lon)],
    kind: "place",
    mode: r.type === "city" ? "city" : "unknown",
    operator: "",
  }));
}
"""

new = """export async function geocodePlaces(q: string, limit = 8): Promise<Place[]> {
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

if old in ts:
    ts = ts.replace(old, new, 1)
    f.write_text(ts, encoding="utf-8")
    print("Fixed geocodePlaces arrow function.")
else:
    print("ERROR: old block not found. Current geocodePlaces region:")
    i = ts.find("export async function geocodePlaces")
    j = ts.find("}", i)
    print(ts[i:j][:400])
    raise SystemExit(1)

# sanity: file should parse as JS now (tsx via vite)
print("geocodePlaces now:", "map((r: any) => ({")
