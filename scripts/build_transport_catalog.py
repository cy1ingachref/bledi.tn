#!/usr/bin/env python3
"""Build apps/web/static/transport_catalog.json from the corrected
transport_map_corrected.json + the current UI language.

Resolves human-readable mode labels per-locale, so the catalog displays
names the user recognizes (e.g. "Buses", "Metro", "Buses") rather than
the raw mode keys.
"""
import json
from pathlib import Path

BASE = Path("C:/Users/cy1in/bledi.tn")
SRC = BASE / "data" / "transport_map_corrected.json"
OUT = BASE / "apps" / "web" / "static" / "transport_catalog.json"

MODE_LABELS = {
    "bus":    {"en": "Buses",    "fr": "Bus",    "ar": "باصات"},
    "louage": {"en": "Louage / Car Sharing", "fr": "Louage", "ar": "لواج"},
    "metro":  {"en": "Metro",    "fr": "Métro",  "ar": "مترو"},
    "rail":   {"en": "Rail / Trains", "fr": "Rail", "ar": "سكك حديد"},
    "taxi":   {"en": "Taxis",    "fr": "Taxis",  "ar": "تاكسي"},
    "train":  {"en": "Intercity / Freight Trains", "fr": "Train / Régional", "ar": "قطار"},
    "unknown":{"en": "Unclassified / Local", "fr": "Non classé", "ar": "غير مصنف"},
}


def main():
    m = json.loads(SRC.read_text(encoding="utf-8"))
    cart = {"modes": {}, "stations": {}}
    cart = {"modes": {}, "stations": {}}
    for mode, v in m["by_mode"].items():
        cart["modes"][mode] = {
            "mode": mode,
            "name": MODE_LABELS[mode]["en"],      # human-readable label (en)
            "name_en": MODE_LABELS[mode]["en"],
            "name_fr": MODE_LABELS[mode]["fr"],
            "name_ar": MODE_LABELS[mode]["ar"],
            "stations": v["stations"],
            "lines": v["lines"],
        }
        for s in v["stations"]:
            cart["stations"][s["id"]] = s

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cart, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", OUT)
    for mode, label in MODE_LABELS.items():
        print("  %-10s %-30s" % (mode, label["en"]))


if __name__ == "__main__":
    main()
