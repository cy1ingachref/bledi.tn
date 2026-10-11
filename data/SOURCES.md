# Data sources

The raw Tunisia transport resources are **not** stored in this repo — they are
large (3.2 GB) and mostly upstream copies. They live in one consolidated folder:

    C:\Users\cy1in\Downloads\tunisia-transport-data\

with a README explaining every subfolder. Layout:

| Folder | Contents |
|---|---|
| `01-bus-network/` | Operator exports (156 files: TRANSTU, SNTRI, SORETRAS, SRTGN, SRTM, SRT Bizerte, SRTJ, SNCFT), GTFS feeds, TNRP national stop registry, `tunisia_louage_network.csv` |
| `02-rail-metro-tgm/` | OSM rail network + metro/train map exports |
| `03-roads/` | HOT OSM roads GeoPackage/Shapefile, road segments N1–N7, highway exports |
| `04-osm-source/` | `tunisia-latest.osm.pbf` — the source for the road and rail graphs |
| `05-raw-exports/` | Reserved (currently empty) |
| `06-docs-tools/` | Earlier project snapshots, `Project Tmap.txt`, web-app requirements, OSRM build artifacts |

## What this repo keeps

`data/` holds only the **derived, committed** datasets the app loads at runtime:

| File | Built by | Contents |
|---|---|---|
| `seed_all_tunisia_routes.tagged.json` | `scripts/import_downloads_transport.py`, `scripts/import_louage_network.py`, `scripts/scrape_bizerteconnect.py` | 7,452 stations, 379 lines |
| `bizerteconnect_network.json` | `scripts/scrape_bizerteconnect.py` | Raw BizerteConnect API scrape |
| `road_graph.npz` (153 MB) | `src/backend/tool/build_road_graph.py` | From the `.osm.pbf` |
| `rail_graph.npz` | `src/backend/tool/build_rail_graph.py` | From the `.osm.pbf` |
| `route_geometry.json`, `taxi_geometry.json` | `src/backend/tool/build_*_geometry.py` | Per-line geometry caches |

## Regenerating

```bash
# Stations + lines from the operator exports and the louage CSV
python scripts/import_downloads_transport.py --write
python scripts/import_louage_network.py --write

# BizerteConnect bus network (live scrape, ~2 min)
python scripts/scrape_bizerteconnect.py --write

# Routing graphs from the OSM extract
python src/backend/tool/build_road_graph.py
python src/backend/tool/build_rail_graph.py
```

Both importers are idempotent — re-running them reports
`TOTAL new stations: 0` rather than duplicating rows.

## Known data gaps

- **BizerteConnect has no public stops endpoint.** 404 on `bus-stops/`,
  `bus-stations/`, `stops/`, `stations/`, `bus-trips/`; `/trips/` and
  `/season-schedules/` return 401 (admin auth). Its 117 imported lines
  therefore carry named endpoints and outbound/return schedules, but no
  intermediate stops and no coordinates.
- **1,082 SNCFT level crossings** (`resau ferre/**/SNCFT-PN-*`) look like
  stations but are not, and are excluded on purpose.
- **3 of 8 GTFS zips are corrupt** (`BadZipFile`) — the SNTRI, SORETRAK,
  TRANSTU and SRTJ feeds are the usable ones.
