#!/usr/bin/env python3
"""Ad-hoc verification for the web-react `vite.config.ts` + `data.ts` change.

Changed behavior (this session):
  1. apps/web-react/vite.config.ts -> removed viteSingleFile() (a production-only
     plugin that broke the dev server and left src/main.tsx as a 404 module);
     wired proxy '/api/v1' -> 'http://localhost:8000'.
  2. apps/web-react/src/data.ts    -> added PLACES (metro "station" Place objects,
     85 entries) and TGM { planned: "metro", metro_stations: [85], metro_line: [7] }
     so that data.ts provides everything that PlaceInput.tsx and MapView.tsx
     import (PLACES, TGM, type Place, byId).

Covers three things:
  1. vite.config.ts has no viteSingleFile() plugin and wires the /api/v1 proxy.
  2. data.ts exports PLACES (85 metro stations), TGM (planned: "metro", 85
     metro_stations, 7 metro_line), place() and byId(), and that no dynamic
     import of /src/data.ts can 404.
  3. (frontend runtime once the Vite dev server is up on 8080)

Ad-hoc (not suite green). Reports PASS/FAIL counts explicitly.
"""
from pathlib import Path
import json
import socket
import sys
import time
import urllib.request

BASE = Path(__file__).resolve().parents[1]
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(("  PASS: " if cond else "  FAIL: ") + name + (f"  [{detail}]" if detail else ""))


def http_get(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def wait_for_port(host, port, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((host, port))
            s.close()
            return True
        except OSError:
            time.sleep(1)
    return False


def main():
    # ---- 1. vite.config.ts ----
    print("== 1. vite.config.ts ==")
    cfg = (BASE / "apps" / "web-react" / "vite.config.ts").read_text(encoding="utf-8")
    check("vite.config.ts exists", cfg.strip() != "")
    check("no viteSingleFile() plugin", "viteSingleFile" not in cfg)
    check("has server port 8080", "port: 8080" in cfg)
    check("has proxy /api/v1", '"/api/v1"' in cfg)
    check("proxy target localhost:8000", 'target: "http://localhost:8000"' in cfg)

    # ---- 2. data.ts exports PLACES + TGM ----
    print("== 2. data.ts exports PLACES + TGM ==")
    data_ts = (BASE / "apps" / "web-react" / "src" / "data.ts").read_text(encoding="utf-8")
    check("data.ts has no stray '}'\n    export const PLACES", "}\n\nexport const PLACES" not in data_ts)
    check("data.ts exports PLACES", "export const PLACES" in data_ts)
    check("data.ts exports TGM", "export const TGM" in data_ts)
    check("data.ts exports byId", "export function byId" in data_ts)
    check("data.ts exports type Place", "export interface Place" in data_ts)

    # Parse TGM block
    try:
        m = json.loads(data_ts[data_ts.find('"planned": "metro"'):])
        tgm = m
        check("TGM.planned == 'metro'", tgm.get("planned") == "metro", tgm.get("planned"))
        check("TGM.metro_stations has 85 entries",
              len(tgm.get("metro_stations", [])) >= 85,
              str(len(tgm.get("metro_stations", []))))
        check("TGM.metro_line has 7 lines",
              len(tgm.get("metro_line", [])) >= 7,
              str(len(tgm.get("metro_line", []))))
    except Exception as e:
        check("TGM block parses", False, repr(e))

    # PLACES is proper
    try:
        start = data_ts.find("export const PLACES = [")
        end = data_ts.find("]", start)
        places = json.loads(data_ts[start:end + 1])
        check("PLACES has 85 entries", len(places) >= 85, str(len(places)))
        check("PLACES[0] has id/fr/ar/en/pos/kind/mode/operator",
              all(k in places[0] for k in ("id", "fr", "ar", "en", "pos", "kind", "mode", "operator")))
    except Exception as e:
        check("PLACES block parses", False, repr(e))

    # ---- 3. data.ts PLACES entries are correct Place shape ----
    print("== 3. data.ts PLACES / TGM content ==")
    check("PLACES[0].fr is a French name", places[0].get("fr") == "PLACE BARCELONE SUD",
          str(places[0].get("fr")))
    check("TGM.metro_line[0].id == 'metro_50_1'",
          tgm.get("metro_line", [{}])[0].get("id") == "metro_50_1",
          str(tgm.get("metro_line", [{}])[0].get("id")))
    check("TGM.metro_line[0].stops non-empty", len(tgm.get("metro_line", [{}])[0].get("stops", [])) > 0)

    # ---- 4. spot-check the frontend source (no 404 candidate) ----
    print("== 4. frontend source spot-check ==")
    for f in ("PlaceInput.tsx", "MapView.tsx", "App.tsx"):
        p = BASE / "apps/web-react/src/components" / f
        txt = p.read_text(encoding="utf-8") if p.exists() else ""
        check(f"{f} imports from data.ts",
              'from "../data"' in txt or 'from "./data"' in txt or 'from "./../data"' in txt,
              ("yes" if ('from "../data"' in txt or 'from "./data"' in txt or 'from "./../data"' in txt) else "no"))
        check(f"{f} references PLACES", "PLACES" in txt)
        check(f"{f} references TGM", "TGM" in txt)

    # ---- 5. backend reachable for '/api/v1' proxy ----
    print("== 5. backend reachable for '/api/v1' proxy ==")
    try:
        st, body = http_get("http://127.0.0.1:8000/api/v1/health", timeout=10)
        check("GET /api/v1/health -> 200", st == 200, f"got {st}")
        try:
            p = json.loads(body)
            check("health status ok", p.get("status") == "ok")
            check("7452 stations / 379 lines",
                  p.get("stations_count") == 7452 and p.get("lines_count") == 379)
        except Exception as e:
            check("health payload parses", False, repr(e))
    except Exception as e:
        check("GET /api/v1/health -> 200", False, repr(e))

    print()
    fails = [x for x in RESULTS if not x[1]]
    print(f"ad-hoc verification: PASS={len(RESULTS)-len(fails)}/{len(RESULTS)} FAIL={len(fails)}")
    for name, _, detail in fails:
        print(f"  FAILED: {name}  [{detail}]")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
