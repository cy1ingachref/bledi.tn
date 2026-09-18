# MVP Scope & Pilot City Selection

---

## Pilot City: Greater Tunis

### Why Greater Tunis
| Criteria | Score |
|----------|-------|
| Population | ~2.5M metro (largest) |
| Transport diversity | Metro, bus, louage, train, taxi, TGM |
| Field research access | Best (can visit in person) |
| Smartphone penetration | Highest in Tunisia |
| Tourism activity | Many cafés/restaurants to review |
| Louage hub | Bab Saadoun — the MAIN louage station |

### Boundaries of Pilot Region
- **North**: La Marsa, Le Bardo, Manouba
- **South**: Mohamedia, Fouchana
- **East**: Tunis Marine, La Goulette
- **West**: Le Kram, Carthage

### Administrative Scope
- Governorates: Tunis, Ben Arous, Ariana, Manouba (part of Greater Tunis)
- Focus: 15 louage/bus/train stations in the core area

---

## MVP Feature Set (Phase 1)

### Must Have (Launch Blockers)
1. **Map View** — Show user's location + nearby transport stations on map
2. **Station Detail** — Tap station → see routes, fares, frequency
3. **Search** — "How do I get from A to B?" → list available routes
4. **Filter** — By transport mode (louage, bus, train, metro, taxi)
5. **Contribute** — User can submit a new route or correction

### Should Have (Strongly Recommended)
6. **Offline Cache** — Download transport data for home region
7. **Multi-language** — Arabic (Tunisian), French, English
8. **Report Error** — Flag incorrect fare, route, or station location

### Nice to Have (If Time)
9. **Estimated Fare Range** — Not exact, but "typically X-Y TND"
10. **Departure Window** — "Usually departs every X min" for louages
11. **Photo Upload** — Station photos from users

### Explicitly NOT in MVP
- Places & ratings (Phase 2)
- Live location sharing (Phase 3)
- Multi-modal routing engine (Phase 3)
- Gamification (Phase 4)
- Business listings/monetization (Phase 4)
- Social features (Phase 3)

---

## MVP Technical Scope

### Mobile App (Flutter)
| Screen | Description |
|--------|-------------|
| Splash | App logo + loading |
| Onboarding | Language selection, location permission |
| Map | Main screen: map + station markers |
| Station Detail | Station info + route list |
| Route Detail | Full route info + contribute button |
| Search | From A to B form + results |
| Filter | Toggle transport modes |
| Contribute | Submit new route form |
| Settings | Language, cache management |

### Backend API (FastAPI)
| Endpoint | Description |
|----------|-------------|
| GET /stations | List stations (with geo filter) |
| GET /stations/{id} | Station detail |
| GET /routes?from={id}&to={id} | Find routes between stations |
| POST /contributions | Submit new route/correction |
| GET /health | Health check |

### Database Schema (MVP)
```sql
-- Simplified MVP schema
CREATE TABLE stations (
    id SERIAL PRIMARY KEY,
    name_ar VARCHAR(200) NOT NULL,
    name_fr VARCHAR(200),
    name_en VARCHAR(200),
    location GEOGRAPHY(Point, 4326),
    governorate VARCHAR(100),
    station_type VARCHAR(20) CHECK (station_type IN ('louage','bus','train','metro','taxi')),
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE routes (
    id SERIAL PRIMARY KEY,
    origin_id INT REFERENCES stations(id),
    destination_id INT REFERENCES stations(id),
    mode VARCHAR(20) CHECK (mode IN ('louage','bus','train','metro','taxi')),
    fare_tnd DECIMAL(5,2),
    duration_minutes INT,
    frequency_description TEXT, -- "Every 30 min" or "When full"
    vehicle_type VARCHAR(50),
    is_verified BOOLEAN DEFAULT FALSE,
    source VARCHAR(50), -- "field_research", "user_submitted", "sncft"
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE contributions (
    id SERIAL PRIMARY KEY,
    contributor_id UUID, -- anonymous or authenticated
    contribution_type VARCHAR(20),
    data JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Data Seeding
- Manual entry from field research: 50-100 routes across 10-15 stations
- Source: Bab Saadoun + 4 other stations in Greater Tunis
- Duration: 2 weekends of field research
- Backup: If field research is delayed, seed with common-knowledge routes (less accurate but fills gaps)

---

## MVP Success Metrics

| Metric | Target |
|--------|--------|
| Stations documented | 15+ |
| Routes documented | 80+ |
| Cities covered | 15+ destinations from Tunis |
| App downloads (first month) | 500+ |
| User contributions (first month) | 50+ |
| App store rating | 4.0+ |
| Daily active users (month 3) | 100+ |

---

## MVP Timeline (8 Weeks)

### Week 1: Foundation
- Set up GitHub repo
- Initialize Flutter project
- Initialize FastAPI backend
- Deploy to Railway/Supabase
- Create database schema

### Week 2: Map & Data
- Implement flutter_map with OSM tiles
- Design data entry form for field research
- Create station/route database entries for 15 seed stations
- GPS locations from Google Maps/OSM

### Week 3: Core Features
- Station detail screen
- Route list per station
- Search form (from → to)
- Basic filtering by mode

### Week 4: Offline + Polish
- Offline tile caching
- Language switching (AR/FR/EN)
- UI polish, Material Design
- Testing on iOS + Android

### Week 5: Contribute Feature
- User contribution form
- Moderation queue (manual review)
- Data validation
- "Report incorrect info" button

### Week 6: Field Research Sprint
- Visit Bab Saadoun + 4 other stations
- Document 50+ routes
- Upload data to production DB
- Take station photos

### Week 7: Integration Testing
- End-to-end testing
- Performance testing
- Beta test with 10-20 users
- Fix bugs

### Week 8: Launch
- App Store + Google Play submission
- Landing page
- Social media announcement
- Post-launch monitoring

---

## MVP Budget

| Item | Cost |
|------|------|
| Flutter development (open source) | $0 |
| FastAPI backend (Railway free tier) | $0 |
| Supabase (DB + Auth + Storage) | $0 |
| Firebase Auth (phone auth) | $0 |
| OpenStreetMap tiles | $0 |
| Domain name | $10/year |
| App Store developer account | $99/year (Apple) |
| Google Play developer account | $25 one-time |
| **Total** | **$134 first year** |

---

## MVP Team (Minimum)

| Role | Effort |
|------|--------|
| Flutter developer | Full-time 8 weeks |
| Backend developer | Part-time 4 weeks |
| Data researcher | 2 weekends (field) |
| Designer (optional) | Part-time 2 weeks |

**Can one person do it?** Yes — if that person can do Flutter + basic backend + field research. Timeline stretches to 12 weeks solo.

---

## MVP Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Louage data inaccurate | High | High | "Report incorrect" + community verification |
| No users | Medium | High | Seed with students, social media marketing |
| App Store rejection | Low | Medium | Follow guidelines, test thoroughly |
| Scope creep | High | Medium | Strict MVP boundary — Phase 2 can wait |
| Offline caching bugs | Medium | Medium | Test on slow 3G, fallback to online |
| Arabic RTL issues | Low | Medium | Use Flutter's built-in Directionality widget |

---

*Document created: 2026-09-18*
*Decision: Greater Tunis pilot, strict MVP scope, $134 budget*
