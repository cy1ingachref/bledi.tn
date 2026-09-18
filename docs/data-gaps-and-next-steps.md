# BLEDI.TN — Transport Modes Summary

## What's Documented

### With Digital Data (scrapable / API / OSM)
| Mode | Lines/Stations | Source | Action |
|------|----------------|--------|--------|
| Metro Tunis | 6 lines, 65 stations | Wikipedia | Extract station lists per line |
| TGM | 10 stations | OSM (partial) | Verify with field research |
| SNCFT Rail | 5 main lines, ~20 stations | sncft.com.tn HTML | Scrape timetable pages |
| BizerteConnect Bus | 131 lines, 120+ stops | bizerteconnect.com | Scrape schedule JS |
| CTN Ferry | 2 domestic routes | ctn.com.tn | Scrape schedules |
| Tunisair Express | 6 domestic routes | tunisair.com | Scrape schedules |

### With Reader-Verified Data (manual entry)
| Mode | Records | Source | Action |
|------|---------|--------|--------|
| Louage fares | 40+ verified | destination-tunis.fr | Already in seed_routes_destination_tunis.json |

### Needs Field Research (no digital data)
| Mode | What to Document | Where |
|------|------------------|-------|
| Louage stations | GPS, name, routes served | Bab Saadoun, Bab Alioua, Moncef Bey |
| Louage routes | All destinations per station | Station chiefs |
| Louage schedule | First/last departure, frequency | Direct observation |
| SNTRI bus | Routes, fares, schedules | Intercity bus stations |
| Taxi stands | GPS, routes | Major transport hubs |
| Transtu bus | ~30 lines, stations | Tunis stations + Wayback Machine |
| Domestic flights | Exact schedules | Tunisair.com (already have routes) |

---

## Data Gaps to Fill

1. **Louage stations in Tunis**: GPS coordinates for Bab Saadoun, Bab Alioua, Moncef Bey (need field visit)
2. **Louage route network**: Each station serves which destinations (need station chief interviews)
3. **Metro line station lists**: Wikipedia has them but needs structuring into DB
4. **BizerteConnect schedule times**: Client-side rendered, needs headless browser
5. **Transtu bus network**: Website offline, need Wayback Machine or physical maps
6. **Taxi stand locations**: No digital source, field research needed
7. **SNTRI intercity bus**: No website, field research at stations needed

---

## Recommended Next Action

**Option A: Field Research Sprint** (recommended for MVP)
- Visit Bab Saadoun (main louage hub)
- Document all routes, fares, GPS
- Get louage station locations for Bab Alioua, Moncef Bey
- Photograph any posted timetables

**Option B: Continue Scraping**
- Scrape SNCFT timetable pages (sncft.com.tn)
- Scrape BizerteConnect with headless browser (Playwright)
- Extract metro station lists from Wikipedia
- Scrape CTN ferry schedules

**Option C: Build App with Existing Data**
- We have 59 louage fares + 41 BizerteConnect lines = enough for MVP
- Launch with Greater Tunis pilot
- Crowdsource corrections and additions

---

*Summary: 2026-09-18 — All digital sources exhausted, field research is the bottleneck for louage/SNTRI/taxi data.*
