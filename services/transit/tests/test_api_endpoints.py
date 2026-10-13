"""API-level acceptance tests for the new endpoints (D1-D5, D8).

Run:  python tests/test_api_endpoints.py

These drive the real FastAPI app in-process (no server, no network) so they
assert the wire contract: status codes, field names and the hard exclusion
guarantee, exactly as a client sees them.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from bledi_transit.domain.modes import canonical_mode
from bledi_transit.main import app

TUNIS_A = (36.7961, 10.18055)
TUNIS_B = (36.75978, 10.19059)


def plan_url(a=TUNIS_A, b=TUNIS_B, **params):
    q = {
        "start_lat": a[0], "start_lon": a[1],
        "end_lat": b[0], "end_lon": b[1],
    }
    q.update({k: v for k, v in params.items() if v is not None})
    parts = [f"{k}={v}" for k, v in q.items()]
    return "/api/v1/route/plan?" + "&".join(parts)


class PlanEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def test_health_still_works(self):
        r = self.c.get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_plan_envelope(self):
        r = self.c.get(plan_url())
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for k in ("query", "itineraries", "available_modes", "message"):
            self.assertIn(k, d)
        self.assertTrue(d["itineraries"])

    def test_d1_exclude_metro_no_metro_leg(self):
        r = self.c.get(plan_url(modes_exclude="metro", max_itineraries=8))
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["itineraries"])
        for it in d["itineraries"]:
            self.assertNotIn("metro", it["modes_used"])
            for leg in it["legs"]:
                if leg.get("type") in ("walk", "transfer"):
                    continue
                self.assertNotEqual(canonical_mode(leg.get("mode")), "metro")

    def test_d1_exclude_train_metro_intercity(self):
        r = self.c.get(
            plan_url((36.8065, 10.1815), (35.8256, 10.6360),
                     modes_exclude="train,metro", max_itineraries=8)
        )
        self.assertEqual(r.status_code, 200)
        for it in r.json()["itineraries"]:
            self.assertNotIn("train", it["modes_used"])
            self.assertNotIn("metro", it["modes_used"])

    def test_unknown_mode_is_400_with_available_list(self):
        r = self.c.get(plan_url(modes_include="hovercraft"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("available", r.json()["detail"])

    def test_bad_objective_is_400(self):
        r = self.c.get(plan_url(objective="scenic"))
        self.assertEqual(r.status_code, 400)

    def test_max_itineraries_validation(self):
        self.assertEqual(self.c.get(plan_url(max_itineraries=0)).status_code, 422)
        self.assertEqual(self.c.get(plan_url(max_itineraries=9)).status_code, 422)

    def test_d3_cheapest_sorted_by_fare(self):
        r = self.c.get(plan_url(objective="cheapest", max_itineraries=8))
        fares = [it["fare_estimate_dinars"] for it in r.json()["itineraries"]]
        self.assertEqual(fares, sorted(fares))

    def test_d2_objectives_produce_orderings(self):
        for obj in ("fastest", "fewest_transfers", "cheapest"):
            r = self.c.get(plan_url(objective=obj, max_itineraries=8))
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["itineraries"], obj)


class StationDetailTests(unittest.TestCase):
    """D4."""

    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def test_station_detail_shape(self):
        r = self.c.get("/api/v1/stations/place_barcelone_sud")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for k in ("id", "name", "lat", "lon", "modes", "lines", "count"):
            self.assertIn(k, d)
        self.assertTrue(d["lines"])

    def test_line_entries_have_stable_id_and_mode(self):
        d = self.c.get("/api/v1/stations/place_barcelone_sud").json()
        for li in d["lines"]:
            for k in ("line_id", "mode", "mode_label", "stops_count"):
                self.assertIn(k, li)
            self.assertIn(li["mode"], ("bus", "tram", "metro", "train", "louaj", "taxi"))

    def test_lines_really_contain_this_stop(self):
        """Built from the line -> stops index, so this must hold exactly."""
        d = self.c.get("/api/v1/stations/place_barcelone_sud").json()
        from bledi_transit.main import LINE_BY_ID

        for li in d["lines"]:
            ln = LINE_BY_ID.get(li["line_id"])
            self.assertIsNotNone(ln, li["line_id"])
            stops = ln.get("stations") or ln.get("stops") or []
            self.assertIn("place_barcelone_sud", stops)

    def test_unknown_station_404(self):
        self.assertEqual(self.c.get("/api/v1/stations/nope_not_real").status_code, 404)

    def test_modes_sorted_in_display_order(self):
        """Find a real multi-mode stop and assert the ordering contract."""
        from bledi_transit.domain.modes import USER_MODES
        from bledi_transit.main import ROUTER

        target = None
        for sid, lids in ROUTER.lines_by_station.items():
            modes = {
                ROUTER.user_mode_of_line.get(lid)
                for lid in lids
                if lid in ROUTER.user_mode_of_line
            }
            modes.discard(None)
            if len(modes) >= 2:
                target = (sid, modes)
                break
        self.assertIsNotNone(target, "no multi-mode station in the seed")
        sid = target[0]
        r = self.c.get(f"/api/v1/stations/{sid}")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        order = [USER_MODES.index(m) for m in d["modes"] if m in USER_MODES]
        self.assertEqual(order, sorted(order))
        self.assertGreaterEqual(len(d["modes"]), 2)


class LineDetailTests(unittest.TestCase):
    """D5."""

    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def test_line_detail_has_ordered_stops(self):
        r = self.c.get("/api/v1/lines/train_23_sncft")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertGreaterEqual(d["count"], 2)
        names = [s["name"] for s in d["stops"]]
        self.assertTrue(all(names))
        self.assertEqual(names, [s["name"] for s in d["stops"]])

    def test_geometry_contract_present(self):
        d = self.c.get("/api/v1/lines/train_23_sncft").json()
        for k in ("geometry", "geometry_complete", "geometry_segments", "gaps"):
            self.assertIn(k, d)
        self.assertEqual(len(d["geometry_segments"]), max(0, d["count"] - 1))

    def test_incomplete_geometry_is_flagged_not_invented(self):
        """A line missing track must report gaps and NOT return a LineString."""
        d = self.c.get("/api/v1/lines/train_23_sncft").json()
        if not d["geometry_complete"]:
            self.assertIsNone(d["geometry"])
            self.assertTrue(d["gaps"], "incomplete geometry must list its gaps")
            for g in d["gaps"]:
                self.assertIn("gap_m", g)

    def test_complete_geometry_is_a_linestring(self):
        d = self.c.get("/api/v1/lines/bus_873_5c").json()
        if d["geometry_complete"]:
            self.assertIsNotNone(d["geometry"])
            self.assertEqual(d["geometry"]["type"], "LineString")
            coords = d["geometry"]["coordinates"]
            self.assertGreaterEqual(len(coords), 2)
            # GeoJSON order is [lon, lat]; Tunis is ~10E / 36N.
            lon, lat = coords[0]
            self.assertTrue(9.0 < lon < 11.5, f"lon out of range: {lon}")
            self.assertTrue(35.0 < lat < 38.0, f"lat out of range: {lat}")

    def test_segments_flag_each_pair(self):
        d = self.c.get("/api/v1/lines/train_23_sncft").json()
        for seg in d["geometry_segments"]:
            for k in ("from_stop_id", "to_stop_id", "has_geometry", "needs_geometry", "gap_m"):
                self.assertIn(k, seg)


class BackwardCompatTests(unittest.TestCase):
    """C3: existing clients must not break."""

    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def test_legacy_transit_endpoint_still_200(self):
        r = self.c.get(
            "/api/v1/route/transit?start_lat=36.7961&start_lon=10.18055"
            "&end_lat=36.75978&end_lon=10.19059"
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("best_fastest", r.json())

    def test_legacy_stations_endpoint_still_200(self):
        self.assertEqual(self.c.get("/api/v1/stations").status_code, 200)

    def test_legacy_lines_endpoint_still_200(self):
        self.assertEqual(self.c.get("/api/v1/lines").status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)