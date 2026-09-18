# Project Tunisia Transport — Quick Start Guide

## What We've Built So Far
- Master plan document
- Data source research (verified live websites, GitHub repos, OSM coverage)
- Free tools & APIs catalog (everything $0)
- Competitor landscape analysis
- Louage field research toolkit
- MVP scope & pilot city selection

---

## Project Structure
```
TunisiaTransport/
├── docs/
│   ├── master-plan.md              # Full 4-phase roadmap
│   ├── free-tools-and-apis.md      # All free tools catalog
│   ├── mvp-scope-and-pilot.md      # MVP definition + timeline
├── research/
│   ├── data_sources/
│   │   └── official-sources.md     # Verified data sources (SNCFT, OSM, etc.)
│   ├── competitor-analysis.md      # Competitor landscape
│   ├── field-research-toolkit.md   # Louage station research toolkit
├── data/                           # Raw data goes here
├── src/                            # App source code goes here
```

---

## Verified Facts (Not Assumptions)

### Data Reality Check
1. **SNCFT** (train schedules): Website exists, has timetable pages. Scrapable.
2. **Transtu** (Tunis metro/bus): Website is OFFLINE. Wayback Machine only. Manual entry needed.
3. **SNTRI** (intercity buses): No website found. Manual entry only.
4. **Louages**: ZERO official data. Must be built from scratch.
5. **OSM coverage**: SPARSE. ~15 bus stations in all of Greater Tunis. ~25 metro stops. ~0 louage stations.

### Existing Open Source Projects
- **TuGo** (Flutter + FastAPI + MongoDB): Abandoned since July 2024. Similar concept but no louage data.
- **Tunisia admin boundaries** (GitHub): Free GeoJSON for 24 governorates. Use for region filtering.

### Tools Verified Working
- **Overpass Kubuntu** (overpass.kumi.systems): Working. Can query OSM data.
- **OSM tiles**: Free, working.
- **Flutter + flutter_map**: Proven combo for offline maps.
- **Supabase + FastAPI**: Free tiers verified.

---

## Immediate Next Steps (Pick One)

### Option A: Start Building MVP Right Now
1. `flutter create tunisia_transport` (in src/)
2. Set up Supabase project (free)
3. Set up FastAPI on Railway (free)
4. Implement map view with flutter_map
5. Enter 15 seed stations manually

### Option B: Field Research First (Recommended)
1. Print the field research toolkit
2. Visit Bab Saadoun this weekend
3. Document 20+ routes
4. Use that data to build MVP

### Option C: Fork TuGo as Starting Point
1. Clone BouajilaHamza/TuGo
2. Merge what works
3. Replace MongoDB with PostgreSQL+PostGIS
4. Add louage data

### Option D: Full Planning Mode
1. Create Figma wireframes
2. Set up GitHub repo
3. Set up project board (GitHub Projects)
4. Start weekly sprints

---

## Recommendation: Option B → A Hybrid

The bottleneck for this app is DATA, not code. The tech stack is standard Flutter + FastAPI + PostGIS — any mid-level dev can build it. What nobody has is louage data.

**Best path**:
1. This weekend: Field research at Bab Saadoun (4 hours, document 30+ routes)
2. Week 1: Set up repo, Flutter project, Supabase
3. Week 2: Map view + seed data entry
4. Week 3-4: Core features
5. Week 5: Beta launch

---

## What I Can Do Right Now

- [ ] Set up Flutter project skeleton
- [ ] Create Supabase project (you'd need to provide email)
- [ ] Create GitHub repo (cy1ingachref/tunisia-transport?)
- [ ] Generate seed data JSON from known louage routes
- [ ] Write API endpoints (FastAPI)
- [ ] Scrape SNCFT schedule pages
- [ ] Create Google Form for crowdsourcing

---

## Decision Needed

What's your priority?
1. Build code immediately (I can scaffold Flutter + API now)
2. Do field research first (I'll prepare the research kit and seed data)
3. Fork TuGo and adapt (fastest to prototype)
4. More planning (Figma, architecture, etc.)

Pick a direction and I'll execute.
