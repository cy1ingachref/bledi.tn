"""WP3 tests: coverage report maths (synthetic data only, no real export)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import open_coverage_report as cov  # noqa: E402


def test_normalise_strips_accents_case_and_common_words():
    assert cov.normalise("Gare de l'Ennour") == cov.normalise("Ennour")


def test_haversine_zero_and_known_distance():
    assert cov.haversine(36.8, 10.2, 36.8, 10.2) == 0.0
    # ~111 m per 0.001 degree latitude.
    assert 100 < cov.haversine(36.8, 10.2, 36.801, 10.2) < 120


def test_station_match_requires_same_mode_distance_and_name():
    legacy = [
        {"id": "L1", "name": "Tunis Marine", "mode": "train", "lat": 36.8, "lon": 10.2},
        {"id": "L2", "name": "Far Away", "mode": "bus", "lat": 36.8, "lon": 10.2},
    ]
    opened = [
        {"id": "O1", "name": "Tunis Marine", "mode": "bus", "lat": 36.8, "lon": 10.2},   # wrong mode
        {"id": "O2", "name": "Tunis Marine", "mode": "train", "lat": 36.81, "lon": 10.2},  # >150 m
        {"id": "O3", "name": "Tunis Marine", "mode": "train", "lat": 36.8005, "lon": 10.2}, # match
    ]
    r = cov.match_stations(legacy, opened, 150.0)
    assert r["matched"] == 1
    assert r["unmatched_legacy"] == 1
    assert r["match_rate"] == 0.5
    assert r["open_only"] == 2  # O3 matched; O1 (wrong mode) and O2 (too far) are open-only


def test_line_match_by_number_operator_name():
    legacy = [{"id": "L1", "number": "M1", "operator": "Transtu", "name": "Line 1", "stations": ["a", "b"]}]
    opened = [{"id": "O1", "number": "M1", "operator": "Transtu", "name": "Line 1", "stops": ["x", "y"]}]
    r = cov.match_lines(legacy, opened)
    assert r["matched"] == 1 and r["missing"] == 0


def test_line_missing_and_top30_uses_stop_proxy():
    legacy = [
        {"id": f"L{i}", "number": f"X{i}", "operator": "Op", "name": f"Line {i}",
         "stations": ["a"] * (i + 1)}
        for i in range(35)
    ]
    r = cov.match_lines(legacy, [])
    assert r["missing"] == 35
    assert len(r["top30_missing_by_stop_proxy"]) == 30
    assert r["top30_missing_by_stop_proxy"][0]["stops"] == 35


def test_report_marks_synthetic_from_manifest(tmp_path):
    manifest = {"fetched_at_utc": None, "osm3s_timestamp_osm_base": None, "export_sha256": None}
    mf = tmp_path / "manifest.json"; mf.write_text(json.dumps(manifest))
    leg = tmp_path / "legacy.json"; leg.write_text(json.dumps({"stations": [], "lines": []}))
    opn = tmp_path / "open.json"; opn.write_text(json.dumps({"stations": [], "lines": []}))
    out_md = tmp_path / "report.md"; out_json = tmp_path / "report.json"
    res = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "open_coverage_report.py"),
         "--legacy", str(leg), "--open", str(opn), "--manifest", str(mf),
         "--out-md", str(out_md), "--out-json", str(out_json),
         "--distance-m", "200"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    data = json.loads(out_json.read_text())
    assert data["synthetic_fixture"] is True
    assert data["stations"]["distance_m"] == 200.0
    assert "synthetic fixture" in out_md.read_text().lower()
