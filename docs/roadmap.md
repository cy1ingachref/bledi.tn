# Roadmap

## Current state

Two services (transit routing in Python, accounts in Rust), a React web app
that also serves as the gateway, and a Flutter client. Seed data covers 379
lines and 7,452 stations countrywide. See [architecture](architecture.md) for
how the parts fit and [provenance](provenance.md) for the data-source audit.

Historical phase reports (moved out of the repo root by the M5 cleanup) are in
[docs/reports/](reports/): `design-issues.md`, `fix_report.md`,
`phase1_report.md`, `phase2_report.md`, `phase3a_report.md`, `phase3c_report.md`,
and the raw route snapshots in `reports/data/`. They are reference material,
not current plans.

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
