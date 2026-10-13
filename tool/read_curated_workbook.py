#!/usr/bin/env python3
"""Read BLEDI_transport.xlsx (the curated workbook) and the louage CSV.

The wrong rows came from `dl_bledi_curated_workbook_*`, i.e. BLEDI_transport.xlsx.
Reading the source sheet tells us the INTENT: were Bir Mouzaina / Douane Bir
Mouzaina / Ajim meant to be Bizerte-region stops (near Lake Ichkeul, where the
bad coordinates sit) or Djerba ones? A column shift would show up as lat/lon
that do not match the named place.

    python tool/read_curated_workbook.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\cy1in\bledi.tn")
DUMP = Path(r"C:\Users\cy1in\Downloads\tunisia-transport-data")
WB = DUMP / "01-bus-network" / "operator-exports" / "BLEDI_transport.xlsx"
LOU = DUMP / "01-bus-network" / "tunisia_louage_network.csv"

try:
    import openpyxl
except ImportError:
    print("openpyxl missing")
    sys.exit(1)

wb = openpyxl.load_workbook(WB, data_only=True, read_only=True)
print(f"{WB.name}: sheets = {wb.sheetnames}\n")

KEYS = ("mouzaina", "ajim", "ghorfa", "ريفي", "مرزين", "اجيم")

for sheet in wb.sheetnames:
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        continue
    header = [str(c) if c is not None else "" for c in rows[0]]
    # Does this sheet mention any target?
    blob = " ".join(" ".join(str(c) for c in r if c is not None) for r in rows[:4000]).lower()
    if not any(k in blob for k in KEYS):
        print(f"--- {sheet}: {len(rows)} rows, no target match")
        continue
    print("=" * 92)
    print(f"### {sheet}  ({len(rows)} rows)")
    print(f"  columns: {header}")
    for i, r in enumerate(rows[1:], start=2):
        txt = " ".join(str(c) for c in r if c is not None).lower()
        if any(k in txt for k in KEYS):
            print(f"  row {i}: {r}")

print("\n" + "=" * 92)
print(f"### {LOU.name}")
text = LOU.read_text(encoding="utf-8-sig", errors="replace")
rows = list(csv.reader(text.splitlines()))
print(f"  rows: {len(rows)}")
if rows:
    print(f"  header: {rows[0]}")
for r in rows[1:]:
    txt = " ".join(r).lower()
    if any(k in txt for k in KEYS):
        print(f"  {r}")
print("\n  --- all louage stations (name + coord) ---")
for r in rows[1:]:
    print(f"  {r}")
