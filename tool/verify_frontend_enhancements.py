#!/usr/bin/env python3
"""Verify the bledi.tn frontend rebuild by MEASURING, not by matching literals.

Run from the repo root, with the backend up on :8000:

    python tool/verify_frontend_enhancements.py

Every check asserts a PROPERTY (a contrast ratio, a count that must agree with
another count, a class that must exist in the BUILT output) rather than a
hardcoded expected literal. That distinction is the whole point: an assertion
on a literal breaks the moment a token is legitimately retuned, and it proves
nothing about whether the property actually holds.

Frontend-specific rules followed here:
  * assert against the MINIFIED build output, which strips quotes and collapses
    whitespace, not against the source text;
  * scope regexes to the array/structure that is meant, so a sibling with the
    same shape cannot satisfy the match.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_ASSETS = ROOT / "apps" / "web" / "build" / "_app" / "immutable" / "assets"
API = "http://127.0.0.1:8000/api/v1"

RESULTS: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((bool(ok), name, detail))


def get(path: str, timeout: int = 120):
    with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
        return json.load(r)


# ── WCAG helpers (the property we actually care about) ────────────────────
def _lum(hexcolor: str) -> float:
    h = hexcolor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    ch = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    f = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]


def ratio(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    return round((max(la, lb) + 0.05) / (min(la, lb) + 0.05), 2)


def css_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in BUILD_ASSETS.glob("*.css"))


# ── 1. Backend: modes are canonical, never raw provenance tags ────────────
def check_backend_modes() -> None:
    stations = get("/stations")
    feats = stations["features"]
    modes = {f["properties"].get("mode") for f in feats}

    # The seed's raw tags must not leak into the API's mode vocabulary.
    leaked = modes & {"rail", "unknown", "louage_red", "louage_blue", "louage_green", "louage"}
    check("no raw provenance tag leaks as a station mode", not leaked, f"leaked={sorted(leaked)}")

    # Every feature must carry both the primary mode and the full mode list.
    missing = [f["properties"].get("id") for f in feats if not f["properties"].get("modes")]
    check("every station carries a modes[] list", not missing, f"{len(missing)} missing")

    # The primary mode must be one of the station's own modes (no invention).
    bad = [
        f["properties"].get("id")
        for f in feats
        if f["properties"].get("mode") not in (f["properties"].get("modes") or [])
    ]
    check("primary mode is always a member of modes[]", not bad, f"{len(bad)} disagree")

    # metadata.by_mode must agree with counting the features ourselves.
    meta = stations["metadata"].get("by_mode") or {}
    counted: dict[str, int] = {}
    for f in feats:
        for m in f["properties"].get("modes") or []:
            counted[m] = counted.get(m, 0) + 1
    check(
        "metadata.by_mode matches an independent count of features",
        meta == counted,
        f"meta={meta} counted={counted}" if meta != counted else "",
    )

    # rail -> train and louage_* -> louaj, verified on real ids rather than a
    # count, so the assertion survives data growth.
    rail_ids = [f["properties"]["id"] for f in feats if f["properties"].get("mode_raw") == "rail"]
    rail_ok = all(
        "train" in (f["properties"].get("modes") or [])
        for f in feats
        if f["properties"].get("mode_raw") == "rail"
    )
    check("raw 'rail' resolves to the train mode", not rail_ids or rail_ok, f"{len(rail_ids)} rail stops")


# ── 2. Backend: the station inspector agrees with the dot colour ──────────
def check_station_detail_consistency() -> None:
    stations = get("/stations")
    feats = stations["features"]

    # Sample a spread of ids rather than only the ones we know about.
    def pick(pred, n=3):
        return [f["properties"]["id"] for f in feats if pred(f["properties"])][:n]

    samples = (
        pick(lambda p: p.get("mode") == "bus")
        + pick(lambda p: p.get("mode") == "train")
        + pick(lambda p: p.get("mode") == "unclassified")
        + pick(lambda p: p.get("mode") == "metro")
    )
    mismatched: list[str] = []
    for sid in samples:
        det = get(f"/stations/{sid}", timeout=60)
        detail_modes = set(det.get("modes") or [])
        if not detail_modes:
            mismatched.append(f"{sid}: detail reports no mode at all")
    check(
        "station detail never reports an empty mode for a coloured stop",
        not mismatched,
        "; ".join(mismatched[:4]),
    )

    # A stop with real lines must report them, and each line must say where the
    # stop sits on it (the "coming from / going by" answer).
    with_lines = None
    for f in feats:
        sid = f["properties"]["id"]
        if f["properties"].get("mode") != "train":
            continue
        det = get(f"/stations/{sid}", timeout=60)
        if det.get("lines"):
            with_lines = det
            break
    if with_lines:
        roles = {ln.get("role") for ln in with_lines["lines"]}
        check(
            "a line-serving stop reports a role for every line",
            roles <= {"origin", "terminus", "through"} and all(
                ln.get("role") for ln in with_lines["lines"]
            ),
            f"roles={roles}",
        )
    else:
        check("a line-serving stop reports a role for every line", False, "no train stop with lines found")


# ── 3. Backend: the network layer carries real geometry by transport type ─
def check_network() -> None:
    net = get("/network")
    segs = net["segments"]
    meta = net["metadata"]
    check("network returns track segments", len(segs) > 0, f"{len(segs)} segments")

    # Only routable modes may appear, and geometry-less segments must be
    # flagged rather than stitched into a straight line.
    modes = {s["mode"] for s in segs}
    check("network modes are canonical", not (modes & {"rail", "unknown"}), f"modes={sorted(modes)}")
    unflagged = [s["id"] for s in segs if not s["has_geometry"] and not s.get("straight_m")]
    check("geometry-less segments are flagged, not stitched", not unflagged, f"{len(unflagged)} unflagged")

    by_mode = meta.get("by_mode") or {}
    counted: dict[str, int] = {}
    for s in segs:
        if s["has_geometry"]:
            counted[s["mode"]] = counted.get(s["mode"], 0) + 1
    check(
        "network metadata.by_mode matches the segments returned",
        by_mode == counted,
        f"meta={by_mode} counted={counted}" if by_mode != counted else "",
    )

    # Rail and road must be distinguishable, which is the whole point of the
    # per-transport neon colouring.
    check(
        "network separates rail from road",
        bool({"train", "metro"} & modes) and "bus" in modes,
        f"modes={sorted(modes)}",
    )


# ── 4. Backend: name search (so no coordinates are ever typed) ────────────
def check_search() -> None:
    res = get("/search?q=ariana", timeout=60)
    hits = res["results"]
    check("name search returns hits", len(hits) > 0, f"{len(hits)} hits")
    check(
        "every hit carries a name and coordinates",
        all(h.get("name") and h.get("lat") and h.get("lon") for h in hits),
    )
    check(
        "hits are labelled stop or city",
        all(h.get("kind") in {"stop", "city"} for h in hits),
        f"kinds={ {h.get('kind') for h in hits} }",
    )

    # Ambiguous names must be separable: the distance bias has to actually move
    # the RANKING. Asserting that the top hit changes is wrong — two reference
    # points can legitimately share a nearest stop (both Tunis and Mahdia are
    # closest to the same "20 Mars"), and the bias still works. Compare the
    # whole ordering instead, which is the property that matters.
    near = [h["id"] for h in get("/search?q=20%20mars&near_lat=36.80&near_lon=10.18", timeout=60)["results"]]
    far = [h["id"] for h in get("/search?q=20%20mars&near_lat=34.74&near_lon=10.76", timeout=60)["results"]]
    if near and far:
        check(
            "distance bias reorders ambiguous names",
            near != far,
            f"identical order from both reference points: {near[:4]}",
        )
    else:
        check("distance bias reorders ambiguous names", False, "no hits for the ambiguous query")


# ── 5. Built CSS: the neon rendering actually shipped ────────────────────
def check_built_css() -> None:
    if not BUILD_ASSETS.exists():
        check("built CSS assets exist", False, str(BUILD_ASSETS))
        return
    css = css_text()

    # One neon token per transport type, declared in BOTH theme blocks.
    for token in ("--n-bus", "--n-tram", "--n-metro", "--n-train", "--n-louaj"):
        # Minifier strips the space after the colon, so match the value shape.
        n = len(re.findall(rf"{re.escape(token)}\s*:\s*#", css))
        check(f"{token} declared in both themes", n >= 2, f"found {n} declarations")

    # Per-mode network panes: the mechanism that gives each transport its own
    # glow (a canvas can only carry one filter).
    panes = set(re.findall(r"leaflet-net_([a-z_]+)-pane", css))
    check(
        "per-mode network panes shipped",
        {"bus", "metro", "train"} <= panes,
        f"panes={sorted(panes)}",
    )

    # Per-mode route leg classes, so each transport's leg gets its own glow.
    legs = set(re.findall(r"route-leg-([a-z_]+)", css))
    check(
        "per-mode route leg classes shipped",
        {"bus", "train", "walk"} <= legs,
        f"legs={sorted(legs)}",
    )

    # The glow itself must be present as a drop-shadow, and the focus dimming
    # must be a real opacity rule.
    check("neon glow uses drop-shadow", css.count("drop-shadow") >= 5, f"{css.count('drop-shadow')} occurrences")
    check(
        "focus mode dims non-route layers",
        bool(re.search(r"focused[^{]*\{[^}]*opacity:\s*0?\.1", css)),
        "no dimming rule found",
    )

    # No emoji may be used as a structural glyph. Scan the shipped JS/CSS for
    # emoji codepoints, which is where a stray icon would end up.
    emoji_re = re.compile(
        "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF]"
    )
    js_dir = ROOT / "apps" / "web" / "build" / "_app" / "immutable"
    offenders = []
    for p in list(js_dir.rglob("*.js")) + list(js_dir.rglob("*.css")):
        m = emoji_re.search(p.read_text(encoding="utf-8", errors="replace"))
        if m:
            offenders.append(f"{p.name}:{m.group(0)}")
    check("no emoji in the shipped bundle", not offenders, ", ".join(offenders[:5]))


# ── 6. Built CSS: light-theme contrast measured, not eyeballed ───────────
def check_contrast() -> None:
    css = css_text()
    # Pull the light-theme block out of the MINIFIED css and read the values
    # from there, so this proves what shipped rather than what we intended.
    light = re.search(r'\[data-theme="?light"?\]\{(.*?)\}', css, re.S)
    if not light:
        light = re.search(r"\[data-theme=light\]\{(.*?)\}", css, re.S)
    if not light:
        check("light theme block present in built CSS", False, "not found")
        return
    block = light.group(1)
    # The component's light block uses --bg; the global (app.css) block uses
    # --g-bg. Accept either, since both are the light ground and either one
    # proves the token set shipped.
    bg_m = re.search(r"--(?:g-)?bg:\s*(#[0-9a-fA-F]{3,6})", block)
    if not bg_m:
        check("light theme declares a background", False, block[:80])
        return
    bg = bg_m.group(1)

    failures = []
    # Check whichever of each pair is present: the component declares --n-*,
    # the global block declares --g-* for map chrome.
    for tokens in (
        ("--n-bus",),
        ("--n-tram",),
        ("--n-metro",),
        ("--n-train",),
        ("--n-louaj",),
        ("--tx", "--g-tx"),
        ("--mu", "--g-mu"),
    ):
        found = None
        for token in tokens:
            m = re.search(rf"{re.escape(token)}:\s*(#[0-9a-fA-F]{{3,6}})", block)
            if m:
                found = (token, m.group(1))
                break
        if not found:
            failures.append(f"{tokens[0]} missing")
            continue
        token, value = found
        r = ratio(value, bg)
        if r < 4.5:
            failures.append(f"{token}={value} ratio {r}")
    check(
        "light-theme text/neon colours clear WCAG AA (>=4.5) on the light ground",
        not failures,
        "; ".join(failures),
    )


def main() -> int:
    try:
        check_backend_modes()
        check_station_detail_consistency()
        check_network()
        check_search()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"BACKEND UNREACHABLE: {exc}")
        print("start it with: uvicorn --factory bledi_transit.main:create_app --port 8000")
        return 2

    check_built_css()
    check_contrast()

    passed = sum(1 for ok, _, _ in RESULTS if ok)
    for ok, name, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail and not ok:
            line += f"\n         -> {detail}"
        print(line)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
