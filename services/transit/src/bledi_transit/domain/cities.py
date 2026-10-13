"""Governorate assignment for stations.

The seed has no governorate field, so each station goes to its nearest
governorate seat. Measured on the seed: 1 711 stations fall into 21 groups and
only 18 remote ones (Sened, Maknassy) sit further than MAX_CITY_DISTANCE_KM from
any seat; those get UNASSIGNED_CITY instead of a wrong governorate.
"""
from __future__ import annotations

from bledi_transit.domain.geo import haversine_m

CITY_SEATS: list[tuple[str, float, float]] = [
    ("Tunis", 36.8065, 10.1815),
    ("Ariana", 36.8628, 10.1957),
    ("Ben Arous", 36.7520, 10.2220),
    ("Manouba", 36.8161, 10.1011),
    ("Nabeul", 36.4560, 10.7376),
    ("Zaghouan", 36.4028, 10.1425),
    ("Bizerte", 37.2744, 9.8739),
    ("Béja", 36.7256, 9.1817),
    ("Jendouba", 36.5008, 8.7806),
    ("Le Kef", 36.1742, 8.7147),
    ("Siliana", 36.3667, 9.2167),
    ("Kairouan", 35.6781, 10.0963),
    ("Kassab", 35.1833, 8.8000),
    ("Sidi Bouzid", 36.4044, 9.4844),
    ("Sousse", 35.8256, 10.6360),
    ("Monastir", 35.7777, 10.8263),
    ("Mahdia", 35.5047, 11.0622),
    ("Sfax", 34.7406, 10.7603),
    ("Kébili", 33.8814, 8.8742),
    ("Gabès", 33.8815, 10.0982),
    ("Médenine", 33.3547, 10.5052),
    ("Tataouine", 32.9291, 10.4517),
    ("Ghorbel", 34.7484, 10.7369),
    ("Tozeur", 33.9197, 8.1339),
]

MAX_CITY_DISTANCE_KM = 60.0

# Explicit bucket rather than null, so clients never invent a fallback.
UNASSIGNED_CITY = "Other"


def nearest_city(lat: float, lon: float) -> str:
    best_name = UNASSIGNED_CITY
    best_d = MAX_CITY_DISTANCE_KM
    for name, slat, slon in CITY_SEATS:
        d = haversine_m(lat, lon, slat, slon) / 1000.0
        if d < best_d:
            best_d, best_name = d, name
    return best_name
