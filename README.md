# BLEDI.TN — Tunisia Transport & Places App

An app that helps Tunisians find transport (louages, buses, taxis, trains), discover and rate places with photos, and share live location with smart multi-modal routing.

## Project Structure

```
bledi.tn/
├── docs/                          # Planning & documentation
│   ├── master-plan.md             # 4-phase roadmap
│   ├── mvp-scope-and-pilot.md     # MVP definition
│   ├── data-model-v02-stops.md    # Schema with ordered stops
│   └── free-tools-and-apis.md     # All tools (all free)
│
├── research/                      # Data sources & analysis
│   ├── data_sources/
│   │   └── official-sources.md    # Verified live sources
│   ├── competitor-analysis.md     # Gap analysis
│   ├── field-research-toolkit.md  # Louage research kit
│   └── bizerteconnect-stations.md # 131 BizerteConnect lines
│
├── data/                          # Seed data (JSON)
│   ├── seed_routes_destination_tunis.json  # 40+ verified fares
│   └── seed_lines_bizerte.json            # 35 lines with stops
│
├── src/
│   ├── mobile/                    # Flutter app
│   │   ├── lib/
│   │   │   ├── main.dart          # App entry
│   │   │   ├── core/
│   │   │   │   ├── constants/
│   │   │   │   ├── models/        # Station, Line, Route, Fare
│   │   │   │   ├── providers/
│   │   │   │   ├── services/
│   │   │   │   └── theme/
│   │   │   ├── features/
│   │   │   │   ├── map/
│   │   │   │   ├── search/
│   │   │   │   ├── routes/
│   │   │   │   ├── stations/
│   │   │   │   └── profile/
│   │   │   └── l10n/              # AR, FR, EN localization
│   │   └── pubspec.yaml
│   │
│   ├── backend/                   # FastAPI + PostGIS
│   │   ├── app/
│   │   │   ├── main.py            # API entry with routes
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── models/            # SQLAlchemy models
│   │   │   ├── schemas/           # Pydantic schemas
│   │   │   ├── services/
│   │   │   └── routers/
│   │   └── scripts/
│   │       └── import_seed_data.py
│   │
│   └── shared/                    # Shared types (if any)
│
└── README.md
```

## Key Insights

1. **Louage data is the moat** — zero official digital data exists
2. **OSM coverage is sparse** — ~15 bus stations in all of Greater Tunis
3. **Real fares exist** — destination-tunis.fr reader-verified fares (2015-2026)
4. **BizerteConnect.com** — 131 bus lines with station dropdowns
5. **Stack**: Flutter + FastAPI + PostgreSQL/PostGIS + Supabase
6. **Budget**: $0-10/month for MVP

## Quick Start

### Mobile (Flutter)

```bash
cd src/mobile
flutter pub get
flutter run
```

### Backend (FastAPI)

```bash
cd src/backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Import Seed Data

```bash
python src/backend/scripts/import_seed_data.py \
  --data-dir ./data \
  --db-url postgresql://user:pass@host:5432/bledi_tn \
  --create-schema
```

## Data Model v02

The app uses a **line-based model** with ordered stops:

- `stations` — all transport stops with GPS
- `lines` — transport routes (bus, louage, train, metro, taxi)
- `line_stations` — ordered stops on each line
- `fares` — prices between stations on a line
- `departures` — schedule times per line per direction

Query flow: User location → nearest stations → lines connecting to destination → show all stops in between.

## License

MIT License — Open source for Tunisia.

---

*BLEDI.TN — بنزرت أسهل معانا 🇹🇳*
