"""Converter tests: real Overpass Turbo GeoJSON export shape."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import rebuild_seed_from_osm as conv  # noqa: E402


def _geojson():
    """Minimal GeoJSON with one stop node and one route relation."""
    return {
        "type": "FeatureCollection", "generator": "overpass-turbo",
        "timestamp": "2026-11-28T00:00:48Z",
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [10.18, 36.80]},
             "properties": {
                 "@id": "node/100", "name": "Tunis Marine", "name:fr": "Tunis Marine",
                 "public_transport": "stop_position", "highway": "bus_stop",
                 "bus": "yes", "operator": "Transtu",
                 "@relations": [{"role": "stop", "rel": 500,
                                 "reltags": {"type": "route", "route": "bus",
                                             "name": "Ligne 20", "operator": "Transtu"}}],
             }},
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [10.19, 36.81]},
             "properties": {
                 "@id": "node/101", "name": "Marsa", "public_transport": "stop_position",
                 "bus": "yes",
                 "@relations": [{"role": "stop", "rel": 500,
                                 "reltags": {"type": "route", "route": "bus",
                                             "name": "Ligne 20", "operator": "Transtu"}}],
             }},
        ],
    }


def test_geojson_elements_adapter():
    els = conv.elements(_geojson())
    nodes = [e for e in els if e.get("type") == "node"]
    rels = [e for e in els if e.get("type") == "relation"]
    assert len(nodes) == 2
    assert nodes[0]["id"] == 100 and abs(nodes[0]["lat"] - 36.80) < 1e-9
    assert nodes[0]["tags"]["public_transport"] == "stop_position"
    assert len(rels) == 1
    assert rels[0]["id"] == 500 and rels[0]["tags"]["route"] == "bus"
    assert {m["ref"] for m in rels[0]["members"]} == {100, 101}


def test_standalone_line_keeps_route_mode(monkeypatch):
    """The light-rail TGM must not be emitted as a bus line."""
    els = conv.elements(_geojson())
    els[0]["tags"]["public_transport"] = "stop_position"
    els[1]["tags"]["public_transport"] = "stop_position"
    for e in els:
        if e.get("type") == "relation":
            e["tags"]["route"] = "light_rail"
    st = conv.osm_stations(els)
    lines = conv.osm_lines(els, st)
    assert len(lines) == 1 and lines[0]["mode"] == "tram"
    assert lines[0]["directions"][0]["mode"] == "tram"


def test_light_rail_and_trolleybus_are_supported():
    assert conv._mode_from_route({"route": "light_rail"}) == "tram"
    assert conv._mode_from_route({"route": "trolleybus"}) == "bus"
    assert conv._mode_from_route({"route": "ferry"}) == "ferry"
    # Unsupported modes are counted rather than silently dropped.
    rep = {}
    els = [{"type": "relation", "id": 99,
            "tags": {"type": "route", "route": "coach"}, "members": []}]
    conv.osm_lines(els, {}, report=rep)
    assert rep.get("dropped_unsupported_mode:coach") == 1


def test_geojson_yields_stations_and_lines():
    els = conv.elements(_geojson())
    report = {}
    stations = conv.osm_stations(els, report=report)
    lines = conv.osm_lines(els, stations, report=report)
    assert len(stations) == 2
    assert len(lines) == 1
    assert lines[0]["stops"] == ["osm:100", "osm:101"]
    assert lines[0]["mode"] == "bus"
