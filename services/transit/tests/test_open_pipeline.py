"""WP5 tests: open pipeline file shapes + provenance gate."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import open_pipeline as pipe  # noqa: E402
import check_provenance as prov  # noqa: E402


def _seed():
    return {
        "metadata": {"source": "OSM", "osm3s_timestamp_osm_base": "2026-01-01T00:00:00Z"},
        "stations": [
            {"id": "osm:1", "name": "A", "name_ar": "أ", "lat": 36.8, "lon": 10.2,
             "mode": "bus", "operator": "Transtu", "license_status": "odbl", "lines_served": ["osm:l"]},
            {"id": "osm:2", "name": "B", "lat": 36.9, "lon": 10.3, "mode": "train", "license_status": "odbl"},
        ],
        "lines": [
            {"id": "osm:l", "name": "Line", "number": "1", "mode": "bus",
             "operator": "Transtu", "stops": ["osm:1", "osm:2"], "license_status": "odbl"},
        ],
    }


def test_convert_produces_service_shapes():
    tagged, tmap = pipe.convert(_seed())
    # Transit service: flat stations/lines with the fields it reads.
    assert set(tagged) == {"metadata", "stations", "lines"}
    s = tagged["stations"][0]
    for key in ("id", "name", "name_ar", "lat", "lon", "mode", "operator", "license_status", "lines_served"):
        assert key in s
    # Rust graph.rs: RawStation/RawLine (id + optional fields).
    assert tmap["stations"][0]["id"] == "osm:1"
    assert tmap["lines"][0]["stations"] == ["osm:1", "osm:2"]
    assert tmap["by_mode"] == {}


def test_documents_match_source():
    doc = (REPO / "docs" / "data-schemas.md").read_text(encoding="utf-8")
    for token in ("transport_map_corrected.json", "seed_all_tunisia_routes.tagged.json", "BLEDI_DATA_DIR", "by_mode"):
        assert token in doc


def test_provenance_count_bad():
    seed = _seed()
    assert prov.count_bad(seed) == (0, 3)
    seed["stations"][0]["license_status"] = "unknown-third-party"
    assert prov.count_bad(seed) == (1, 3)


def test_open_profile_gate_enforcing(tmp_path):
    good = tmp_path / "good.json"; good.write_text(json.dumps(_seed()))
    bad_seed = _seed(); bad_seed["lines"][0]["license_status"] = "unknown-third-party"
    bad = tmp_path / "bad.json"; bad.write_text(json.dumps(bad_seed))
    g = subprocess.run([sys.executable, str(REPO / "scripts" / "check_provenance.py"),
                        "--profile", "open", "--seed", str(good)], capture_output=True, text=True)
    b = subprocess.run([sys.executable, str(REPO / "scripts" / "check_provenance.py"),
                        "--profile", "open", "--seed", str(bad)], capture_output=True, text=True)
    assert g.returncode == 0 and "OK" in g.stdout
    assert b.returncode == 1 and "FAILED" in b.stdout


def test_legacy_profile_gate_informational(tmp_path):
    seed = _seed(); seed["stations"][0]["license_status"] = "unknown-third-party"
    p = tmp_path / "legacy.json"; p.write_text(json.dumps(seed))
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "check_provenance.py"),
                        "--profile", "legacy", "--seed", str(p)], capture_output=True, text=True)
    assert r.returncode == 0 and "WARNING" in r.stdout


def test_pipeline_runs_end_to_end(tmp_path):
    src = tmp_path / "seed_open_source.json"; src.write_text(json.dumps(_seed()))
    out = tmp_path / "open"
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "open_pipeline.py"),
                        "--source", str(src), "--out-dir", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    tagged = json.loads((out / "seed_all_tunisia_routes.tagged.json").read_text())
    tmap = json.loads((out / "transport_map_corrected.json").read_text())
    assert tagged["metadata"]["profile"] == "open"
    assert tmap["lines"][0]["stations"] == ["osm:1", "osm:2"]
