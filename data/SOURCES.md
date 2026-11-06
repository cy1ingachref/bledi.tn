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
| `seed_all_tunisia_routes.tagged.json` | `scripts/import_downloads_transport.py`, `scripts/import_louage_network.py`, `scripts/scrape_bizerteconnect.py`, `scripts/tag_provenance.py` | 7,452 stations, 379 lines |
| `bizerteconnect_network.json` | `scripts/scrape_bizerteconnect.py` | Raw BizerteConnect API scrape |
| `route_geometry.json`, `taxi_geometry.json` | `services/transit/tools/build_*_geometry.py` | Per-line geometry caches |
| `rail_graph.npz` (641 KB) | `services/transit/tools/build_rail_graph.py` | Rail graph; **committed** because the test suite asserts long rail legs carry real geometry |
| `transport_map_corrected.json` | `scripts/build_transport_catalog.py` | Mode-banded network + station mapping consumed by the frontend `transport_catalog.json` |
| `transport_encyclopedia.json` | `scripts/build_encyclopedia.py` | Driver-facing guide + other-modes encyclopedia (louage, taxi, tram/metro, TGM, rail, ferry, airport) from the downloaded source guides |
| `louage_corridors.example.json` | `scripts/import_louage_network.py` (ref) | Louage corridor definitions, not a seed file |

**Not committed** (regenerable, large, or upstream third-party content):

| File | Why not committed | Rebuilt by |
|---|---|---|
| `road_graph.npz` (153 MB) | Size; derived from the OSM extract | `services/transit/tools/build_road_graph.py` |
| `scripts/tunismapper_all_routes_stops.json` (21 MB) | Upstream third-party scrape, size | `scripts/scrape_all_routes.py` |
| `scripts/tunismapper_station_details.json` (1.7 MB) | Upstream third-party scrape | `scripts/scrape_station_details.py` |
| `apps/mobile/tool/osm_nodes_cache.json` (1.2 MB) | Derived cache | re-run the tool that wrote it |

`road_graph.npz` is ignored via `.gitignore`; `rail_graph.npz` is committed.
Build the road graph before running the backend:

```bash
# Needs a local OSM extract (default: ~/Downloads/roads/roads.gpkg,
# override with BLEDI_ROADS_GPKG)
python services/transit/tools/build_road_graph.py
```

Without the road graph the backend still starts, but road legs are drawn as
straight lines between two stops instead of following the real road. Rail legs
are unaffected, because `rail_graph.npz` ships with the repo — the test suite
asserts that a long rail leg is never a bare straight line, and that assertion
cannot hold if the graph is missing.

## Regenerating

All paths below default to `~/Downloads/...` and can be overridden with the
environment variable named in parentheses.

```bash
# Stations + lines from the operator exports and the louage CSV
# (BLEDI_OPERATOR_EXPORTS, BLEDI_LOUAGE_CSV)
python scripts/import_downloads_transport.py --write
python scripts/import_louage_network.py --write

# BizerteConnect bus network (live scrape, ~2 min)
python scripts/scrape_bizerteconnect.py --write

# Provenance tags on every record
python scripts/tag_provenance.py

# Routing graphs from the OSM extract (BLEDI_ROADS_GPKG, BLEDI_RAILS_GEOJSON)
python services/transit/tools/build_road_graph.py
python services/transit/tools/build_rail_graph.py
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
