"""STEP 1 regression tests: hardened Overpass fetch (partial/error payloads)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import fetch_osm_export as fetch  # noqa: E402

QUERY = fetch.load_query(REPO / "scripts" / "overpass_query.ql")


def _payload(n_nodes=0, n_routes=0, remark=""):
    els = []
    for i in range(n_nodes):
        els.append({"type": "node", "id": i, "lat": 36.8, "lon": 10.2,
                    "tags": {"public_transport": "stop_position", "bus": "yes"}})
    for i in range(n_routes):
        els.append({"type": "relation", "id": 1000 + i,
                    "tags": {"type": "route", "route": "bus"}})
    p = {"elements": els, "osm3s": {"timestamp_osm_base": "2026-01-01T00:00:00Z"}}
    if remark:
        p["remark"] = remark
    return p


def test_error_remark_is_a_failure():
    for remark in ("error: something failed", "Query timed out", "out of memory", "runtime error"):
        with pytest.raises(ValueError, match="remark"):
            fetch.validate_payload(_payload(fetch.MIN_STOP_NODES, fetch.MIN_ROUTE_RELATIONS, remark))


def test_benign_remark_is_accepted():
    counts = fetch.validate_payload(_payload(fetch.MIN_STOP_NODES, fetch.MIN_ROUTE_RELATIONS, "query OK"))
    assert counts["stop_nodes"] >= fetch.MIN_STOP_NODES
    assert counts["route_relations"] >= fetch.MIN_ROUTE_RELATIONS


def test_minimum_stop_nodes_required():
    with pytest.raises(ValueError, match="stop nodes"):
        fetch.validate_payload(_payload(fetch.MIN_STOP_NODES - 1, fetch.MIN_ROUTE_RELATIONS))


def test_minimum_route_relations_required():
    with pytest.raises(ValueError, match="route relations"):
        fetch.validate_payload(_payload(fetch.MIN_STOP_NODES, fetch.MIN_ROUTE_RELATIONS - 1))


def test_empty_payload_rejected():
    with pytest.raises(ValueError):
        fetch.validate_payload({"elements": []})


def test_query_sourced_from_file_and_narrow():
    assert 'ISO3166-1"="TN' in QUERY
    assert 'node(area.a)["railway"];' not in QUERY
    assert '"railway"~"^(station|halt|tram_stop|stop)$"' in QUERY
    assert "node(r.rels);" in QUERY


def test_user_agent_requires_contact(monkeypatch):
    monkeypatch.delenv("OVERPASS_CONTACT", raising=False)
    with pytest.raises(RuntimeError, match="OVERPASS_CONTACT"):
        fetch.user_agent_from_env()
    monkeypatch.setenv("OVERPASS_CONTACT", "maintainer@example.com")
    ua = fetch.user_agent_from_env()
    assert "maintainer@example.com" in ua


def test_retry_delay_respects_retry_after():
    class R:
        headers = {"Retry-After": "7"}
    assert fetch.retry_delay(R(), 0) == 7
    assert fetch.retry_delay(type("X", (), {"headers": {}})(), 1) >= 2


def test_retryable_statuses_include_502_503():
    for status in (429, 502, 503, 504):
        assert fetch.is_retryable(status)
    assert not fetch.is_retryable(400)
    assert not fetch.is_retryable(200)


def test_fetch_error_carries_status():
    e = fetch.FetchError("HTTP 502", status=502)
    assert e.status == 502 and "502" in str(e)


def test_http_error_from_fetch_once_is_wrapped(monkeypatch):
    import urllib.error
    def boom(*a, **k):
        raise urllib.error.HTTPError("http://x", 502, "Bad Gateway", {}, None)
    monkeypatch.setattr(fetch.urllib.request, "urlopen", boom)
    with pytest.raises(fetch.FetchError) as exc:
        fetch._fetch_once("http://x", "ua", QUERY)
    assert exc.value.status == 502


def test_manifest_written_only_after_success(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    monkeypatch.setenv("OVERPASS_CONTACT", "maintainer@example.com")
    fail = lambda *a, **k: (_ for _ in ()).throw(fetch.FetchError("offline"))
    rc = fetch.main(["--manifest", str(manifest), "--output", str(tmp_path / "export.json")],
                    fetchers=[fail, fail])
    assert rc == 2
    assert not manifest.exists()
