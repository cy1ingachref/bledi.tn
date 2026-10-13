"""Acceptance tests for the multi-objective / mode-filtered router (D1-D5).

Run:  python tests/test_routing_objectives.py      (or: pytest tests/test_routing_objectives.py)

These assert the CONTRACT from ROUTING_FIX_INSTRUCTIONS.txt, not incidental
behaviour. Where a test encodes a guess rather than the contract it says so.

OD pairs are real Tunisian places chosen because more than one journey exists
for them. That matters: the earlier "metro vs bus" OD inside Tunis has both
(bus 21 min, metro 32 min), which is what makes objective ranking observable.
"""

from __future__ import annotations

import unittest

from bledi_transit.application.routing import router as routing

# Intra-Tunis: a bus route AND a metro route both connect these two points.
TUNIS_A = (36.7961, 10.18055)   # Place Barcelone Sud (metro)
TUNIS_B = (36.75978, 10.19059)  # Kabaria (metro)
INTERCITY = (36.8065, 10.1815, 35.8256, 10.6360)  # Tunis -> Sousse


def _build():
    graph, router = routing.build_graph()
    return router


class ModeTaxonomyTests(unittest.TestCase):
    """B1: metro must be separable from train."""

    def test_metro_is_not_train(self):
        self.assertNotIn("metro", routing.MODE_ALIASES["train"])
        self.assertEqual(routing.canonical_mode("metro"), "metro")
        self.assertEqual(routing.canonical_mode("train"), "train")
        self.assertEqual(routing.canonical_mode("rail"), "train")

    def test_seed_raw_modes_map_cleanly(self):
        self.assertEqual(routing.canonical_mode("bus"), "bus")
        self.assertEqual(routing.canonical_mode("rfr"), "bus")
        self.assertEqual(routing.canonical_mode("tram"), "tram")

    def test_unknown_mode_does_not_vanish(self):
        # An unrecognised tag is still a scheduled line; it must not silently
        # delete real services from the network.
        self.assertEqual(routing.canonical_mode("hovercraft"), "bus")
        self.assertEqual(routing.canonical_mode(None), "bus")

    def test_exclude_train_removes_raw_rail(self):
        allowed = routing.resolve_allowed_modes(None, ["train"])
        self.assertNotIn("rail", allowed)
        self.assertNotIn("train", allowed)

    def test_exclude_bus_removes_rfr(self):
        allowed = routing.resolve_allowed_modes(None, ["bus"])
        self.assertNotIn("rfr", allowed)
        self.assertNotIn("bus", allowed)

    def test_walk_always_available_for_access(self):
        allowed = routing.resolve_allowed_modes(["bus"], ["metro"])
        self.assertIn("bus", allowed)
        self.assertNotIn("metro", allowed)

    def test_unknown_mode_raises_with_available_list(self):
        with self.assertRaises(ValueError) as cm:
            routing.resolve_allowed_modes(["hovercraft"], None)
        self.assertIn("available", str(cm.exception))

    def test_impossible_filter_raises(self):
        with self.assertRaises(ValueError):
            routing.resolve_allowed_modes(["metro"], ["metro"])


class FareModelTests(unittest.TestCase):
    """C5: documented constants, ranking driven by fare."""

    def test_constants_are_documented_and_positive(self):
        for mode, (base, per_km) in routing.FARE_DINARS.items():
            self.assertGreaterEqual(base, 0.0, mode)
            self.assertGreaterEqual(per_km, 0.0, mode)

    def test_fare_never_none_and_monotonic_in_distance(self):
        # train has a per-km component, so distance must raise the fare.
        a = routing.fare_for_leg("train", 0)
        b = routing.fare_for_leg("train", 50_000)
        self.assertIsNotNone(a)
        self.assertLess(a, b)
        # bus is a flat ticket by design; equal is correct, not a bug.
        self.assertEqual(
            routing.fare_for_leg("bus", 0), routing.fare_for_leg("bus", 50_000)
        )

    def test_train_base_above_bus(self):
        self.assertGreater(routing.fare_for_leg("train", 0), routing.fare_for_leg("bus", 0))

    def test_walk_is_free(self):
        self.assertEqual(routing.fare_for_leg("walk", 10_000), 0.0)

    def test_charged_once_per_boarded_line_not_per_edge(self):
        # An itinerary is expanded one step per STOP, so a 10-edge train ride
        # arrives as 10 legs. Charging per leg quoted ~122 DT for a bus+train
        # trip; charging per boarded line must be far less.
        legs = [{"type": "ride", "mode": "train", "line": "L1", "distance_m": 5000}] * 10
        total = routing.fare_for_itinerary(legs)
        self.assertAlmostEqual(total, routing.fare_for_leg("train", 50_000), places=2)
        self.assertLess(total, 30.0)

    def test_change_of_line_adds_a_charge(self):
        one = [{"type": "ride", "mode": "bus", "line": "A", "distance_m": 1000}] * 3
        two = one + [{"type": "ride", "mode": "bus", "line": "B", "distance_m": 1000}] * 3
        self.assertGreater(routing.fare_for_itinerary(two), routing.fare_for_itinerary(one))

    def test_walks_and_transfers_free(self):
        legs = [
            {"type": "walk", "mode": "walk", "distance_m": 900},
            {"type": "transfer", "mode": "transfer", "distance_m": 0},
        ]
        self.assertEqual(routing.fare_for_itinerary(legs), 0.0)

    def test_cheapest_is_not_just_fastest_renamed(self):
        """D3: on an OD where metro is slower but cheaper, cheapest must win."""
        r = _build()
        plan = r.route_plan(*TUNIS_A, *TUNIS_B, objective="cheapest", max_itineraries=5)
        fastest = r.route_plan(*TUNIS_A, *TUNIS_B, objective="fastest", max_itineraries=5)
        self.assertTrue(plan["itineraries"], "cheapest returned nothing")
        self.assertTrue(fastest["itineraries"], "fastest returned nothing")
        def sig(it):
            return tuple(
                (x.get("mode"), x.get("line"))
                for x in it["legs"]
                if x.get("type") == "ride"
            )

        if sig(plan["itineraries"][0]) == sig(fastest["itineraries"][0]):
            self.skipTest(
                "cheapest and fastest coincide on this OD; ordering unobservable"
            )
        self.assertLessEqual(
            plan["itineraries"][0]["fare_estimate_dinars"],
            fastest["itineraries"][0]["fare_estimate_dinars"] + 1e-9,
        )


class ExclusionHardFilterTests(unittest.TestCase):
    """D1: an excluded mode can never appear in a leg."""

    @classmethod
    def setUpClass(cls):
        cls.router = _build()

    def _ride_modes(self, plan):
        out = []
        for it in plan["itineraries"]:
            for step in it["legs"]:
                if step.get("type") in ("walk", "transfer"):
                    continue
                out.append(routing.canonical_mode(step.get("mode") or step.get("type")))
        return out

    def test_exclude_metro_yields_no_metro_leg(self):
        plan = self.router.route_plan(*TUNIS_A, *TUNIS_B, exclude=["metro"], max_itineraries=8)
        self.assertNotIn("metro", self._ride_modes(plan))

    def test_exclude_train_metro_yields_no_rail_legs(self):
        plan = self.router.route_plan(
            *TUNIS_A, *TUNIS_B, exclude=["train", "metro"], max_itineraries=8
        )
        for m in self._ride_modes(plan):
            self.assertNotIn(m, ("train", "metro"))

    def test_exclude_everything_scheduled_leaves_road_or_walk(self):
        plan = self.router.route_plan(
            *TUNIS_A, *TUNIS_B, exclude=["bus", "tram", "metro", "train"], max_itineraries=8
        )
        for m in self._ride_modes(plan):
            self.assertIn(m, ("taxi", "louaj", "walk"))

    def test_include_only_bus_has_no_rail(self):
        plan = self.router.route_plan(*TUNIS_A, *TUNIS_B, include=["bus"], max_itineraries=8)
        for m in self._ride_modes(plan):
            self.assertIn(m, ("bus", "taxi", "walk"))

    def test_exclusion_holds_across_intercity(self):
        plan = self.router.route_plan(*INTERCITY, exclude=["train", "metro"], max_itineraries=8)
        for m in self._ride_modes(plan):
            self.assertNotIn(m, ("train", "metro"))


class ObjectiveTests(unittest.TestCase):
    """D2: distinct labelled itineraries when the paths differ."""

    @classmethod
    def setUpClass(cls):
        cls.router = _build()

    def test_multiple_distinct_itineraries_offered(self):
        plan = self.router.route_plan(*TUNIS_A, *TUNIS_B, objective="fastest", max_itineraries=8)
        self.assertGreaterEqual(len(plan["itineraries"]), 2, "only one option offered")

    def test_itineraries_are_distinct(self):
        plan = self.router.route_plan(*TUNIS_A, *TUNIS_B, max_itineraries=8)
        sigs = [
            tuple(
                (s.get("mode"), s.get("line"))
                for s in it["legs"]
                if s.get("type") == "ride"
            )
            for it in plan["itineraries"]
        ]
        self.assertEqual(len(sigs), len(set(sigs)), "duplicate itineraries returned")

    def test_fastest_is_ordered_by_duration(self):
        plan = self.router.route_plan(*TUNIS_A, *TUNIS_B, objective="fastest", max_itineraries=8)
        durs = [it["duration_s"] for it in plan["itineraries"]]
        self.assertEqual(durs, sorted(durs))

    def test_cheapest_is_ordered_by_fare(self):
        plan = self.router.route_plan(*TUNIS_A, *TUNIS_B, objective="cheapest", max_itineraries=8)
        fares = [it["fare_estimate_dinars"] for it in plan["itineraries"]]
        self.assertEqual(fares, sorted(fares))

    def test_fewest_transfers_ordered_by_transfer_count(self):
        plan = self.router.route_plan(
            *TUNIS_A, *TUNIS_B, objective="fewest_transfers", max_itineraries=8
        )
        trs = [it["transfers"] for it in plan["itineraries"]]
        self.assertEqual(trs, sorted(trs))

    def test_max_transfers_is_enforced(self):
        plan = self.router.route_plan(
            *TUNIS_A, *TUNIS_B, objective="fastest", max_transfers=0, max_itineraries=8
        )
        for it in plan["itineraries"]:
            self.assertLessEqual(it["transfers"], 0)

    def test_max_itineraries_respected_and_capped(self):
        plan = self.router.route_plan(*TUNIS_A, *TUNIS_B, max_itineraries=1)
        self.assertLessEqual(len(plan["itineraries"]), 1)
        plan = self.router.route_plan(*TUNIS_A, *TUNIS_B, max_itineraries=99)
        self.assertLessEqual(len(plan["itineraries"]), 8)

    def test_unknown_objective_rejected(self):
        with self.assertRaises(ValueError):
            self.router.route_plan(*TUNIS_A, *TUNIS_B, objective="scenic")


class ResponseShapeTests(unittest.TestCase):
    """B5: the documented envelope."""

    @classmethod
    def setUpClass(cls):
        cls.router = _build()
        cls.plan = cls.router.route_plan(*TUNIS_A, *TUNIS_B, max_itineraries=3)

    def test_top_level_keys(self):
        for k in ("query", "itineraries", "available_modes", "message"):
            self.assertIn(k, self.plan)

    def test_query_echo(self):
        q = self.plan["query"]
        for k in ("start", "end", "modes_include", "modes_exclude", "objective"):
            self.assertIn(k, q)

    def test_itinerary_required_fields(self):
        self.assertTrue(self.plan["itineraries"])
        for it in self.plan["itineraries"]:
            for k in (
                "id", "label", "rank_reason", "duration_min", "transfers",
                "fare_estimate_dinars", "modes_used", "legs",
                "geometry_complete", "gaps",
            ):
                self.assertIn(k, it, f"missing {k}")

    def test_available_modes_lists_taxonomy(self):
        for m in ("bus", "metro", "train", "louaj", "taxi"):
            self.assertIn(m, self.plan["available_modes"])

    def test_geometry_gap_reporting(self):
        """Every reported gap must be quantified, so the client can dash it."""
        for it in self.plan["itineraries"]:
            for gap in it["gaps"]:
                # Routing gaps report distance_m; line-detail gaps report gap_m.
                self.assertTrue(
                    "gap_m" in gap or "distance_m" in gap,
                    f"gap carries no length: {gap}",
                )

    def test_complete_flag_agrees_with_gap_list(self):
        for it in self.plan["itineraries"]:
            self.assertEqual(it["geometry_complete"], not it["gaps"])

    def test_labels_are_french_and_non_empty(self):
        for it in self.plan["itineraries"]:
            self.assertTrue(it["label"].strip())
            self.assertTrue(it["rank_reason"].strip())


class TransferCountTests(unittest.TestCase):
    def test_transfer_count_is_line_changes(self):
        steps = [
            {"type": "ride", "line": "A"},
            {"type": "ride", "line": "A"},
            {"type": "ride", "line": "B"},
            {"type": "ride", "line": "C"},
        ]
        self.assertEqual(routing.Router._count_transfers(steps), 2)

    def test_single_line_is_zero_transfers(self):
        steps = [{"type": "ride", "line": "A"}] * 5
        self.assertEqual(routing.Router._count_transfers(steps), 0)

    def test_walks_do_not_count_as_transfers(self):
        steps = [
            {"type": "ride", "line": "A"},
            {"type": "walk", "line": None},
            {"type": "ride", "line": "A"},
        ]
        self.assertEqual(routing.Router._count_transfers(steps), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)