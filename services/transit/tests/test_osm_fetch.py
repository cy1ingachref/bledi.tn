"""WP1 regression tests: reproducible Overpass fetch + manifest."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import fetch_osm_export as fetch  # noqa: E402


def test_query_uses_iso_code_not_name():
    assert 'ISO3166-1"="TN' in fetch.QUERY
    assert 'name"="Tunisie' not in fetch.QUERY


def test_query_fetches_route_master_and_way_platforms():
    assert 'type"="route_master' in fetch.QUERY
    assert ">;".strip() in fetch.QUERY  # recursion includes way platforms/members


def test_element_counts_by_type():
    payload = {"elements": [{"type": "node"}, {"type": "node"}, {"type": "relation"}, {"type": "way"}]}
    assert fetch.element_counts(payload) == {"node": 2, "relation": 1, "way": 1}


def test_manifest_records_query_timestamp_counts_and_hash(tmp_path):
    raw = b'{"elements": [{"type": "node"}], "osm3s": {"timestamp_osm_base": "2026-01-01T00:00:00Z"}}'
    payload = json.loads(raw)
    out = tmp_path / "tunisia_pt.json"
    m = fetch.make_manifest(payload, raw, out)
    assert m["query"] == fetch.QUERY
    assert m["osm3s_timestamp_osm_base"] == "2026-01-01T00:00:00Z"
    assert m["element_counts"] == {"node": 1}
    assert m["export_sha256"] == fetch.sha256_bytes(raw)
    assert m["license"] == "ODbL — attribution required"
    assert m["fetched_at_utc"].endswith("Z") or "+" in m["fetched_at_utc"]


def test_raw_export_is_gitignored():
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "data/osm_overpass/tunisia_pt.json" in gitignore
