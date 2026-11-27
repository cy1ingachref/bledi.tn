"""WP6 tests: golden-route file validity and profile comparison maths."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import compare_profiles as cp  # noqa: E402


def test_golden_file_shape_and_coverage():
    d = json.loads((REPO / "tests" / "golden_routes.json").read_text(encoding="utf-8"))
    pairs = d["pairs"]
    assert len(pairs) >= 40
    assert len({p["id"] for p in pairs}) == len(pairs)
    assert any("Tunis Marine" in p["from"]["label"] and "Marsa" in p["to"]["label"] for p in pairs)
    for p in pairs:
        assert p["expect"] in ("resolve", "resolve_or_no_route", "trivial")
        for side in ("from", "to"):
            e = p[side]
            assert 30 < e["lat"] < 38 and 7 < e["lon"] < 12  # Tunisia bounds
            assert e["mode_hint"] in ("bus", "train", "rail", "metro", "louage")
    regions = {p["region"] for p in pairs}
    assert "greater_tunis" in regions and "national" in regions


def test_all_endpoints_snap_to_legacy_seed_within_150m():
    d = json.loads((REPO / "tests" / "golden_routes.json").read_text(encoding="utf-8"))
    seed = json.loads((REPO / "data" / "seed_all_tunisia_routes.tagged.json").read_text(encoding="utf-8"))
    hints = {
        "metro": {"metro", "rail", "train"},
        "train": {"train", "rail"},
        "bus": {"bus", "rural", "rfr"},
        "louage": {"louage", "louaj"},
        "rail": {"rail", "train"},
    }

    def hav(a, b, c, d):
        R = 6371000
        p1, p2 = math.radians(a), math.radians(c)
        h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
        return 2 * R * math.asin(math.sqrt(h))

    for p in d["pairs"]:
        for side in ("from", "to"):
            e = p[side]
            best = min(
                (hav(e["lat"], e["lon"], s["lat"], s["lon"])
                 for s in seed["stations"]
                 if s.get("lat") is not None and s.get("mode") in hints[e["mode_hint"]]),
                default=float("inf"),
            )
            assert best <= 150.0, (p["id"], side, e["label"], best)


def test_compare_computes_ratios_and_failures():
    pairs = [
        {"id": "A", "category": "bus", "region": "x", "expect": "resolve"},
        {"id": "B", "category": "rail", "region": "x", "expect": "resolve"},
    ]
    def fake_runner(base, p, timeout):
        if p["id"] == "A":
            return {"resolved": True, "duration_min": 10.0, "transfers": 0}
        return ({"resolved": True, "duration_min": 20.0, "transfers": 1}
                if base == "legacy" else {"resolved": False, "status": "no_route"})
    r = cp.compare(pairs, "legacy", "open", 5.0, runner=fake_runner)
    assert r["legacy_resolved"] == 2 and r["open_resolved"] == 1
    assert r["open_resolution_rate"] == 0.5
    assert r["legacy_only_failures"] == ["B"]
    assert r["median_duration_ratio"] == 1.0
