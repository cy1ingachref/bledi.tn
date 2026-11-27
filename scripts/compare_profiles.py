#!/usr/bin/env python3
"""WP6: compare golden routes across the legacy and open profiles.

Runs every pair in tests/golden_routes.json through the routing API for each
profile and reports: resolved on legacy, resolved on open, duration ratio,
transfer counts, and pairs that resolve on legacy but not open.

No network to Overpass; only local API calls. Each profile is a base URL, so
the same script works against a legacy stack and an open stack.

Usage:
  python scripts/compare_profiles.py \
      --legacy-url http://127.0.0.1:8080 --open-url http://127.0.0.1:8081 \
      --out docs/reports/profile-comparison.json
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = REPO / "tests" / "golden_routes.json"
DEFAULT_OUT = REPO / "docs" / "reports" / "profile-comparison.json"


def route(base: str, pair: dict, timeout: float) -> dict:
    q = urllib.parse.urlencode({
        "start_lat": pair["from"]["lat"], "start_lon": pair["from"]["lon"],
        "end_lat": pair["to"]["lat"], "end_lon": pair["to"]["lon"],
        "modes_include": "bus,train,louage,taxi,metro",
        "max_itineraries": 3,
    })
    url = base.rstrip("/") + "/api/v1/route/plan?" + q
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        its = data.get("itineraries") or []
        if not its:
            return {"resolved": False, "status": "no_route"}
        best = min(its, key=lambda i: float(i.get("duration_min") or 0))
        return {
            "resolved": True,
            "duration_min": float(best.get("duration_min") or 0),
            "transfers": int(best.get("transfers") or 0),
            "modes": best.get("modes_used") or [],
        }
    except Exception as exc:  # network/HTTP/timeout -> unresolved, with reason
        return {"resolved": False, "status": f"error: {type(exc).__name__}"}


def compare(pairs: list[dict], legacy_url: str, open_url: str, timeout: float,
            *, runner=route) -> dict:
    results = []
    for p in pairs:
        l = runner(legacy_url, p, timeout)
        o = runner(open_url, p, timeout)
        ratio = None
        if l.get("resolved") and o.get("resolved") and l.get("duration_min"):
            ratio = round(o["duration_min"] / l["duration_min"], 3)
        results.append({
            "id": p["id"], "category": p.get("category"), "region": p.get("region"),
            "expect": p.get("expect"),
            "legacy": l, "open": o, "duration_ratio_open_legacy": ratio,
            "legacy_only_failure": bool(l.get("resolved") and not o.get("resolved")),
        })
    resolved_l = sum(1 for r in results if r["legacy"]["resolved"])
    resolved_o = sum(1 for r in results if r["open"]["resolved"])
    ratios = [r["duration_ratio_open_legacy"] for r in results if r["duration_ratio_open_legacy"]]
    ratios.sort()
    return {
        "pairs": len(results),
        "legacy_resolved": resolved_l, "open_resolved": resolved_o,
        "open_resolution_rate": round(resolved_o / resolved_l, 4) if resolved_l else 0.0,
        "median_duration_ratio": ratios[len(ratios) // 2] if ratios else None,
        "legacy_only_failures": [r["id"] for r in results if r["legacy_only_failure"]],
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    ap.add_argument("--legacy-url", default="http://127.0.0.1:8080")
    ap.add_argument("--open-url", default="http://127.0.0.1:8081")
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    report = compare(golden["pairs"], args.legacy_url, args.open_url, args.timeout)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    print(f"legacy resolved {report['legacy_resolved']}/{report['pairs']}; "
          f"open resolved {report['open_resolved']}; ratio {report['open_resolution_rate']:.1%}")
    if report["legacy_only_failures"]:
        print("legacy-only failures:", ", ".join(report["legacy_only_failures"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
