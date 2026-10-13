from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import Any

import pytest
from support import client

HIT = {"lat": "36.8", "lon": "10.18", "display_name": "Tunis", "type": "city"}


class FakeGeocoder:
    def __init__(self, answer: list[dict[str, Any]] | None) -> None:
        self.answer = answer

    def search(self, query: str) -> list[dict[str, Any]] | None:
        return self.answer


@pytest.fixture
def geocoder() -> Iterator[FakeGeocoder]:
    state = client().app.state
    real = state.services
    fake = FakeGeocoder([])
    state.services = dataclasses.replace(real, geocoder=fake)
    yield fake
    state.services = real


def test_no_match_is_an_empty_list(geocoder: FakeGeocoder) -> None:
    r = client().get("/api/v1/geocode?q=nowhere")
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_an_outage_is_a_503(geocoder: FakeGeocoder) -> None:
    geocoder.answer = None
    assert client().get("/api/v1/geocode?q=tunis").status_code == 503


def test_limit_is_bounded(geocoder: FakeGeocoder) -> None:
    geocoder.answer = [HIT, HIT]
    assert len(client().get("/api/v1/geocode?q=tunis&limit=1").json()["results"]) == 1
    assert client().get("/api/v1/geocode?q=tunis&limit=-1").status_code == 422
