#!/usr/bin/env python3
"""Verify the bledi.tn app: routing behaviour, frontend build, UI invariants.

Ad-hoc verification, NOT a suite green. Exits 0 only if every check passes.

  python scripts/verify_frontend.py [--skip-build]

Checks:
  1. Routing: the mode selection actually filters results. The original bug
     was that the taxi fallback ignored the caller's mode filter, so
     "walk only" returned a taxi. Each single mode must come back alone, and
     a multi-mode selection must not smuggle in an unselected taxi.
  2. Louage is priced as a shared van, distinct from a private taxi.
  3. Production build succeeds (static adapter emits build/).
  4. The emitted CSS bundle exists and carries the dark theme tokens.
  5. Source invariants for the redesign (icons, i18n/RTL, mode counter,
     grey-out, fare field, polyline casing, a11y).
  6. Live probe of :8080 when a preview server is listening.

NOTE: running the build replaces hashed assets under a live `vite preview`
and stops it, so :8080 is probed before the build (`--skip-build` to only
probe).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"
MAP = FE / "src/routes/map/+page.svelte"
ICON = FE / "src/lib/Icon.svelte"
I18N = FE / "src/lib/i18n.ts"
ROUTER = FE / "src/lib/router.ts"
ROUTING = ROOT / "src/backend/app/routing.py"

API = "http://localhost:8000/api/v1"
_TRIP = (
    "start_lat=36.8065&start_lon=10.1815"
    "&end_lat=36.7528&end_lon=10.2108&objective=fastest"
)

_results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    _results.append((ok, f"{label}{f' ({detail})' if detail else ''}"))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def get(url: str, timeout: float = 12.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def modes_for(selection: str) -> str:
    """Sorted modes_used per itinerary, pipe-joined. 'ERR' when unreachable."""
    try:
        d = get(f"{API}/route/plan?{_TRIP}&modes_include={selection}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return "ERR"
    return "|".join(
        ",".join(sorted(i.get("modes_used") or [])) for i in d.get("itineraries", [])
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true", help="do not run npm run build")
    args = ap.parse_args()

    src, icon, i18n, router, routing = (
        read(MAP), read(ICON), read(I18N), read(ROUTER), read(ROUTING)
    )

    # Probe first — the build below stops a live preview server.
    print("=== LIVE :8080 ===")
    for path, want in (("/map", 200), ("/api/v1/health", 200)):
        try:
            with urllib.request.urlopen(f"http://localhost:8080{path}", timeout=5) as r:
                check(r.status == want, f"GET {path}", str(r.status))
        except (urllib.error.URLError, OSError):
            print(f"SKIP  GET {path} — no server on :8080")

    # 1. mode filtering — the reported bug.
    print("\n=== ROUTING: mode selection filters ===")
    try:
        get(f"{API}/health")
    except (urllib.error.URLError, OSError):
        print("SKIP  backend not reachable on :8000")
    else:
        for sel in ("walk", "louaj", "bus", "metro", "train", "taxi"):
            check(modes_for(sel) == sel, f"{sel} only -> {sel}", modes_for(sel))
        multi = modes_for("bus,metro,tram,train,rfr")
        check("taxi" not in multi, "default 5 modes inject no taxi", multi)
        check("taxi" not in modes_for("walk"), "walk-only returns no taxi")

        # 2. louage priced as shared, not private hire.
        print("\n=== ROUTING: louage vs taxi fare ===")
        def fare(sel: str) -> float:
            try:
                d = get(f"{API}/route/plan?{_TRIP}&modes_include={sel}")
            except (urllib.error.URLError, OSError, json.JSONDecodeError):
                return 0.0
            its = d.get("itineraries") or [{}]
            return float(its[0].get("fare_estimate_dinars") or its[0].get("fare_dinars") or 0)
        lf, tf = fare("louaj"), fare("taxi")
        check(lf > 0 and lf != tf, "louage fare differs from taxi", f"{lf} vs {tf} DT")

    # 3. build
    print("\n=== BUILD ===")
    if args.skip_build:
        print("SKIP  npm run build (--skip-build)")
    else:
        p = subprocess.run(
            ["npm", "run", "build"], cwd=FE, capture_output=True, text=True, shell=True
        )
        check(p.returncode == 0, "npm run build exits 0", str(p.returncode))
        if p.returncode != 0:
            print((p.stderr or p.stdout)[-1200:])

    # 4. emitted CSS
    print("\n=== EMITTED CSS ===")
    css = list((FE / "build/_app/immutable/assets").glob("*.css"))
    if css:
        blob = "".join(read(c) for c in css)
        check(sum(len(read(c)) for c in css) > 20_000, "css bundle > 20KB")
        check("070d18" in blob, "theme background token present")
        check("leaflet-container" in blob, "leaflet base styles present")
    else:
        check(False, "css bundle emitted")

    # 5. source invariants
    print("\n=== ICONS ===")
    emoji = re.findall(r"[\U0001F300-\U0001FAFF]", src)
    check(not emoji, "no emoji in map page", f"{len(emoji)} found")
    check(bool(re.search(r'icon:\s*"bus"', src)), "modes use icon names")
    check(icon.count(": '") >= 18, "vector icon set", f"{icon.count(chr(58) + ' ')} entries")

    print("\n=== I18N / RTL ===")
    for loc in ("fr", "en", "ar"):
        check(f"const {loc}: Dict" in i18n, f"locale '{loc}' defined")
    check("rtl" in i18n, "RTL direction helper")
    check("dir={dir}" in src and "lang={lang}" in src, "dir/lang bound on root")
    check('"modes.taxi": "Taxi"' in i18n, "taxi translated (fr)")
    check('"modes.taxi": "تاكسي"' in i18n, "taxi translated (ar)")

    print("\n=== MODES UI ===")
    block = re.search(r"const MODES = \[(.*?)\] as const;", src, re.S)
    n_modes = len(re.findall(r'\{ id: "', block.group(1))) if block else 0
    check(n_modes == 8, "mode count (incl. taxi)", str(n_modes))
    check('class="counter"' in src, "mode counter present")
    check("count === 0" in src, "zero-count guard present")
    check("disabled={computing || count === 0}" in src, "CTA disabled at 0 modes")
    check("mode:not(.on)" in src, "unchecked modes greyed entirely")
    check("showToast" in src, "toast implemented")

    print("\n=== RESULT CORRECTNESS ===")
    check("fare_estimate_dinars" in src, "reads fare_estimate_dinars")
    check("legLabel" in src, "leg label humanised")
    check("modeLabel" in i18n and "modeLabel" in src, "modeLabel guards raw keys")
    check(not re.findall(r't\("modes\.\s*"\s*\+', src), "no raw mode-key concatenation")
    check("casing" in src.lower(), "polyline casing present")
    check("World_Dark_Gray" in src, "Esri dark basemap in use")
    check("invert(1)" not in src, "no muddy invert() filter")
    check("scrollIntoView" in src, "auto-scroll to results")
    check("geocode(q: string)" in router, "geocode in router")

    print("\n=== ROUTING SOURCE GUARDS ===")
    check("taxi_permitted" in routing, "route(): taxi gated on allowed_modes")
    check("hop_permitted" in routing, "_expand_path(): hop gated")
    check('not (allowed_modes - {"walk"})' in routing, "walk-only short-circuit")
    check('road_mode = "louaj"' in routing, "louage labelled as louage")

    print("\n=== A11Y / POLISH ===")
    for needle, label in (
        ("aria-pressed", "aria-pressed on toggles"),
        ('role="alert"', "role=alert on errors"),
        (":focus-visible", "focus-visible styles"),
        ("prefers-reduced-motion", "reduced-motion support"),
        ("@media (max-width", "responsive breakpoints"),
    ):
        check(needle in src, label)

    # summary
    print("\n=== SUMMARY ===")
    for ok, label in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    failed = sum(1 for ok, _ in _results if not ok)
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    if failed:
        print("RESULT: FAILURES PRESENT")
        return 1
    print("RESULT: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

