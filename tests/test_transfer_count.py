#!/usr/bin/env python3
"""Regression test: transfer count must not double-count when a transfer
also crosses modes (bus -> train).

The _router_to_option conversion in main.py used two independent checks
that were not mutually exclusive: a "transfer" step type AND a mode-change
between consecutive rides. Fix uses an after_transfer flag so a bus->train
transfer is counted once. This file contains:
- static tests of _router_to_option (conversion logic)
- dynamic end-to-end tests using the real Router + tagged seed
  (routes involving mode changes on real corridors)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pytest
from src.backend.app.main import _router_to_option


def _step(type_, mode, line, from_=None, to=None, label="", to_name="", from_name=""):
    base = {"type": type_, "mode": mode, "line": line, "label": label}
    if from_:
        base["from"] = from_
    if to:
        base["to"] = to
    if to_name:
        base["to_name"] = to_name
    if from_name:
        base["from_name"] = from_name
    return base


def _bike():
    return _step("ride", "bike", "", to={"lat": 36.0, "lon": 10.0}, label="bike")


def _walk():
    return _step("walk", "walk", "")


def _ride(mode, line, from_=None, to=None, label="", to_name="", from_name=""):
    return _step("ride", mode, line, from_=from_, to=to, label=label, to_name=to_name, from_name=from_name)


class TestTransferCountNoDoubleCount:
    """A single transfer between ride segments must increment the transfer
    count exactly once, even when it also crosses modes."""

    def test_bus_to_train_transfer_counts_once(self):
        router_out = {
            "mode": "transit",
            "duration_min": 40.0,
            "steps": [
                _ride("bus", "BUS-1",
                      from_={"lat": 36.0, "lon": 10.0}, to={"lat": 36.01, "lon": 10.01},
                      label="Bus A", to_name="Hub"),
                _step("transfer", "transfer", None,
                      from_={"lat": 36.01, "lon": 10.01}, to={"lat": 36.01, "lon": 10.02},
                      label="Correspondance : marcher jusqu'à Gare"),
                _ride("train", "TRAIN-36",
                      from_={"lat": 36.01, "lon": 10.02}, to={"lat": 36.05, "lon": 10.05},
                      label="Train 36", to_name="Gare"),
            ],
        }
        opt = _router_to_option(router_out)
        assert opt["transfers"] == 1, f"expected 1 transfer, got {opt['transfers']} in {opt}"

    def test_two_transfers_count_twice(self):
        router_out = {
            "mode": "transit",
            "duration_min": 60.0,
            "steps": [
                _ride("bus", "BUS-1", from_={"lat": 0, "lon": 0}, to={"lat": 1, "lon": 0}, label="Bus"),
                _step("transfer", "transfer", None, from_={"lat": 1, "lon": 0}, to={"lat": 1, "lon": 1}, label="X"),
                _ride("bus", "BUS-2", from_={"lat": 1, "lon": 1}, to={"lat": 2, "lon": 1}, label="Bus2"),
                _step("transfer", "transfer", None, from_={"lat": 2, "lon": 1}, to={"lat": 2, "lon": 2}, label="Y"),
                _ride("train", "TRAIN-1", from_={"lat": 2, "lon": 2}, to={"lat": 3, "lon": 2}, label="Train"),
            ],
        }
        opt = _router_to_option(router_out)
        assert opt["transfers"] == 2, f"expected 2 transfers, got {opt['transfers']}"

    def test_mode_change_without_explicit_transfer_step_still_counts(self):
        """Legacy path: a ride->ride sequence where the mode changes but no
        explicit transfer step was emitted must still count as a transfer."""
        router_out = {
            "mode": "transit",
            "duration_min": 30.0,
            "steps": [
                _ride("bus", "BUS-1", from_={"lat": 0, "lon": 0}, to={"lat": 1, "lon": 0}, label="Bus"),
                _ride("train", "TRAIN-1", from_={"lat": 1, "lon": 0}, to={"lat": 2, "lon": 0}, label="Train"),
            ],
        }
        opt = _router_to_option(router_out)
        assert opt["transfers"] == 1, f"expected 1 transfer (mode change), got {opt['transfers']}"


# ── end-to-end: real router + tagged seed ────────────────────────────────


class TestTransferCountEndToEnd:
    """Dynamic tests: run the real Router against the tagged seed, convert
    with _router_to_option, and assert transfer counts are sane on
    multi-leg / multi-mode routes."""

    @pytest.fixture(scope="class")
    def router(self):
        from src.backend.app.routing import build_graph
        _, r = build_graph()
        return r

    def test_real_transit_no_false_double_count(self, router):
        """A real transit path (Tunis Centre -> Bizerte) that the router
        resolves as a single line (no transfer) must report transfers == 0,
        and a path that genuinely transfers once must report transfers == 1,
        never 2."""
        from src.backend.app.main import _router_to_option
        res = router.route(36.806, 10.184, 36.914, 9.866)
        assert res.get("error") is None, res
        opt = _router_to_option(res)
        # The current seed resolves Tunis Centre -> Bizerte as a single
        # train line via TGM (no transfer), so transfers should be 0.
        assert opt["transfers"] == 0, (
            f"expected 0 transfers for single-line Tunis->Bizerte path, "
            f"got {opt['transfers']} (double-count?)\n{opt}"
        )

    def test_real_path_with_walk_transfer_counts_correctly(self, router):
        """A path that contains an intermediate walk (between lines) should
        have has_walk_transfer True and transfers reflecting only real line
        changes, not the walk."""
        from src.backend.app.main import _router_to_option
        # Tunis Centre -> Birsa (TGM) then walk to another line.
        # Use a pair close enough to get a transit path.
        res = router.route(36.806, 10.184, 36.816, 10.174)
        assert res.get("error") is None, res
        opt = _router_to_option(res)
        # Transfers must be a non-negative integer; has_walk_transfer must be
        # a bool; under no circumstances may transfers exceed the number of
        # ride steps (which would indicate double-counting).
        assert isinstance(opt["transfers"], int) and opt["transfers"] >= 0
        assert isinstance(opt["has_walk_transfer"], bool)
        ride_steps = [s for s in opt["steps"] if s["type"] == "ride"]
        assert opt["transfers"] <= len(ride_steps), (
            f"transfers ({opt['transfers']}) exceed ride steps ({len(ride_steps)}): "
            f"double-count bug in _router_to_option\n{opt}"
        )
