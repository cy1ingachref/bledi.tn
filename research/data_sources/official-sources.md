# Official Transport Data Sources — Tunisia

## Status: Confirmed (Verified 2026-09-18)

---

## 1. SNCFT — Société Nationale des Chemins de Fer Tunisiens
- **Website**: https://www.sncft.com.tn (French, Arabic, English)
- **What exists**: Timetables published on website, route maps
- **API**: NONE — all data is on HTML pages or PDF
- **Data format**: HTML timetable pages + PDF schedules
- **Lines**: Tunis–Sfax, Tunis–Sousse, Tunis–Bizerte, TGM (Tunis–Goulette–Marsa)
- **Scraping feasibility**: HIGH — WordPress site, schedule pages are static HTML
- **License**: Public info, commercial use unclear — safe for MVP
- **Menu structure**: La SNCFT → Voyageurs → Horaires / Tarifs / Gares

## 2. Transtu — Société de Transport de Tunis
- **Domain**: transtu.com.tn (OFFLINE from public internet, requires VPN or local ISP)
- **What exists**: Tunis metro léger (light rail), urban bus routes
- **Website archive**: Wayback Machine has snapshots from 2023-2024
- **Lines**: 6 metro léger lines (M1-M6), ~30 bus lines
- **Scraping feasibility**: LOW — site is down/offline
- **Alternative**: Manual entry from physical maps at stations, screenshots from Wayback Machine
- **Status**: The company still operates but web presence is minimal

## 3. SNTRI — Société Nationale de Transport Interurbain
- **Website**: NONE confirmed (snrti.com.tn didn't resolve)
- **What exists**: PDF timetables on SNCFT website sometimes list connections
- **Data**: Intercity bus routes Tunis–Sousse–Sfax–Bizerte–Nabeul–Kairouan
- **Scraping feasibility**: NONE — no digital presence found
- **Alternative**: Manual research at intercity bus stations

## 4. Louages — Informal Shared Taxis
- **Official digital data**: ZERO
- **What exists**: Word of mouth, Facebook groups, station "chefs de gare"
- **Key stations**: Bab Saadoun (main hub), Bab Alioua, Bab Jallad, Bab El Khadra, Sousse, Sfax
- **Data collection strategy**: Field research + crowdsourcing
- **Facebook groups**: "Les Louages en Tunisie", "Louage Tunisie", regional groups

## 5. OpenStreetMap — Tunisia Coverage
- **Coverage quality**: SPARSE
- **Bus stations in Greater Tunis**: ~15 nodes in OSM (very incomplete)
- **Light rail stops (Tunis metro léger)**: ~25 stops mapped (partially complete)
- **Train stations**: Few mapped, mainly major hubs (Tunis Marine, Sfax, Sousse)
- **Louage stations**: ALMOST ZERO
- **Download source**: https://download.geofabrik.de/africa/tunisia.html (PBF format)
- **License**: ODbL (open, attribution required)
- **Use**: Base map + partial station locations

## 6. OpenStreetMap — Overpass API Access
- **Working endpoint**: https://overpass.kumi.systems/api/interpreter (reliable)
- **Main endpoint**: https://overpass-api.de/api/interpreter (rate-limited, often 406)
- **License**: ODbL

## 7. Existing Tunisia Transport Apps (Competitors)

### TuGo (BouajilaHamza/TuGo on GitHub)
- **Stack**: Flutter + MongoDB + FastAPI
- **Purpose**: Real-time Tunisia transport info (bus + train)
- **Status**: Last commit July 2024 (abandoned)
- **Stars**: ~5-10 (low)
- **Insight**: Community-driven data model is right approach, but louage data is the missing piece

### Other Apps
- Bolt: Ride-hailing only, urban Tunisia
- Yassir: Ride-hailing only
- Google Maps: Car + walk, limited public transit
- Moovit: Urban transit only, no louages

---

## 8. Alternative Data Sources

### Administrative Boundaries
- **Repo**: https://github.com/mn-youssef/state-municipality-tunisia
- **Content**: Governorate and municipality boundaries GeoJSON for all 24 governorates
- **Use**: Region filtering, administrative grouping

### Wayback Machine
- Transtu historical snapshots may have route maps
- URL pattern: https://web.archive.org/web/2024*/transtu.com.tn

### Google Maps / Places
- Has restaurant/café/POI data for Tunisia
- No louage data
- Not free at scale ($500/month for production)

### Facebook Groups
- "Les Louages en Tunisie" — community-maintained route info
- Regional groups for each city
- Manual extraction possible

---

## 9. Data Acquisition Strategy Summary

| Source | Method | Effort | Quality |
|--------|--------|--------|---------|
| SNCFT train schedules | Web scrape sncft.com.tn | Medium | High |
| SNCFT train stations | OSM + manual geocode | Low | High |
| Transtu metro/bus | Manual from stations + Wayback | High | Medium |
| SNTRI intercity buses | Manual from bus stations | High | Medium |
| Louage stations & routes | FIELD RESEARCH + crowdsourcing | Very High | Medium |
| POIs (places) | OSM + crowdsourcing + Google Places | Medium | Medium |
| Admin boundaries | GitHub repo (free) | Low | High |
| Base map tiles | OpenStreetMap (free) | Low | High |

---

## 10. Critical Finding: The Louage Data Problem

Louages have NO official digital data. This is the core risk and the core value proposition. Three approaches:

### Option A: Field Research First (Recommended)
- Visit 5 major louage stations in Tunis
- Document all routes, fares, departure patterns
- Create seed dataset of ~100 routes
- Launch MVP with this data

### Option B: Crowdsourcing-First
- Build app with empty louage data
- Users submit routes they know
- Gamify contributions
- Risk: Cold start problem

### Option C: Hybrid (Best)
- Field research for 50-100 seed routes
- Launch with seed data
- Crowdsourcing for corrections + expansion
- This is the recommended approach

---

*Research completed: 2026-09-18*
*Sources verified via actual HTTP requests*
