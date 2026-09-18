# Tunisia Transport & Places App — Master Plan

## Project Overview
A mobile app helping Tunisians find transport (louages, buses, taxis, trains), discover and rate places with photos, and share live location with smart multi-modal routing.

---

## Phase 0: Research & Validation (Weeks 1-4)

### 0.1 Data Source Discovery

#### Transport Data Sources
| Source | Type | Availability | Notes |
|--------|------|--------------|-------|
| SNTRI (Société Nationale de Transport Interurbain) | Intercity buses | Official schedules exist | May have PDF timetables, no known API |
| SNCFT (Société Nationale des Chemins de Fer Tunisiens) | Trains + TGM | Official website | Timetables published, potential for scraping |
| Transtu | Tunis metro léger + buses | Official (transtu.com.tn) | Route maps, schedules available |
| SRTG | Regional transport | Semi-official | May have PDF schedules |
| Louages | Shared intercity vans | NO official data | Will need crowdsourcing + field research |

#### Louage Research Strategy
1. **Field visits**: Visit 2-3 louage stations (e.g., Bab Saadoun, Bab Alioua, Sousse, Sfax) — document routes, fares, departure patterns
2. **Community mapping**: Create Google Form/MapMyIndia to crowdsource from Tunisians on Reddit (r/Tunisia), Facebook groups
3. **Station "chefs de gare"**: Interview station chiefs — they know all routes and prices
4. **Existing informal data**: Facebook groups like "Les louages en Tunisia", WhatsApp groups

#### Places Data Sources
| Source | Coverage | Legality | Cost |
|--------|----------|----------|------|
| OpenStreetMap (OSM) Tunisia | Partial | Open data (ODbL) | Free |
| Google Places API | Good | Paid, strict usage limits | $$$ |
| Facebook Places | Good | API access limited | Free-ish |
| Foursquare/Places API | Decent | Freemium | Free tier limited |
| Manual crowdsourcing | Build slowly | Clean | Free |

#### OpenStreetMap Tunisia Status
- Tunisia OSM coverage: Moderate (urban areas better, rural sparse)
- Key tags: `amenity=bus_station`, `amenity=ferry_terminal`, `public_transport=station`, `highway=bus_stop`
- Tools: Overpass API, osmium, JOSM editor

### 0.2 Competitor Analysis

| App | Tunisia Coverage | Transport Modes | Places | Weakness |
|-----|------------------|-----------------|--------|----------|
| Bolt | Urban (Tunis, Sousse) | Ride-hailing only | None | No intercity, no louages |
| Yassir | Urban | Ride-hailing only | None | Same as Bolt |
| Google Maps | Good roads, poor public transit | Car, walk, limited transit | Excellent | No louage/bus schedules, no Tunisian French/Arabic UI |
| Moovit | Urban only | Bus, metro, train | Limited | No louages, limited intercity |
| Rome2rio | Global | Multi-modal | None | No louage data, inaccurate for Tunisia |

**Gap**: No single app covers louages + buses + trains + taxis in Tunisia with local language support.

### 0.3 Legal & Regulatory Check
- **Scraping SNCFT/SNTRI**: Likely fine for personal/non-commercial use, but commercial use may need permission
- **OSM data**: Open data (ODbL), can use commercially with attribution
- **User-generated data**: Clean, no legal issues
- **Recommendation**: Start with OSM + user-generated + manually entered public data; seek partnerships later

### 0.4 Pilot City Selection

**Criteria**:
1. Population density + transport diversity
2. Personal access for ground-truthing
3. Transport mode variety
4. Tourism/review potential

**Candidates**:
- **Greater Tunis** (Tunis, La Marsa, Le Bardo, etc.) — Best for pilot: largest metro, all transport modes, TGM, metro léger, louages to everywhere, high smartphone penetration
- **Sousse** — Second largest, good louage hub, beaches for places
- **Sfax** — Industrial hub, different transport patterns

**Recommendation**: Start with Greater Tunis (Tunis + suburbs), expand to Sousse/Sfax in Phase 4.

---

## Phase 1: MVP — Transport Directory (Weeks 5-16)

### 1.1 Database Schema (PostgreSQL + PostGIS)

```sql
-- Core tables
CREATE TABLE governorates (
    id SERIAL PRIMARY KEY,
    name_ar VARCHAR(100),
    name_fr VARCHAR(100),
    name_en VARCHAR(100),
    boundary GEOMETRY(MultiPolygon, 4326)
);

CREATE TABLE stations (
    id SERIAL PRIMARY KEY,
    name_ar VARCHAR(200),
    name_fr VARCHAR(200),
    name_en VARCHAR(200),
    location GEOMETRY(Point, 4326),
    governorate_id INT REFERENCES governorates(id),
    station_type ENUM('louage', 'bus', 'train', 'metro', 'taxi_stand'),
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE routes (
    id SERIAL PRIMARY KEY,
    origin_station_id INT REFERENCES stations(id),
    destination_station_id INT REFERENCES stations(id),
    mode ENUM('louage', 'bus', 'train', 'metro', 'taxi'),
    approximate_duration_minutes INT,
    approximate_price_tnd DECIMAL(5,2),
    frequency_type ENUM('fixed_schedule', 'when_fill', 'on_demand'),
    schedule JSONB, -- flexible: {"weekday": ["06:00", "07:30"], "weekend": [...]}
    notes TEXT,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE user_contributions (
    id SERIAL PRIMARY KEY,
    user_id INT,
    contribution_type ENUM('new_route', 'correction', 'new_station'),
    data JSONB,
    status ENUM('pending', 'approved', 'rejected'),
    reviewed_by INT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 1.2 MVP Feature Set
- **Map view**: Show transport stations near user (PostGIS `ST_DWithin`)
- **Search**: "How to get from A to B" — returns available routes with modes, prices, durations
- **Filter**: By mode (louage, bus, train, metro, taxi), price range, duration
- **Offline cache**: Download transport data for home region
- **Language**: Arabic (Tunisian), French, English
- **Contribute**: Submit new route or correction (moderated)

### 1.3 Tech Stack Final Decision

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Mobile app | **Flutter** | Better performance, offline support, single codebase, good map libraries |
| Backend | **Node.js + Express** or **FastAPI** | FastAPI for quick API dev, Node.js if team knows JS better |
| Database | **PostgreSQL + PostGIS** | Geospatial queries essential |
| Maps | **Mapbox GL JS** or **Flutter Map** | Free tier generous, good OSM support |
| Routing engine | **OSRM** (self-hosted) or **GraphHopper** | Free, open-source, offline-capable |
| Image storage | **Cloudflare R2** | Free egress, S3-compatible |
| Auth | **Firebase Auth** | Phone auth built-in, easy |
| Realtime (Phase 3) | **Firebase Realtime DB** | Easy live location sharing |
| Hosting | **Railway**, **Render**, or **Vercel** | Free tiers for MVP |
| CI/CD | **GitHub Actions** | Free for public repos |

### 1.4 Data Seeding Strategy
1. **Manual entry**: 50-100 key louage/bus routes in pilot region (Greater Tunis)
2. **OSM import**: Import all bus stops, train stations from OSM Tunisia via Overpass API
3. **Community seeding**: Google Form shared on r/Tunisia, Facebook groups, campus boards
4. **Field research**: Weekend trips to document actual routes

---

## Phase 2: Places & Ratings (Weeks 17-28)

### 2.1 Places Schema
```sql
CREATE TABLE places (
    id SERIAL PRIMARY KEY,
    name_ar VARCHAR(200),
    name_fr VARCHAR(200),
    name_en VARCHAR(200),
    location GEOMETRY(Point, 4326),
    category_id INT REFERENCES categories(id),
    address TEXT,
    nearest_station_id INT REFERENCES stations(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name_ar VARCHAR(100),
    name_fr VARCHAR(100),
    name_en VARCHAR(100),
    icon VARCHAR(50) -- Material icon name
);

CREATE TABLE photos (
    id SERIAL PRIMARY KEY,
    place_id INT REFERENCES places(id),
    user_id INT,
    url VARCHAR(500),
    is_approved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE reviews (
    id SERIAL PRIMARY KEY,
    place_id INT REFERENCES places(id),
    user_id INT,
    rating INT CHECK (rating BETWEEN 1 AND 5),
    text TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 2.2 Features
- Browse places by category (restaurants, cafés, sights, services)
- Photo upload + compression
- Ratings + reviews (1-5 stars)
- "How to get here" — link to nearest transport from Phase 1
- Anti-fake review: require minimum app usage, rate limiting
- Favorites/saved places

---

## Phase 3: Social Location + Smart Routing (Weeks 29-44)

### 3.1 Social Features
- Friend system with privacy controls
- Opt-in live location sharing (1-hour default expiry)
- Real-time map with friend indicators
- Emergency contact / panic button

### 3.2 Multi-Modal Routing Engine
- Input: user location, friend location, preferred modes
- Output: step-by-step instructions ("Walk 3 min to Bab Saadoun → Louage to Bizerte (30 min, 5 TND) → Walk 5 min")
- ETA with uncertainty ranges for louages
- "Meet in the middle" feature

---

## Phase 4: Growth & Monetization (Weeks 45+)

### 4.1 Monetization
- Business listings (premium placement)
- Affiliate deals with Bolt/Yassir for taxi rides
- Community moderator roles
- Gamification (badges for contributors)

### 4.2 Expansion
- City-by-city based on demand data
- SNTRI/Transtu partnerships for verified schedules

---

## Resource Requirements

### Team
| Role | Count | Effort |
|------|-------|--------|
| Mobile developer (Flutter) | 1 | Full-time |
| Backend developer | 1 | Full-time |
| Data researcher/collector | 1 | Part-time (Phase 0-1) |
| UI/UX designer | 1 | Part-time |

### Budget (MVP)
| Item | Cost |
|------|------|
| Mapbox free tier | $0 |
| Firebase Spark plan | $0 |
| Railway/Render free tier | $0 |
| Domain (optional) | $10/year |
| Cloudflare R2 | $0 |
| **Total** | **$10-50/month** |

### Tools (All Free/Open Source)
- Flutter (free)
- PostgreSQL + PostGIS (free)
- OSRM/GraphHopper (free, self-hosted)
- OSM data (free)
- Firebase Spark (free tier)
- GitHub (free for public repos)
- Figma (free tier for design)
- VS Code (free)

---

## Immediate Next Actions (This Week)

1. **Create GitHub repo** for project
2. **Set up Overpass API queries** to extract Tunisia transport data from OSM
3. **Create Google Form** for crowdsourcing louage data
4. **Visit Bab Saadoun louage station** — document top 10 routes
5. **Design Figma wireframes** for MVP screens
6. **Set up Flutter project skeleton** with map view
7. **Set up PostgreSQL + PostGIS** locally or on Railway

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Louage data inaccurate | "Report incorrect info" button on every route; community verification |
| OSM Tunisia coverage poor | Manual entry + crowdsourcing fills gaps |
| No user adoption | Start with students/young professionals (Facebook campus groups) |
| Legal issues with scraping | Only use OSM + user-generated + publicly posted schedules |
| Connectivity issues | Offline-first design; download region data on Wi-Fi |
| Fake reviews | Rate limiting, require usage history, report button |

---

## Success Metrics (Phase 1 MVP)

- 100+ transport routes documented in pilot region
- 50+ stations geolocated
- 500+ app downloads in first month
- 100+ user contributions (corrections/additions)
- App store rating 4.0+

---

*Plan created: 2026-09-18*
*Status: Phase 0 ready to begin*
