"""STEP 1 regression tests: hardened Overpass fetch (partial/error payloads)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import fetch_osm_export as fetch  # noqa: E402


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


def test_railway_query_narrowed_to_station_types():
    for value in ("station", "halt", "tram_stop", "stop", "platform"):
        assert f'"railway"="{value}"' in fetch.QUERY or f'railway={value}' in fetch.QUERY
    assert 'node(area.a)["railway"];' not in fetch.QUERY


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


def test_retryable_statuses():
    assert fetch.is_retryable(429)
    assert fetch.is_retryable(504)
    assert not fetch.is_retryable(400)
    assert not fetch.is_retryable(200)


def test_fetch_error_carries_status():
    from fetch_osm_export import FetchError
    e = FetchError("HTTP 502", status=502)
    assert e.status == 502 and "502" in str(e)


def test_http_error_from_fetch_once_is_wrapped(monkeypatch):
    import urllib.error
    from fetch_osm_export import FetchError, _fetch_once
    def boom(*a, **k):
        raise urllib.error.HTTPError("http://x", 502, "Bad Gateway", {}, None)
    monkeypatch.setattr(fetch.urllib.request, "urlopen", boom)
    try:
        _fetch_once("http://x", "ua")
    except FetchError as e:
        assert e.status == 502
    else:
        raise AssertionError("HTTPError was not wrapped in FetchError")


def test_manifest_written_only_after_success(tmp_path, monkeypatch):
    # A failed fetch must leave no manifest behind.
    manifest = tmp_path / "manifest.json"
    monkeypatch.setenv("OVERPASS_CONTACT", "maintainer@example.com")
    from fetch_osm_export import FetchError
    fail = lambda *a, **k: (_ for _ in ()).throw(FetchError("offline"))
    rc = fetch.main(["--manifest", str(manifest), "--output", str(tmp_path / "export.json")],
                    fetchers=[fail, fail])
    assert rc == 2
    assert not manifest.exists()
