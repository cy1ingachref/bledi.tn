"""WP4 tests: per-mode defaults are explicit estimates; official overrides win."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from bledi_transit.domain.mode_defaults import MODE_DEFAULTS, as_dict, defaults_for  # noqa: E402
from bledi_transit.application.routing.planner import _uses_estimated_defaults  # noqa: E402


def test_every_mode_has_a_documented_estimate():
    assert MODE_DEFAULTS
    for name, d in MODE_DEFAULTS.items():
        assert d.estimated is True, name
        assert d.source, name
        assert d.headway_s >= 0 and d.speed_kmh > 0 and d.fare_dinars >= 0, name


def test_defaults_are_exposed_as_a_dict():
    d = as_dict("bus")
    assert d["estimated"] is True
    assert d["headway_s"] == 600.0
    assert "source" in d and d["source"]


def test_unknown_mode_falls_back_to_bus_estimate():
    assert defaults_for("no-such-mode") == defaults_for("unknown")


def test_itinerary_without_official_marker_is_estimated():
    assert _uses_estimated_defaults({"steps": [{"mode": "bus"}]}) is True
    assert _uses_estimated_defaults({}) is True


def test_official_and_license_tagged_steps_override_estimates():
    assert _uses_estimated_defaults({"steps": [{"mode": "bus", "official": True}]}) is False
    assert _uses_estimated_defaults({"steps": [{"mode": "bus", "license_status": "official-public"}]}) is False
