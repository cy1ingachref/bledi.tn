"""The corridor file: validation, and unverified entries staying out by default."""
from __future__ import annotations

from bledi_transit.adapters.louage_corridors import merge_corridors

STATIONS = [
    {"id": "hub", "name": "Hub", "lat": 36.81, "lon": 10.16, "mode": "louage"},
    {"id": "end", "name": "End", "lat": 37.04, "lon": 9.67, "mode": "louage"},
]
DATA = {
    "stops": [{"id": "mid", "name": "Djedeida", "lat": 36.85, "lon": 9.93}],
    "corridors": [{"id": "a", "number": "L31", "stops": ["hub", "mid", "end"], "verified": True, "wait_min": 15}],
}


def test_a_verified_corridor_becomes_a_line_with_its_inline_stop():
    st, ln, rep = merge_corridors(DATA, STATIONS, [])
    assert rep.loaded == ["a"] and rep.stops_added == ["mid"]
    line = ln[0]
    assert line["id"] == "corridor_a" and line["mode"] == "louage" and line["stations"] == ["hub", "mid", "end"]
    assert line["wait_s"] == 900.0 and line["operator"] == "louage"
    assert {s["id"] for s in st} == {"hub", "end", "mid"}


def test_unverified_corridors_are_skipped_unless_opted_in():
    draft = {**DATA, "corridors": [{**DATA["corridors"][0], "verified": False}]}
    _, ln, rep = merge_corridors(draft, STATIONS, [])
    assert not ln and rep.skipped == [("a", "unverified")]
    _, ln, rep = merge_corridors(draft, STATIONS, [], include_unverified=True)
    assert len(ln) == 1


def test_bad_entries_are_rejected_with_a_reason():
    bad = {
        "stops": [{"id": "far", "name": "Paris", "lat": 48.8, "lon": 2.3}],
        "corridors": [
            {"id": "one_stop", "stops": ["hub"], "verified": True},
            {"id": "ghost", "stops": ["hub", "nope"], "verified": True},
            {"id": "mode", "stops": ["hub", "end"], "mode": "rocket", "verified": True},
        ],
    }
    st, ln, rep = merge_corridors(bad, STATIONS, [])
    reasons = dict(rep.skipped)
    assert not ln and len(st) == 2
    assert "coordinates inside Tunisia" in reasons["far"]
    assert "2 stops" in reasons["one_stop"] and "unknown stop ids" in reasons["ghost"] and "mode" in reasons["mode"]


def test_rural_shuttle_lines_use_the_bus_mode():
    d = {"corridors": [{"id": "r", "mode": "bus", "stops": ["hub", "end"], "verified": True}]}
    _, ln, _ = merge_corridors(d, STATIONS, [])
    assert ln[0]["mode"] == "bus" and ln[0]["operator"] == "Transport rural"


def test_inputs_are_not_mutated():
    st, ln = list(STATIONS), []
    merge_corridors(DATA, st, ln)
    assert st == STATIONS and ln == []
