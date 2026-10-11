#!/usr/bin/env python3
"""Verify the bledi.tn SvelteKit frontend (build + design invariants).

Ad-hoc verification, NOT a suite green. Exits 0 only if every check passes.

  python scripts/verify_frontend.py [--skip-build]

Checks:
  1. Production build succeeds (static adapter emits build/).
  2. The emitted CSS bundle exists and carries the dark theme tokens.
  3. Source invariants for the redesign:
       - no emoji used as structural icons (ui-ux-pro-max pro-rules)
       - FR/EN/AR dictionaries + RTL helper
       - taxi is a first-class mode, and translated
       - modeLabel() guards against raw i18n keys reaching the DOM
       - fares read fare_estimate_dinars (the field the API returns)
       - polyline casing, results auto-scroll
       - a11y: aria-pressed, role=alert, focus-visible, reduced-motion
  4. If a preview server is listening on :8080, probe it.

NOTE: running the build replaces hashed assets under a live `vite preview`
and stops it. Probe :8080 before building (`--skip-build` to only probe).
"""
from __future__ import annotations

import argparse
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

_results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    _results.append((ok, f"{label}{f' ({detail})' if detail else ''}"))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true", help="do not run npm run build")
    args = ap.parse_args()

    src, icon, i18n, router = read(MAP), read(ICON), read(I18N), read(ROUTER)

    # 4. probe first — the build below stops a live preview server.
    print("=== PREVIEW :8080 ===")
    for path, want in (("/map", "200"), ("/api/v1/health", "200")):
        try:
            with urllib.request.urlopen(f"http://localhost:8080{path}", timeout=5) as r:
                check(r.status == int(want), f"GET {path}", str(r.status))
        except (urllib.error.URLError, OSError):
            print(f"SKIP  GET {path} — no server on :8080")

    # 1. build
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

    # 2. emitted CSS
    print("\n=== EMITTED CSS ===")
    css = list((FE / "build/_app/immutable/assets").glob("*.css"))
    if css:
        blob = "".join(read(c) for c in css)
        check(sum(len(read(c)) for c in css) > 20_000, "css bundle > 20KB")
        check("070d18" in blob, "theme background token present")
        check("map-tiles-dark" in blob, "dark tile filter present")
        check("leaflet-container" in blob, "leaflet base styles present")
    else:
        check(False, "css bundle emitted")

    # 3. source invariants
    print("\n=== ICONS ===")
    emoji = re.findall(r"[\U0001F300-\U0001FAFF]", src)
    check(not emoji, "no emoji in map page", f"{len(emoji)} found")
    check(bool(re.search(r"icon:\s*\"bus\"", src)), "modes use icon names")
    check(icon.count(": '") >= 18, "vector icon set", f"{icon.count(chr(58) + ' ')} entries")

    print("\n=== I18N / RTL ===")
    for loc in ("fr", "en", "ar"):
        check(f"const {loc}: Dict" in i18n, f"locale '{loc}' defined")
    check("rtl" in i18n, "RTL direction helper")
    check("dir={dir}" in src and "lang={lang}" in src, "dir/lang bound on root")
    check("LANGS" in src, "language switcher in UI")
    check('"modes.taxi": "Taxi"' in i18n, "taxi translated (fr)")
    check('"modes.taxi": "تاكسي"' in i18n, "taxi translated (ar)")

    print("\n=== MODES ===")
    block = re.search(r"const MODES = \[(.*?)\] as const;", src, re.S)
    n_modes = len(re.findall(r'\{ id: "', block.group(1))) if block else 0
    check(n_modes == 8, "mode count (incl. taxi)", str(n_modes))
    check("taxi" in src, "taxi wired into UI")

    print("\n=== RESULT CORRECTNESS ===")
    check("fare_estimate_dinars" in src, "reads fare_estimate_dinars")
    check("legLabel" in src, "leg label humanised")
    check("modeLabel" in i18n and "modeLabel" in src, "modeLabel guards raw keys")
    leaks = re.findall(r't\("modes\.\s*"\s*\+', src)
    check(not leaks, "no raw mode-key concatenation", f"{len(leaks)} found")
    check("casing" in src.lower(), "polyline casing present")
    check("scrollIntoView" in src, "auto-scroll to results")
    check("geocode(q: string)" in router, "geocode in router")

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
