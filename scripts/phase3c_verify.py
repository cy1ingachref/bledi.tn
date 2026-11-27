#!/usr/bin/env python3
"""Phase 3C verification: Python oracle (transit :8000) vs Rust routing (:8081/:18081).

Runs 5 sample routes, records fastest/cheapest legs/time/fare from each
service that is actually reachable, compares when both run, and writes
phase3c_routes.json under docs/reports/data/. Never fabricates:
unreachable services are recorded as unavailable with the real error.
"""
from __future__ import annotations
import json, os, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_BASE = os.environ.get("PY_TRANSIT_URL", "http://127.0.0.1:8000").rstrip("/")
RUST_PORTS = [int(os.environ.get("RUST_ROUTING_PORT", "18081")), 8081]
TIMEOUT = 60

# Fallback city centres (lat, lon) used only if /geocode fails.
CITIES = {
    "Tunis Centre": (36.8000, 10.1800),
    "Tunis": (36.8000, 10.1800),
    "Sousse": (35.8250, 10.6400),
    "Hammamet": (36.4000, 10.1000),
    "Bizerte": (37.2710, 9.8710),
    "Monastir": (35.7770, 10.8280),
    "Tunis local S": (36.7360, 10.1830),
}
ROUTES = [
    ("Tunis Centre->Sousse", "Tunis Centre", "Sousse"),
    ("Tunis->Hammamet", "Tunis", "Hammamet"),
    ("Bizerte->Tunis", "Bizerte", "Tunis"),
    ("Sousse->Monastir", "Sousse", "Monastir"),
    ("Tunis local (Centre->S)", "Tunis Centre", "Tunis local S"),
]

def http_json(url, timeout=TIMEOUT):
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, json.loads(body), round(time.time() - t0, 3), None
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read().decode("utf-8", "replace"))
        except Exception: body = None
        return e.code, body, round(time.time() - t0, 3), f"HTTPError {e.code}"
    except Exception as e:
        return None, None, round(time.time() - t0, 3), f"{type(e).__name__}: {e}"

def geocode(name):
    code, data, _, err = http_json(f"{PY_BASE}/api/v1/geocode?q={urllib.request.quote(name)}&limit=1", timeout=15)
    if code == 200 and data and data.get("results"):
        r = data["results"][0]
        return (float(r["lat"]), float(r["lon"])), "geocode"
    return CITIES[name], f"fallback({err or code})"

def py_route(start, end, objective):
    q = (f"start_lat={start[0]}&start_lon={start[1]}&end_lat={end[0]}&end_lon={end[1]}"
         f"&objective={objective}&max_itineraries=1")
    code, data, dt, err = http_json(f"{PY_BASE}/api/v1/route/plan?{q}")
    it = (data.get("itineraries") or [None])[0] if data else None
    return {"status": code, "ms": dt, "error": err,
            "duration_min": it.get("duration_min") if it else None,
            "fare_dinars": it.get("fare_estimate_dinars") if it else None,
            "transfers": it.get("transfers") if it else None,
            "modes_used": it.get("modes_used") if it else None,
            "legs": len(it.get("legs") or []) if it else None,
            "label": it.get("label") if it else None}

def rust_base():
    for port in RUST_PORTS:
        code, data, _, _ = http_json(f"http://127.0.0.1:{port}/health", timeout=5)
        # Vite on 8081 returns HTML -> json parse fails -> data None -> skip.
        if code == 200 and isinstance(data, dict) and data.get("status") == "ok":
            return f"http://127.0.0.1:{port}", data
    return None, None

def rust_route(base, start, end, objective):
    q = (f"from_lat={start[0]}&from_lon={start[1]}&to_lat={end[0]}&to_lon={end[1]}"
         f"&objective={objective}")
    code, data, dt, err = http_json(f"{base}/route?{q}")
    if not isinstance(data, dict):
        return {"status": code, "ms": dt, "error": err or "non-json"}
    legs = data.get("legs") or []
    dur = data.get("duration_min") or data.get("total_time_min") or data.get("time_min")
    if dur is None and data.get("duration_s"):
        dur = round(data["duration_s"] / 60.0, 1)
    return {"status": code, "ms": dt, "error": err,
            "duration_min": dur,
            "fare_dinars": data.get("fare_dinars") or data.get("fare") or data.get("total_fare"),
            "transfers": data.get("transfers"),
            "legs": len(legs) if legs else None,
            "raw_keys": sorted(data.keys())}

def try_start_rust():
    """Best-effort: launch a prebuilt debug/release binary on 18081."""
    cands = list((ROOT / "services/routing/target").glob("*/bledi-routing*")) + \
            list((ROOT / "services/routing/target").glob("*/bledi_routing*"))
    for exe in cands:
        if exe.is_file():
            try:
                env = dict(os.environ, PORT="18081", BLEDI_DATA_DIR=str(ROOT / "data"))
                subprocess.Popen([str(exe)], env=env, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                for _ in range(30):
                    time.sleep(1)
                    base, _ = rust_base()
                    if base: return base
            except Exception:
                pass
    return None

def main():
    out = {"python_base": PY_BASE, "routes": []}
    code, health, _, err = http_json(f"{PY_BASE}/api/v1/health", timeout=10)
    out["python_health"] = {"status": code, "data": health, "error": err}
    rust, rhealth = rust_base()
    if not rust:
        started = try_start_rust()
        rust, rhealth = (started, None) if started else (None, None)
        if started:
            _, rhealth, _, _ = http_json(f"{started}/health", timeout=5)
    out["rust_base"] = rust
    out["rust_health"] = rhealth
    for name, a, b in ROUTES:
        start, how_a = geocode(a); end, how_b = geocode(b)
        rec = {"route": name, "from": {"city": a, "latlon": start, "how": how_a},
               "to": {"city": b, "latlon": end, "how": how_b}}
        for obj in ("fastest", "cheapest"):
            rec[f"python_{obj}"] = py_route(start, end, obj) if code == 200 else {"status": None, "error": "python unavailable"}
            rec[f"rust_{obj}"] = rust_route(rust, start, end, obj) if rust else {"status": None, "error": "rust_unavailable"}
        out["routes"].append(rec)
        print(name, rec["python_fastest"], rec["rust_fastest"], flush=True)
    dest = ROOT / "docs" / "reports" / "data" / "phase3c_routes.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"wrote {dest}  python={out['python_health']} rust={rust} {rhealth}")

if __name__ == "__main__":
    main()
