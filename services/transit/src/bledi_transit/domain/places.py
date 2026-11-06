"""Well-known places riders search for that are not transit stops.

"La Marsa", "Aeroport Tunis-Carthage" or "Les Berges du Lac" match no stop name
(stops are called "Marsa", "AEROPORT", "Lac Palace"), so the stop-only search
returned nothing or the wrong airport. Coordinates are approximate centroids
(about 100 to 300 m); check them against your own data before relying on them.

(name_fr, name_ar, name_en, aliases, lat, lon, governorate)
"""
from __future__ import annotations

Place = tuple[str, str, str, tuple[str, ...], float, float, str]

PLACES: tuple[Place, ...] = (
    ("La Marsa", "المرسى", "La Marsa", ("marsa ville", "lamarsa"), 36.8782, 10.3247, "Tunis"),
    ("Aéroport Tunis-Carthage", "مطار تونس قرطاج", "Tunis-Carthage Airport",
     ("aeroport", "airport", "aeroport tunis", "tunis carthage", "مطار"), 36.8510, 10.2272, "Tunis"),
    ("Médina de Tunis", "مدينة تونس العتيقة", "Medina of Tunis", ("medina", "la medina", "المدينة العتيقة"), 36.7985, 10.1707, "Tunis"),
    ("Les Berges du Lac", "ضفاف البحيرة", "Berges du Lac", ("lac 1", "lac1", "berges du lac", "les berges"), 36.8333, 10.2333, "Tunis"),
    ("Les Berges du Lac 2", "ضفاف البحيرة 2", "Berges du Lac 2", ("lac 2", "lac2"), 36.8400, 10.2650, "Tunis"),
    ("Carthage", "قرطاج", "Carthage", ("carthage ville", "site de carthage"), 36.8528, 10.3233, "Tunis"),
    ("Sidi Bou Saïd", "سيدي بوسعيد", "Sidi Bou Said", ("sidi bousaid", "sidi bou said"), 36.8705, 10.3430, "Tunis"),
    ("Gammarth", "قمرت", "Gammarth", (), 36.9181, 10.2850, "Tunis"),
    ("La Goulette", "حلق الوادي", "La Goulette", ("goulette",), 36.8183, 10.3052, "Tunis"),
    ("Le Bardo", "باردو", "Bardo", ("bardo", "musee du bardo"), 36.8092, 10.1340, "Tunis"),
    ("Le Kram", "الكرم", "Le Kram", ("kram",), 36.8350, 10.3200, "Tunis"),
    ("Ennasr", "النصر", "Ennasr", ("cite ennasr", "nasr"), 36.8650, 10.1650, "Ariana"),
    ("La Soukra", "سكرة", "La Soukra", ("soukra",), 36.8830, 10.2500, "Ariana"),
    ("Radès", "رادس", "Rades", ("rades",), 36.7700, 10.2750, "Ben Arous"),
    ("Hammam Lif", "حمام الأنف", "Hammam Lif", (), 36.7300, 10.3340, "Ben Arous"),
    ("Ezzahra", "الزهراء", "Ezzahra", ("ez zahra",), 36.7430, 10.3040, "Ben Arous"),
    ("Borj Cédria", "برج السدرية", "Borj Cedria", ("borj cedria",), 36.6970, 10.4000, "Ben Arous"),
    ("Hammamet", "الحمامات", "Hammamet", (), 36.4000, 10.6167, "Nabeul"),
    ("Djerba - Houmt Souk", "جربة حومة السوق", "Djerba", ("djerba", "houmt souk", "jerba", "جربة"), 33.8750, 10.8570, "Médenine"),
)
