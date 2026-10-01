#!/usr/bin/env python3
"""Generate the localization files that easy_localization loads at runtime.

easy_localization reads `<locale>.json` from the asset directory, so those are
what actually ship. The `.arb` files are kept alongside as the source-friendly
copy for translators.

Keeping one dict here (instead of hand-synced copies) means a new string cannot
drift between ar/fr/en. Run after editing TRANSLATIONS:

    python tool/gen_arb.py
"""

import json
from pathlib import Path

KEYS = [
    "app_name", "tagline", "search_hint", "origin", "destination",
    "choose_origin", "choose_destination", "swap", "clear", "search_route",
    "routing", "no_route", "retry", "close", "cancel", "save", "settings",
    "stations", "lines", "total_duration", "transfers", "fare", "steps",
    "walk", "ride", "transfer", "taxi", "bus", "metro", "train", "rfr",
    "no_stations", "my_location", "location_permission_denied",
    "location_unavailable", "backend_url", "backend_healthy",
    "backend_unreachable", "check_connection", "stations_loaded",
    "lines_loaded", "distance", "origin_destination_required",
    "instructions", "loading",
    "rail", "bus", "louage", "unknown",
    "cities", "all_cities", "filter", "show_all", "lines_here", "no_lines",
]

TRANSLATIONS = {
    "en": {
        "app_name": "BLEDI.TN",
        "tagline": "Public transport in Tunisia",
        "search_hint": "Search a station or line",
        "origin": "Origin",
        "destination": "Destination",
        "choose_origin": "Choose origin",
        "choose_destination": "Choose destination",
        "swap": "Swap",
        "clear": "Clear",
        "search_route": "Search route",
        "routing": "Finding a route…",
        "no_route": "No route found",
        "retry": "Retry",
        "close": "Close",
        "cancel": "Cancel",
        "save": "Save",
        "settings": "Settings",
        "stations": "Stations",
        "lines": "Lines",
        "total_duration": "Total duration",
        "transfers": "Transfers",
        "fare": "Fare",
        "steps": "Steps",
        "walk": "Walk",
        "ride": "Ride",
        "transfer": "Transfer",
        "taxi": "Taxi",
        "bus": "Bus",
        "metro": "Metro",
        "train": "Train",
        "rfr": "Express train",
        "no_stations": "No stations",
        "my_location": "My position",
        "location_permission_denied": "Location permission denied",
        "location_unavailable": "Location unavailable",
        "backend_url": "Backend URL",
        "backend_healthy": "Backend connected",
        "backend_unreachable": "Backend unreachable",
        "check_connection": "Check connection",
        "stations_loaded": "stations loaded",
        "lines_loaded": "lines loaded",
        "distance": "Distance",
        "origin_destination_required": "Choose an origin and a destination",
        "instructions": "Instructions",
        "loading": "Loading…",
        "rail": "Train / Metro",
        "bus": "Bus",
        "louage": "Taxi / Louage",
        "unknown": "Other",
        "cities": "Cities",
        "all_cities": "All cities",
        "filter": "Filter",
        "show_all": "Show all",
        "lines_here": "Lines from this stop",
        "no_lines": "No lines listed for this stop",
    },
    "fr": {
        "app_name": "BLEDI.TN",
        "tagline": "Transport public en Tunisie",
        "search_hint": "Rechercher une station ou une ligne",
        "origin": "Départ",
        "destination": "Destination",
        "choose_origin": "Choisissez le point de départ",
        "choose_destination": "Choisissez la destination",
        "swap": "Inverser",
        "clear": "Effacer",
        "search_route": "Rechercher un itinéraire",
        "routing": "Recherche d'itinéraire…",
        "no_route": "Aucun itinéraire trouvé",
        "retry": "Réessayer",
        "close": "Fermer",
        "cancel": "Annuler",
        "save": "Enregistrer",
        "settings": "Paramètres",
        "stations": "Stations",
        "lines": "Lignes",
        "total_duration": "Durée totale",
        "transfers": "Correspondances",
        "fare": "Tarif",
        "steps": "Étapes",
        "walk": "Marche",
        "ride": "Trajet",
        "transfer": "Correspondance",
        "taxi": "Taxi",
        "bus": "Bus",
        "metro": "Métro",
        "train": "Train",
        "rfr": "Train express",
        "no_stations": "Aucune station",
        "my_location": "Ma position",
        "location_permission_denied": "Autorisation de localisation refusée",
        "location_unavailable": "Position indisponible",
        "backend_url": "Adresse du serveur",
        "backend_healthy": "Serveur connecté",
        "backend_unreachable": "Serveur injoignable",
        "check_connection": "Vérifier la connexion",
        "stations_loaded": "stations chargées",
        "lines_loaded": "lignes chargées",
        "distance": "Distance",
        "origin_destination_required": "Choisissez un départ et une destination",
        "instructions": "Instructions",
        "loading": "Chargement…",
        "rail": "Train / Métro",
        "bus": "Bus",
        "louage": "Taxi / Louage",
        "unknown": "Autre",
        "cities": "Villes",
        "all_cities": "Toutes les villes",
        "filter": "Filtrer",
        "show_all": "Tout afficher",
        "lines_here": "Lignes depuis cet arrêt",
        "no_lines": "Aucune ligne pour cet arrêt",
    },
    "ar": {
        "app_name": "BLEDI.TN",
        "tagline": "نقل عمومي في تونس",
        "search_hint": "ابحث عن محطة أو خط",
        "origin": "نقطة الانطلاق",
        "destination": "الوجهة",
        "choose_origin": "اختر نقطة الانطلاق",
        "choose_destination": "اختر الوجهة",
        "swap": "تبديل",
        "clear": "مسح",
        "search_route": "ابحث عن الطريق",
        "routing": "جارٍ البحث عن طريق…",
        "no_route": "لم يتم العثور على طريق",
        "retry": "إعادة المحاولة",
        "close": "إغلاق",
        "cancel": "إلغاء",
        "save": "حفظ",
        "settings": "الإعدادات",
        "stations": "المحطات",
        "lines": "الخطوط",
        "total_duration": "المدة الإجمالية",
        "transfers": "التنقلات",
        "fare": "التعرفة",
        "steps": "الخطوات",
        "walk": "مشي",
        "ride": "ركوب",
        "transfer": "تغيير",
        "taxi": "تاكسي",
        "bus": "حافلة",
        "metro": "مترو",
        "train": "قطار",
        "rfr": "قطار سريع",
        "no_stations": "لا توجد محطات",
        "my_location": "موقعي الحالي",
        "location_permission_denied": "تم رفض إذن الموقع",
        "location_unavailable": "تعذر تحديد الموقع",
        "backend_url": "عنوان الخادم",
        "backend_healthy": "الخادم متصل",
        "backend_unreachable": "تعذر الاتصال بالخادم",
        "check_connection": "فحص الاتصال",
        "stations_loaded": "محطة محملة",
        "lines_loaded": "خط محمل",
        "distance": "المسافة",
        "origin_destination_required": "اختر نقطة الانطلاق والوجهة",
        "instructions": "التعليمات",
        "loading": "جارٍ التحميل…",
        "rail": "قطار / مترو",
        "bus": "حافلة",
        "louage": "تاكسي / لاج",
        "unknown": "أخرى",
        "cities": "المدن",
        "all_cities": "كل المدن",
        "filter": "تصفية",
        "show_all": "عرض الكل",
        "lines_here": "الخطوط من هذه المحطة",
        "no_lines": "لا توجد خطوط لهذه المحطة",
    },
}

OUT = Path(__file__).resolve().parent.parent / "assets" / "l10n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for locale, table in TRANSLATIONS.items():
        missing = [k for k in KEYS if k not in table]
        extra = [k for k in table if k not in KEYS]
        if missing or extra:
            raise SystemExit(
                f"{locale}: missing={missing} extra={extra}"
            )

        # Runtime format: plain <locale>.json, what easy_localization loads.
        payload = {k: table[k] for k in KEYS}
        json_path = OUT / f"{locale}.json"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        # Translator-facing copy, with the ARB locale marker.
        arb_path = OUT / f"app_{locale}.arb"
        arb_path.write_text(
            json.dumps({"@@locale": locale, **payload}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

        print(f"wrote {json_path.name} + {arb_path.name} ({len(KEYS)} keys)")


if __name__ == "__main__":
    main()