#!/usr/bin/env python3
"""Build a consolidated transport encyclopedia reference from the two
downloaded source files (louage_tunisia.json + tunisia_transport_other_modes.json)
and drop it into the bledi.tn project as data/transport_encyclopedia.json.

This file holds RIDER-FACING reference/guide content (what the modes are, how
they run, fares, operating times, tips, connections) -- distinct from the
routing network (seed_all_tunisia_routes.tagged.json) and the mode-banded
catalog (transport_map_corrected.json). It is consumed by the frontend
transport catalog and by the docs/guide pages.
"""

from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]

import json

DOWNLOADS = Path(
    str(Path.home() / "Downloads")
)  # files were attached here
OUT = REPO / "data" / "transport_encyclopedia.json"

# Human-readable labels for the encyclopedia sections, per locale.
ENCYC_LABELS = {
    "driver_facing": {
        "en": "Driver-facing guide",
        "fr": "Guide conducteur",
        "ar": "دليل السائق",
    },
    "other_modes": {
        "en": "Other transport modes",
        "fr": "Autres modes de transport",
        "ar": "وسائل النقل الأخرى",
    },
    "vehicle_types": {
        "en": "Vehicle types",
        "fr": "Types de véhicules",
        "ar": "أنواع المركبات",
    },
    "operating_hours": {
        "en": "Operating hours",
        "fr": "Horaires d'exploitation",
        "ar": "ساعات العمل",
    },
    "stations": {
        "en": "Key stations",
        "fr": "Gares principales",
        "ar": "محطات رئيسية",
    },
    "tickets": {
        "en": "Tickets & payment",
        "fr": "Billets et paiement",
        "ar": "التذاكر والدفع",
    },
    "pricing_rules": {
        "en": "Pricing rules",
        "fr": "Règles tarifaires",
        "ar": "قواعد التسعير",
    },
    "no_direct_connections": {
        "en": "No direct connections",
        "fr": "Aucune connexion directe",
        "ar": "لا توجد اتصالات مباشرة",
    },
    "multi_leg_routes": {
        "en": "Multi-leg routes",
        "fr": "Itinéraires en plusieurs étapes",
        "ar": "مسارات متعددة الأجزاء",
    },
    "fare_observations": {
        "en": "Observed fares",
        "fr": "Tarifs observés",
        "ar": "الأسعار المسجلة",
    },
    "tips_for_travelers": {
        "en": "Tips for travelers",
        "fr": "Conseils aux voyageurs",
        "ar": "نصائح للمسافرين",
    },
    "data_quality_notes": {
        "en": "Data quality notes",
        "fr": "Remarques sur la qualité des données",
        "ar": "ملاحظات جودة البيانات",
    },
    "modeling_notes_not_from_source": {
        "en": "Modeling notes (not from source)",
        "fr": "Notes de modélisation (non issues de la source)",
        "ar": "ملاحظات النمذجة (غير مشتقة من المصدر)",
    },
    "taxi": {
        "en": "Taxi",
        "fr": "Taxis",
        "ar": "تاكسي",
    },
    "tunis_tram_metro": {
        "en": "Tunis Metro & Tramway",
        "fr": "Métro et tramway de Tunis",
        "ar": "المترو والترام Tunis",
    },
    "tgm": {
        "en": "TGM (Tunis-La Goulette-La Marsa)",
        "fr": "TGM (Tunis-La Goulette-La Marsa)",
        "ar": "تGAM (تونس-الق Shrewsbury-المرسى)",
    },
    "national_rail": {
        "en": "National rail (SNCFT)",
        "fr": "Voie ferrée nationale (SNCFT)",
        "ar": "السكك الحديدية الوطنية (سنتIFT)",
    },
    "kerkennah_ferry": {
        "en": "Kerkennah ferry",
        "fr": "Ferries de Kerkennah",
        "ar": "المضيق الكيركينا",
    },
    "tunis_carthage_airport": {
        "en": "Tunis-Carthage airport",
        "fr": "Aéroport de Tunis-Carthage",
        "ar": "المطار تاونس-كارثة",
    },
    "other_modes_overview": {
        "en": "Other modes overview",
        "fr": "Aperçu des autres modes",
        "ar": "نظرة عامة على وسائل النقل الأخرى",
    },
    "interchange_notes": {
        "en": "Interchange notes",
        "fr": "Remarques sur les échanges",
        "ar": "ملاحظات التبادل",
    },
}


def extract_louage(d: dict) -> dict:
    """Extract the louage encyclopedia section from louage_tunisia.json."""
    out: dict[str, object] = {}
    meta = d.get("_meta")
    if meta:
        out["_meta"] = {
            "source_url": meta.get("source_url"),
            "publisher": meta.get("publisher"),
            "page_last_modified": meta.get("page_last_modified"),
            "retrieved": meta.get("retrieved"),
            "source_language": meta.get("source_language"),
            "currency": meta.get("currency"),
            "price_note": meta.get("price_note"),
            "official_tariff_page": meta.get("official_tariff_page"),
        }

    concept = d.get("concept") or {}
    if concept:
        out["concept"] = {
            "summary": concept.get("summary"),
            "vehicle": concept.get("vehicle"),
            "capacity": concept.get("capacity"),
            "departure_rule": concept.get("departure_rule"),
            "route_signage": concept.get("route_signage"),
            "tourist_pricing": concept.get("tourist_pricing"),
        }

    vehicle_types = d.get("vehicle_types")
    if isinstance(vehicle_types, list):
        out["vehicle_types"] = vehicle_types

    operating_hours = d.get("operating_hours")
    if isinstance(operating_hours, dict):
        out["operating_hours"] = operating_hours

    stations = d.get("stations")
    if isinstance(stations, dict):
        out["stations"] = {k: v for k, v in stations.items() if v}

    tickets = d.get("tickets")
    if isinstance(tickets, dict):
        out["tickets"] = tickets

    pricing_rules = d.get("pricing_rules")
    if isinstance(pricing_rules, dict):
        out["pricing_rules"] = pricing_rules

    no_direct_connections = d.get("no_direct_connections")
    if isinstance(no_direct_connections, list):
        out["no_direct_connections"] = no_direct_connections

    multi_leg_routes = d.get("multi_leg_routes")
    if isinstance(multi_leg_routes, list):
        out["multi_leg_routes"] = multi_leg_routes

    fare_observations = d.get("fare_observations")
    if isinstance(fare_observations, list):
        out["fare_observations"] = fare_observations

    tips_for_travelers = d.get("tips_for_travelers")
    if isinstance(tips_for_travelers, list):
        out["tips_for_travelers"] = tips_for_travelers

    data_quality_notes = d.get("data_quality_notes")
    if isinstance(data_quality_notes, list):
        out["data_quality_notes"] = data_quality_notes

    modeling_notes = d.get("modeling_notes_not_from_source")
    if isinstance(modeling_notes, list):
        out["modeling_notes_not_from_source"] = modeling_notes

    return out


def extract_other_modes(d: dict) -> dict:
    """Extract the other-modes encyclopedia section from
    tunisia_transport_other_modes.json."""
    out: dict[str, object] = {}
    meta = d.get("_meta")
    if meta:
        out["_meta"] = {
            "source_site": meta.get("source_site"),
            "pages_used": meta.get("pages_used"),
            "not_included": meta.get("not_included"),
            "retrieved": meta.get("retrieved"),
            "source_language": meta.get("source_language"),
            "currency": meta.get("currency"),
            "caveat": meta.get("caveat"),
        }

    # Pass each mode section through, keyed by section name.
    for key in (
        "taxi",
        "tunis_tram_metro",
        "tgm",
        "national_rail",
        "kerkennah_ferry",
        "tunis_carthage_airport",
        "other_modes_overview",
        "interchange_notes",
    ):
        val = d.get(key)
        if val is None:
            continue
        if isinstance(val, dict):
            out[key] = val
        elif isinstance(val, list):
            out[key] = val

    # modelling notes
    modeling_notes = d.get("modeling_notes_not_from_source")
    if isinstance(modeling_notes, list):
        out["modeling_notes_not_from_source"] = modeling_notes

    return out


def build_encyclopedia() -> dict:
    """Assemble the full encyclopedia."""
    louage_d = json.loads((DOWNLOADS / "louage_tunisia.json").read_text(encoding="utf-8"))
    other_d = json.loads((DOWNLOADS / "tunisia_transport_other_modes.json").read_text(encoding="utf-8"))

    louage_sec = extract_louage(louage_d)
    other_sec = extract_other_modes(other_d)

    # Merge the two, prefixing keys so there is no collision (louage has
    # "tickets", "stations", "multi_leg_routes"; other_modes has none of these
    # names, but the prefix keeps the two sources distinguishable).
    merged: dict[str, object] = {}
    for k, v in louage_sec.items():
        merged["louage_" + k] = v
    for k, v in other_sec.items():
        merged[k] = v

    return {
        "generated_by": "scripts/build_encyclopedia.py",
        "source_files": [
            "louage_tunisia.json",
            "tunisia_transport_other_modes.json",
        ],
        "sections": merged,
    }


def main() -> int:
    encyc = build_encyclopedia()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(encyc, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"wrote {OUT}")
    for k, v in encyc["sections"].items():
        print(f"  {k:45s} sections={len(v) if isinstance(v, dict) else 'list'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
