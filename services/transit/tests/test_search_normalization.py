"""Search must tolerate accents, articles, spacing and ALL-CAPS names. No seed needed."""
from __future__ import annotations

from bledi_transit.application.catalog import Catalog
from bledi_transit.application.network import Network
from bledi_transit.domain.textnorm import fold, pretty


def _stop(sid, name, lat, lon, mode):
    return {"id": sid, "name": name, "lat": lat, "lon": lon, "mode": mode}


def make_catalog() -> Catalog:
    stations = [
        _stop("marsa", "Marsa", 36.8758, 10.3249, "bus"),
        _stop("marsa_plage", "MARSA PLAGE", 36.8830, 10.3335, "metro"),
        _stop("a_roport", "AÉROPORT", 36.8319, 10.3139, "metro"),
        _stop("sidi_bousaid", "SIDI BOUSAID", 36.8705, 10.3421, "metro"),
        _stop("sfax", "Sfax", 34.7352, 10.7671, "train"),
        _stop("bizerte_bus", "BIZERTE", 37.2748, 9.8456, "bus"),
        _stop("bizerte", "Bizerte", 37.2664, 9.8639, "train"),
        _stop("tunis_marine", "TUNIS MARINE", 36.8002, 10.1928, "metro"),
        _stop("el_mourouj_1", "EL MOUROUJ 1", 36.7385, 10.2066, "metro"),
        _stop("mourouj_bus", "Mourouj 1", 36.7380, 10.2070, "bus"),
        _stop("far_airport", "Aeroport Skanes Monastir", 35.7625, 10.7541, "train"),
    ]
    louage = [{"id": "tunis_marine", "name_fr": "Tunis Marine", "location": {"lat": 36.8003, "lon": 10.1904}}]
    return Catalog(Network(stations=stations, lines=[], louage_stations=louage), None)


def top(q, n=1):
    return [r["display_name"] for r in make_catalog().search(q, n, None, None)["results"]]


def test_leading_article_is_optional():
    r = make_catalog().search("la marsa", 5, None, None)["results"]
    assert r and r[0]["kind"] == "place" and r[0]["name"] == "La Marsa"
    assert {"marsa", "marsa_plage"} <= {x["id"] for x in r}


def test_accents_are_ignored():
    assert top("aeroport")[0].startswith("Aéroport Tunis-Carthage")
    ids = [r["id"] for r in make_catalog().search("aeroport", 10, None, None)["results"]]
    assert "a_roport" in ids and ids.index("a_roport") < ids.index("far_airport")


def test_spacing_variants_match():
    ids = [r["id"] for r in make_catalog().search("sidi bou said", 5, None, None)["results"]]
    assert "sidi_bousaid" in ids


def test_arabic_query_finds_the_place():
    assert top("المرسى")[0] == "La Marsa"


def test_city_labels_use_the_governorate_not_the_nearest_seat():
    r = {x["id"]: x for x in make_catalog().search("marsa", 10, None, None)["results"]}
    assert r["marsa"]["city"] == "Tunis" and r["marsa_plage"]["city"] == "Tunis"


def test_display_name_has_no_duplicate_city_and_no_shouting():
    names = top("sfax", 5) + top("bizerte", 5)
    assert "Sfax · Sfax" not in names and "Bizerte · Bizerte" not in names
    assert "BIZERTE" not in names
    assert pretty("TUNIS MARINE NORD") == "Tunis Marine Nord"
    assert pretty("Carthage Byrsa") == "Carthage Byrsa"
    assert pretty("RR23") == "RR23"


def test_stops_of_one_interchange_are_merged():
    rs = make_catalog().search("tunis marine", 5, None, None)["results"]
    assert len(rs) == 1 and set(rs[0]["modes"]) == {"metro", "louaj"}


def test_exact_city_ranks_first():
    assert make_catalog().search("sfax", 3, None, None)["results"][0]["kind"] == "city"


def test_fold():
    assert fold("  Sidi Bou-Saïd ") == "sidi bou said"
    assert fold("AÉROPORT") == "aeroport"
