#!/usr/bin/env python3
"""Seed integrity checks.

Reports (does not fail on) data-quality issues:
- duplicate station IDs
- line stop references that do not resolve
- coordinates outside Tunisia's bounding box
- lines with fewer than 2 valid stops
- count of stations with mode "unknown"

Fails on the quarantine invariant, because a quarantined station is a silent
behavioural change to the API surface and nothing else in this file would catch
it being reverted or half-applied.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

SEED_PATH = REPO_ROOT / "data" / "seed_all_tunisia_routes.json"
SEED_TAGED_PATH = REPO_ROOT / "data" / "seed_all_tunisia_routes.tagged.json"
_SEED_PATH = SEED_TAGED_PATH if SEED_TAGED_PATH.exists() else SEED_PATH

# Tunisia bounding box (approx).
TUNISIA_LAT_MIN = 30.0
TUNISIA_LAT_MAX = 37.5
TUNISIA_LON_MIN = 7.5
TUNISIA_LON_MAX = 12.0


@pytest.fixture(scope="session")
def seed():
    import json
    with _SEED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


class TestSeedIntegrity:
    def test_no_duplicate_station_ids(self, seed):
        stations = seed.get("stations", [])
        ids = [s.get("id") for s in stations if s.get("id")]
        dupes = [k for k, v in Counter(ids).items() if v > 1]
        assert not dupes, f"Duplicate station ids: {dupes[:10]}"

    def test_all_line_stop_references_resolve(self, seed):
        stations = seed.get("stations", [])
        sids = {s["id"] for s in stations if s.get("id")}
        unresolved: list[tuple[str, str]] = []
        for ln in seed.get("lines", []):
            stops = ln.get("stations") or ln.get("stops") or []
            for sid in stops:
                if sid and sid not in sids:
                    unresolved.append((ln.get("id", "?"), sid))
        assert not unresolved, f"Unresolved stop ids: {unresolved[:20]}"

    def test_coordinates_inside_tunisia_bbox(self, seed):
        out_of_bounds: list[tuple[str, float, float]] = []
        for s in seed.get("stations", []):
            lat, lon = s.get("lat"), s.get("lon")
            if lat is None or lon is None or lat == 0 or lon == 0:
                continue
            if not (TUNISIA_LAT_MIN <= lat <= TUNISIA_LAT_MAX and TUNISIA_LON_MIN <= lon <= TUNISIA_LON_MAX):
                out_of_bounds.append((s.get("id", "?"), lat, lon))
        # We report rather than fail for borderline cases.
        if out_of_bounds:
            print(f"\n{len(out_of_bounds)} stations outside Tunisia bbox (reported, not failed):")
            for sid, lat, lon in out_of_bounds[:10]:
                print(f"  {sid}: ({lat:.4f}, {lon:.4f})")

    def test_no_line_with_fewer_than_two_valid_stops(self, seed):
        """Nothing may be unroutable *silently*.

        A line with fewer than 2 resolvable stops is not a graph edge, so it can
        never appear in a route. That is fine when it is known and recorded --
        the 117 BizerteConnect lines have no stops because that API publishes no
        stops endpoint -- but it is a data bug when it is not.

        So this test does two things, and the second is what stops the first
        from being a loophole:

        1. every line with <2 valid stops must be explicitly ``routable: false``;
        2. every line that is explicitly ``routable: false`` must actually have
           <2 valid stops.

        Without (2), marking a perfectly good line ``routable: false`` would
        hide it from (1) and the test would pass while the line silently
        vanished from routing. Without (1), a new import could add unroutable
        lines and nothing would notice.
        """
        stations = {s["id"] for s in seed.get("stations", []) if s.get("id")}

        unmarked_short: list[tuple[str, int]] = []
        wrongly_marked: list[str] = []

        for ln in seed.get("lines", []):
            stops = ln.get("stations") or ln.get("stops") or []
            valid = [s for s in stops if s in stations]
            lid = ln.get("id", ln.get("number", "?"))
            marked_unroutable = ln.get("routable") is False

            if len(valid) < 2 and not marked_unroutable:
                # Unroutable but silent: this is the failure mode.
                unmarked_short.append((lid, len(valid)))

            if marked_unroutable and len(valid) >= 2:
                # Marked unroutable but demonstrably routable: the marker is
                # hiding a working line from the graph.
                wrongly_marked.append(lid)

        assert not unmarked_short, (
            "Lines with <2 valid stops that are NOT marked routable=false "
            f"(mark them with scripts/mark_unroutable_lines.py): {unmarked_short[:20]}"
        )
        assert not wrongly_marked, (
            "Lines marked routable=false that actually have >=2 valid stops, "
            f"so the marker is hiding them from routing: {wrongly_marked[:20]}"
        )

    def test_known_unroutable_lines_keep_their_data(self, seed):
        """The unroutable lines must stay, with their data intact.

        The cheapest way to make the test above pass is to delete the 117
        BizerteConnect lines. That would throw away the destination names and
        the departure times the UI uses. This pins that the data survives the
        marker.

        Note the schedule assertion is about the KEYS still being present, not
        about them being non-empty: 2 of the 117 lines came back from the
        BizerteConnect API with genuinely empty departure arrays. That is a gap
        in the upstream data, not something the marking script caused, so the
        test must not pretend otherwise.
        """
        unroutable = [ln for ln in seed.get("lines", []) if ln.get("routable") is False]
        assert unroutable, "expected the known unroutable lines to be present"

        for ln in unroutable:
            lid = ln.get("id", "?")
            # Identity: what the UI needs to show the line at all.
            for field in ("origin", "destination", "name", "number"):
                assert ln.get(field), f"{lid}: lost its {field}"
            # Schedule keys must survive, even where upstream had no times.
            assert "departures" in ln, f"{lid}: lost the departures key"
            assert "return_departures" in ln, f"{lid}: lost the return_departures key"

        # The overwhelming majority do carry real times; if a future change
        # wiped them, this catches it while tolerating the two known gaps.
        with_times = [ln for ln in unroutable if ln.get("departures")]
        assert len(with_times) >= 100, (
            f"only {len(with_times)} of {len(unroutable)} unroutable lines still "
            "carry departure times; the schedules look wiped"
        )

        # The count is recorded in metadata, so it cannot drift unnoticed.
        meta_count = seed.get("metadata", {}).get("unroutable_lines", {}).get("count")
        assert meta_count == len(unroutable), (
            f"metadata says {meta_count} unroutable lines but the rows say "
            f"{len(unroutable)}"
        )

    def test_report_unknown_mode_stations(self, seed):
        stations = seed.get("stations", [])
        unknown = [s for s in stations if (s.get("mode") or "").lower() == "unknown"]
        # Report the count; do NOT fail the test.
        print(f"\nStations with mode='unknown': {len(unknown)} of {len(stations)}")
        if unknown:
            print("  Examples:")
            for s in unknown[:5]:
                print(f"    {s.get('id')}: {s.get('name')}")

    def test_quarantined_stations_are_well_formed(self, seed):
        """A quarantined row must be inert: no coords, a reason, an audit trail.

        The backend skips any station with null/zero coordinates, so nulling them
        is what removes the point from the map. If a future edit quarantines a row
        without nulling the coordinates the bad point silently stays on the map
        while claiming to be fixed.
        """
        bad: list[str] = []
        for s in seed.get("stations", []):
            if not s.get("quarantined"):
                continue
            sid = s.get("id", "?")
            if s.get("lat") is not None or s.get("lon") is not None:
                bad.append(f"{sid}: coordinates still set ({s.get('lat')}, {s.get('lon')})")
            if not s.get("quarantine_reason"):
                bad.append(f"{sid}: no quarantine_reason")
            if not s.get("quarantined_from"):
                bad.append(f"{sid}: no quarantined_from to audit the original position")
        assert not bad, "Malformed quarantine rows:\n  " + "\n  ".join(bad)

    def test_quarantine_metadata_matches_the_rows(self, seed):
        """metadata must not claim a station is correct that the rows quarantine.

        d4f0c49 listed "Croiisement Ghorfa" under water_quarantine.verified_correct
        while a user reported it as a wrong point. The file then asserted the
        opposite of the data; this pins that the two cannot drift apart again.
        """
        meta = seed.get("metadata", {})
        quarantined = {s["name"].strip().lower() for s in seed.get("stations", []) if s.get("quarantined")}

        assert "verified_correct" not in meta.get("water_quarantine", {}), (
            "water_quarantine.verified_correct is back; if a station has been "
            "re-verified, remove its quarantine in the same commit"
        )
        verified = meta.get("water_quarantine", {}).get("verified_correct", [])
        overlap = quarantined & {n.strip().lower() for n in verified}
        assert not overlap, f"Metadata claims verified but rows quarantine: {overlap}"

        reported = meta.get("user_reported_faulty", {})
        assert set(n.strip().lower() for n in reported.get("names", [])) <= quarantined, (
            f"user_reported_faulty names are not all quarantined in the rows: {reported.get('names')}"
        )
