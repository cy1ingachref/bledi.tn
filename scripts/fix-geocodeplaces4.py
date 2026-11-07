#!/usr/bin/env python3
"""Fix the geocodePlaces closing-paren count in apps/web-react/src/data.ts.

Line 56 is `  })));` -> should be `  })))`:
  - `}` closes the object literal body
  - `)` closes the arrow function
  - `)` closes .map(
Currently there is one EXTRA `)`.
"""
from pathlib import Path

BASE = Path("C:/Users/cy1in/bledi.tn")
f = BASE / "apps" / "web-react" / "src" / "data.ts"
ts = f.read_text(encoding="utf-8")

old = """  return (data.results || []).map((r: any) => ({
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

new = """  return (data.results || []).map((r: any) => ({
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
    print("Fixed: removed one extra ')' in geocodePlaces.")
else:
    print("ERROR: old block not found. Current context:")
    i = ts.find("map((r: any)")
    if i != -1:
        print(ts[i - 50:i + 120])
    raise SystemExit(1)
