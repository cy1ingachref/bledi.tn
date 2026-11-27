"""WP2 converter tests: synthetic Overpass fixture proves the review findings.

The fixture contains: stop nodes tagged only with bus=yes, a stop_area merging
two platform nodes, two route relations for one route_master (both directions),
a stop shared by two lines, an unnamed stop, an out-of-bounds node, and a
one-stop line. Each test maps to a finding in the open-data cutover handoff §3.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import rebuild_seed_from_osm as conv  # noqa: E402


@pytest.fixture
def fixture():
    return {
        "elements": [
            # Bus stop tagged only with bus=yes (finding 1).
            {"type": "node", "id": 1, "lat": 36.80, "lon": 10.18,
             "tags": {"name": "Tunis Marine", "public_transport": "stop_position", "bus": "yes"}},
            # stop_position + platform for the same stop (finding 2).
            {"type": "node", "id": 2, "lat": 36.81, "lon": 10.19,
             "tags": {"name": "Le Bac", "public_transport": "stop_position", "bus": "yes"}},
            {"type": "node", "id": 3, "lat": 36.8101, "lon": 10.1901,
             "tags": {"name": "Le Bac", "public_transport": "platform", "bus": "yes"}},
            {"type": "relation", "id": 100, "tags": {"type": "public_transport:stop_area", "name": "Le Bac"},
             "members": [{"type": "node", "ref": 2}, {"type": "node", "ref": 3}]},
            # Unnamed stop (finding 6).
            {"type": "node", "id": 4, "lat": 36.82, "lon": 10.20,
             "tags": {"public_transport": "stop_position", "highway": "bus_stop"}},
            # Out-of-bounds node (finding 7).
            {"type": "node", "id": 5, "lat": 48.85, "lon": 2.35,
             "tags": {"name": "Paris", "public_transport": "stop_position", "bus": "yes"}},
            # Rail station (finding 1 - railway=station).
            {"type": "node", "id": 6, "lat": 36.84, "lon": 10.32,
             "tags": {"name": "Carthage", "railway": "station", "public_transport": "station"}},
            # route_master + two directional route relations (finding 4).
            {"type": "relation", "id": 200, "tags": {"type": "route_master", "route": "bus", "ref": "M1", "name": "Line 1"},
             "members": [{"type": "relation", "ref": 201}, {"type": "relation", "ref": 202}]},
            {"type": "relation", "id": 201,
             "tags": {"type": "route", "route": "bus", "ref": "M1", "name": "Line 1 →", "operator": "Transtu"},
             "members": [{"type": "node", "ref": 1}, {"type": "node", "ref": 2}]},
            {"type": "relation", "id": 202,
             "tags": {"type": "route", "route": "bus", "ref": "M1", "name": "Line 1 ←", "operator": "Transtu"},
             "members": [{"type": "node", "ref": 2}, {"type": "node", "ref": 1}]},
            # Second line sharing stop 2 (finding 3).
            {"type": "relation", "id": 203,
             "tags": {"type": "route", "route": "bus", "ref": "M2", "name": "Line 2", "operator": "Transtu"},
             "members": [{"type": "node", "ref": 2}, {"type": "node", "ref": 6}]},
            # One-stop line (finding 5).
            {"type": "relation", "id": 204,
             "tags": {"type": "route", "route": "bus", "ref": "M3", "name": "Short line"},
             "members": [{"type": "node", "ref": 1}]},
        ]
    }


def test_mode_from_bus_flag(fixture):
    stations = conv.osm_stations(fixture["elements"])
    assert stations["osm:1"]["mode"] == "bus"
    assert stations["osm:4"]["mode"] == "bus"


def test_duplicate_platforms_merged(fixture):
    stations = conv.osm_stations(fixture["elements"])
    assert ("osm:2" in stations) != ("osm:3" in stations)  # one canonical station
    assert "osm:2" in stations or "osm:3" in stations


def test_lines_served_complete(fixture):
    stations = conv.osm_stations(fixture["elements"])
    lines = conv.osm_lines(fixture["elements"], stations)
    conv.link_lines_served(stations, lines)
    served = stations["osm:2"]["lines_served"]
    assert len(served) >= 2  # shared by line 1 and line 2


def test_route_master_groups_directions(fixture):
    stations = conv.osm_stations(fixture["elements"])
    lines = conv.osm_lines(fixture["elements"], stations)
    m1 = [ln for ln in lines if ln.get("number") == "M1"]
    assert len(m1) == 1  # two directions grouped into one line
    assert {v["direction"] for v in m1[0]["directions"]} == {"forward", "backward"}


def test_short_line_dropped(fixture):
    stations = conv.osm_stations(fixture["elements"])
    lines = conv.osm_lines(fixture["elements"], stations)
    assert all(len(ln["stops"]) >= 2 for ln in lines)
    assert not any("M3" in (ln.get("number") or "") for ln in lines)


def test_out_of_bounds_rejected(fixture):
    stations = conv.osm_stations(fixture["elements"])
    assert "osm:5" not in stations  # Paris is outside the Tunisia box


def test_unnamed_flagged(fixture):
    stations = conv.osm_stations(fixture["elements"])
    assert stations["osm:4"].get("unnamed") is True


def test_all_records_odbl(fixture):
    stations = conv.osm_stations(fixture["elements"])
    lines = conv.osm_lines(fixture["elements"], stations)
    assert all(s["license_status"] == "odbl" for s in stations.values())
    assert all(ln["license_status"] == "odbl" for ln in lines)
