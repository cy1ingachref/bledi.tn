"""Tests for endpoint override, 502/503 retry, and --from-file import."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import fetch_osm_export as fetch  # noqa: E402

QUERY_FILE = REPO / "scripts" / "overpass_query.ql"
QUERY = fetch.load_query(QUERY_FILE)


def _overpass_payload(n_nodes=60, n_routes=12, base="2026-01-01T00:00:00Z"):
    els = []
    for i in range(n_nodes):
        els.append({"type": "node", "id": i, "tags": {"public_transport": "stop_position"}})
    for i in range(n_routes):
        els.append({"type": "relation", "id": 1000 + i, "tags": {"type": "route"}})
    return {"elements": els, "osm3s": {"timestamp_osm_base": base}}


def test_endpoint_override_from_env(monkeypatch):
    monkeypatch.delenv("OVERPASS_ENDPOINTS", raising=False)
    assert fetch.endpoints_from_env() == fetch.DEFAULT_ENDPOINTS
    monkeypatch.setenv("OVERPASS_ENDPOINTS", "https://a.test/api, https://b.test/api")
    assert fetch.endpoints_from_env() == ("https://a.test/api", "https://b.test/api")
    monkeypatch.setenv("OVERPASS_ENDPOINTS", "not-a-url")
    with pytest.raises(ValueError, match="OVERPASS_ENDPOINTS"):
        fetch.endpoints_from_env()


def test_502_and_503_retried_once_then_next_endpoint(monkeypatch):
    calls = []

    def first(*a, **k):
        calls.append("a")
        raise fetch.FetchError("HTTP 502", status=502)

    def second(*a, **k):
        calls.append("b")
        raise fetch.FetchError("HTTP 503", status=503)

    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)
    with pytest.raises(fetch.FetchError):
        fetch.fetch_payload("ua", query=QUERY,
                            endpoints=["https://a.test", "https://b.test"],
                            fetchers=[first, second])
    # one retry per endpoint, then move on: 2 calls per endpoint
    assert calls.count("a") == 2 and calls.count("b") == 2


def test_from_file_accept_real_geojson(tmp_path):
    geo = {
        "type": "FeatureCollection", "generator": "overpass-turbo",
        "timestamp": "2026-11-28T00:00:48Z",
        "features": [
            {"type": "Feature", "properties": {
                "@id": f"node/{i}", "public_transport": "stop_position",
                "@relations": ([{"rel": 1, "reltags": {"type": "route"}}] if i == 0 else []),
            }} for i in range(60)
        ] + [
            {"type": "Feature", "properties": {
                "@id": f"relation/{j}", "@relations": [{"rel": 2000 + j, "reltags": {"type": "route"}}],
            }} for j in range(12)
        ],
    }
    src = tmp_path / "export.geojson"; src.write_text(json.dumps(geo), encoding="utf-8")
    out, man = tmp_path / "out.json", tmp_path / "manifest.json"
    rc = fetch.main(["--from-file", str(src), "--output", str(out),
                     "--manifest", str(man), "--query-file", str(QUERY_FILE)])
    assert rc == 0
    assert out.read_bytes() == src.read_bytes()
    m = json.loads(man.read_text(encoding="utf-8"))
    assert m["source"] == "manual overpass-turbo"
    assert m["query"] == QUERY
    assert m["osm3s_timestamp_osm_base"] == "2026-11-28T00:00:48Z"
    assert m["export_sha256"] == fetch.sha256_bytes(src.read_bytes())
    assert m["element_counts"]["stop_nodes"] >= fetch.MIN_STOP_NODES
    assert m["element_counts"]["route_relations"] >= fetch.MIN_ROUTE_RELATIONS


def test_from_file_reject_old_louage_export(tmp_path):
    # Old louage export shape: 84 elements, no route relations, no timestamp.
    old = {"osm3s": {"timestamp_osm_base": "2026-10-27T14:31:56Z"},
           "elements": [{"type": "node", "id": i, "tags": {"highway": "bus_stop"}} for i in range(65)]}
    src = tmp_path / "louage.json"; src.write_text(json.dumps(old), encoding="utf-8")
    man = tmp_path / "manifest.json"
    rc = fetch.main(["--from-file", str(src), "--manifest", str(man),
                     "--output", str(tmp_path / "out.json"), "--query-file", str(QUERY_FILE)])
    assert rc == 2
    assert not man.exists()  # never write a manifest for a rejected file


def test_from_file_rejects_geojson_without_timestamp(tmp_path):
    geo = {"type": "FeatureCollection", "features": [
        {"properties": {"public_transport": "stop_position",
                        "@relations": [{"rel": i, "reltags": {"type": "route"}} for i in range(12)]}}
        for _ in range(60)
    ]}
    src = tmp_path / "no-ts.json"; src.write_text(json.dumps(geo), encoding="utf-8")
    man = tmp_path / "manifest.json"
    rc = fetch.main(["--from-file", str(src), "--manifest", str(man),
                     "--output", str(tmp_path / "out.json"), "--query-file", str(QUERY_FILE)])
    assert rc == 2
    assert not man.exists()


def test_manifest_uses_real_query_file_text(tmp_path):
    raw = json.dumps(_overpass_payload()).encode()
    payload = json.loads(raw)
    m = fetch.make_manifest(payload, raw, tmp_path / "e.json",
                            counts=fetch.validate_payload(payload),
                            query=QUERY, endpoint="https://x.test")
    assert m["query"] == QUERY_FILE.read_text(encoding="utf-8").strip()
