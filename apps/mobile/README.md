# BLEDI.TN — Flutter app

Flutter client for the [BLEDI.TN](https://github.com/cy1ingachref/bledi.tn) Tunisia
public-transport backend. Renders the network on an interactive map and asks the
backend's local multi-modal router for itineraries.

The routing algorithm lives in the transit service (`services/transit`); this
app only requests and renders it.

## Requirements

- Flutter 3.24+ / Dart 3
- A running BLEDI.TN backend (see below)

## Run it

Start the transit service from the repository root:

```bash
pip install -e services/transit
uvicorn --factory bledi_transit.main:create_app --port 8000
```

Then run the app:

```bash
cd apps/mobile
flutter pub get
flutter run --dart-define=BLED_API_BASE=http://localhost:8000
```

### Pointing at a different backend

`BLED_API_BASE` is compile-time configurable and defaults to
`http://localhost:8000`.

```bash
# A phone on the same Wi-Fi — use the host machine's LAN IP, not localhost.
flutter run --dart-define=BLED_API_BASE=http://192.168.1.20:8000

# Android emulator reaching the host loopback.
flutter run --dart-define=BLED_API_BASE=http://10.0.2.2:8000
```

It is also editable at runtime from the Settings screen, and persisted with
`shared_preferences`, so you can repoint a debug build without rebuilding.

## Features

- **Map** — OpenStreetMap tiles, centred on Tunis, constrained to Tunisia's
  bounds. Attribution is rendered as the tile policy requires.
- **Every station on the map** — 1 729 stops drawn individually, coloured by
  mode: green for train/metro/RFR, red for bus, yellow for taxi/louage, grey for
  unclassified.
- **Mode filter** — toggle each category to show or hide it.
- **City grouping** — 24 governorates, each a tappable label. Tapping filters the
  map to that city and zooms in; a chip clears the filter.
- **Station details** — tap a stop to see its modes, city and the lines serving
  it, each tinted by mode.
- **Routing** — set origin/destination by search or map long-press, then request
  an itinerary. The route is drawn with per-mode polylines and stop markers, and
  the panel shows total duration, transfers, fare and step-by-step
  instructions.
- **Localisation** — Arabic, French and English.

## Layout

```
lib/
  main.dart                     app entry, EasyLocalization + theme
  app.dart                      go_router routes
  core/
    constants.dart              API base URL, map defaults, bounds
    theme.dart                  Material 3 theme + the mode colour palette
    utils/
      state.dart                MapPoint
      transport_mode_l10n.dart  localised TransportMode labels
  data/
    models/                     freezed models: station, line, itinerary, city
    datasources/                ApiClient (dio), StationsDataSource
    repositories/               RoutingRepository
  features/
    home/                       map + endpoint selection + routing
    routing/                    itinerary panel and step list
    stations/                   map layer, city picker, station sheets
    settings/                   backend URL editor + health check
  providers/                    riverpod providers
assets/l10n/                    en / fr / ar (generated — see tool/gen_arb.py)
docs/
  osm-stop-audit.md     seed-vs-OpenStreetMap comparison and its findings
tool/
  gen_arb.py             regenerates assets/l10n from one table
  check_backend_city.py  asserts the backend's station→city assignment
```

## Auditing the seed against OSM

The seed was audited against live OpenStreetMap during construction. Findings
are in `docs/osm-stop-audit.md`. Key takeaways:

- Match on position within 250 m, not on name. Tunisian names vary between
  transliterations and our seed abbreviates (`Sousse Zi` for
  `Sousse Zone Industrielle`), so 544 of 1 666 confirmed pairs differ in label
  while being the same stop.
- `railway=stop` and `public_transport=stop_position` are **not** bus-only
  tags. SNCFT halts and TGM platforms carry them, so a naive comparison reports
  ~60 correctly-mapped rail stops as mode errors.

## Data layer notes

Two conventions in the backend payload are easy to get wrong, so both are
handled once and covered by tests:

- **Station coordinates are `[lon, lat]`** (GeoJSON, RFC 7946).
- **Transit step coordinates are `[lat, lon]`** — the opposite.

Mixing them up silently places stations in the Indian Ocean, so the conversions
live in `StationsDataSource` and `RouteStep`'s `@JsonKey` converter rather than
at call sites.

Backend fields are snake_case; every freezed field carries an explicit
`@JsonKey`.

`Station.transportMode` prefers the backend's `mode` field. When talking to an
older backend that sends only `{id, name, lines}`, it falls back to inferring the
mode from the line ids (`metro_56_tgm`, `bus_705_12`), so the colours degrade
rather than breaking.

## Tests

```bash
flutter test          # 44 tests
```

Covers model parsing against captured backend payloads, coordinate orientation,
per-step duration estimation, localisation assets, and the enum/colour mapping.

The integration tests hit a live backend and skip themselves when one is not
reachable:

```bash
# terminal 1, from the repository root
uvicorn --factory bledi_transit.main:create_app --port 8000
# terminal 2
flutter test
```

To assert nothing silently skipped:

```bash
flutter test 2>&1 | grep -E "\+[0-9]+ ~[0-9]+" && echo "SKIPS PRESENT"
```

## Regenerating translations

`assets/l10n/*.json` is what `easy_localization` loads at runtime and is
generated. Edit the tables in `tool/gen_arb.py`, then:

```bash
python tool/gen_arb.py
```

It writes the runtime `.json` files and fails if the three locales disagree on
their key set.

## Known limitations

- Per-step durations in the instruction list are **estimates** derived from
  straight-line distance (prefixed with `~`). The backend populates
  `duration_min` on the itinerary, not per step, and real road geometry lives on
  the backend.
- `Other` groups stations further than 60 km from any governorate seat. Border
  cases such as Maknassy and Sened are really Sfax-area; correcting that needs
  real boundary data the seed does not carry.
- Routing calls the local router only.
- Not yet verified on a real Android or iOS device; only web has been exercised
  against a live backend.