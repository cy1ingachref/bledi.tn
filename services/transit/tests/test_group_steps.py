"""group_steps: one segment per ride instead of one entry per stop."""
from __future__ import annotations

from bledi_transit.application.routing.planner import group_steps


def _ride(a, b, wait=0.0, dur=2.0, line="metro_x"):
    return {
        "type": "ride", "mode": "metro", "line": line, "from_name": a, "to_name": b,
        "from": {"lat": 0, "lon": 0}, "to": {"lat": 0, "lon": 1}, "from_id": a, "to_id": b,
        "distance_m": 800, "duration_min": dur + wait, "wait_min": wait,
        "geometry": [[0, 0], [0, 1]], "needs_geometry": False,
    }


def test_consecutive_hops_on_one_line_become_one_segment():
    steps = [
        {"type": "walk", "distance_m": 100, "duration_min": 1.0, "geometry": []},
        _ride("A", "B", wait=7.0), _ride("B", "C"), _ride("C", "D"),
        {"type": "walk", "distance_m": 50, "duration_min": 1.0, "geometry": []},
    ]
    segs = group_steps(steps, {"metro_x": {"label": "TGM", "operator": "Transtu"}})
    assert [s["type"] for s in segs] == ["walk", "ride", "walk"]
    ride = segs[1]
    assert (ride["from_name"], ride["to_name"], ride["stops"]) == ("A", "D", 3)
    assert ride["wait_min"] == 7.0 and ride["ride_min"] == 6.0 and ride["duration_min"] == 13.0
    assert ride["line_label"] == "TGM"
    assert ride["distance_m"] == 2400


def test_a_change_of_line_starts_a_new_segment():
    segs = group_steps([_ride("A", "B"), _ride("B", "C", line="other")])
    assert len(segs) == 2
