# Roadmap

## Current state

The repository currently contains a working backend (`src/backend/app/main.py`),
a physical-cost local router (`src/backend/app/routing.py`), a canonical
Leaflet frontend (`frontend/index.html`), and a self-contained offline variant
(`frontend/bledi-map.html`). Seed data covers 232 lines and 1,711 stations
countrywide. See `README.md` for what exists today and `docs/provenance.md` for
the data-source audit.

## Previously planned phases (kept for context, not commitments)

The files below were the original planning documents and are now superseded by
this roadmap and the README. They are retained only as historical reference.

### Data sources considered

- **SNTRI** — intercity buses; official schedules may exist as PDFs, no known API.
- **SNCFT / ONCF** — trains and TGM; timetables published on the official site.
- **Transtu** — Tunis metro léger + buses; the official site is offline, Wayback
  Machine only; manual entry would be needed.
- **SRTG** — regional transport; possibly PDF schedules.
- **Louages** — shared intercity vans; no official data; would need
  crowdsourcing and field research.
- **OpenStreetMap** — partial Tunisia coverage; ODbL-licensed; useful for
  geometries and some stop locations.

### Places data

Options that have been considered: OSM (free, partial), Google Places (paid),
Foursquare (freemium), Facebook Places (limited API), and manual
crowdsourcing. None of the places/ratings features are implemented in the
current codebase.

### Louage research strategy that was discussed

Field visits to louage stations, community crowdsourcing (forms, social groups),
interviewing station chiefs, and scraping existing informal data. This remains
unstarted.

## Items flagged as future / aspirational

The following are not implemented and are not on the critical path for the
current pilot:

- Flutter mobile app (`src/mobile/` is a stub).
- PostGIS / PostgreSQL backend replacing the in-memory seed.
- Places database with ratings and photos.
- Live location sharing.
- Full nationwide coverage with licensable data sources replacing Tunismapper.

## Pilot scope

The seed data is countrywide, but the pilot region the routing engine and
tuning are optimized for is not stated in the repo. If you are piloting a
specific region (for example Greater Tunis or Bizerte), say so and I will
record it here and tune constants accordingly. Do not assume a region until you
confirm it.

## Data-source replacement

See `docs/provenance.md` for the current provenance audit. The main unresolved
question is the Tunismapper-derived data: either confirm its terms are acceptable
or replace it with licensable sources (Transtu PDFs, SNCFT, OSM, or own field
data) before claiming a license for the repository.
