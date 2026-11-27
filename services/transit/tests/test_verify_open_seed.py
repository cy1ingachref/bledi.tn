"""WP2 tests: validator rejects bad open seeds and accepts a good one."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import verify_open_seed as voc  # noqa: E402


def _good():
    return {
        "metadata": {"source": "OSM"},
        "stations": [
            {"id": "a", "lat": 36.8, "lon": 10.2, "license_status": "odbl"},
            {"id": "b", "lat": 36.9, "lon": 10.3, "license_status": "official-public"},
        ],
        "lines": [{"id": "l1", "stops": ["a", "b"], "license_status": "odbl"}],
    }


def test_good_seed_passes():
    assert voc.validate(_good()) == []


def test_duplicate_ids_rejected():
    d = _good(); d["stations"].append(dict(d["stations"][0]))
    assert any("duplicate station ids" in f for f in voc.validate(d))


def test_out_of_bounds_rejected():
    d = _good(); d["stations"][0]["lat"] = 48.85
    assert any("outside Tunisia bounds" in f for f in voc.validate(d))


def test_unresolved_stop_rejected():
    d = _good(); d["lines"][0]["stops"] = ["a", "missing"]
    assert any("unresolved stops" in f for f in voc.validate(d))


def test_short_line_rejected():
    d = _good(); d["lines"][0]["stops"] = ["a"]
    assert any("fewer than 2 stops" in f for f in voc.validate(d))


def test_unknown_license_rejected():
    d = _good(); d["stations"][0]["license_status"] = "unknown-third-party"
    assert any("bad license_status" in f for f in voc.validate(d))


def test_missing_top_level_key_rejected():
    assert voc.validate({"stations": [], "lines": []})  # missing metadata
