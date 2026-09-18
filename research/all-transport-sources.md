# All Transport Data Sources — Tunisia

**Comprehensive extraction: 2026-09-18**
**Scope: Every public transport mode in Tunisia**

---

## 1. TUNIS LIGHT METRO (Métro Léger de Tunis)

| Field | Value |
|-------|-------|
| Operator | Transtu (Société des transports de Tunis) |
| Lines | 6 (Line 1, 2, 3, 4, 5, 6) |
| Stations | 65 |
| Length | 45.2 km |
| Opened | 1985 |
| Website | https://www.transtu.tn (OFFLINE) |
| Data availability | SPARSE in OSM (~25 stops mapped) |

### Lines and Stations (from Wikipedia)

**Line 1**: Tunis Marine → Ben Arous (1985)
**Line 2**: Place de Barcelone → Ariana (1989)
**Line 3**: Place de la République → Mohamed Ali (1990)
**Line 4**: Place de Barcelone → Den Den (1992)
**Line 5**: Place de Barcelone → Intilaka (1992)
**Line 6**: Tunis Marine → El Mourouj 4 (2008)

### Rolling Stock
- 135 × Siemens-Duewag TW 6000 (high-floor)
- 55 × Alstom Citadis 302 (low-floor)

### Key Hub Stations
- Tunis Marine (Lines 1, 3, 6) — connects to TGM, buses, louages
- Place de Barcelone (Lines 2, 4, 5)
- Place de la République (Lines 1, 3, 4)
- Ben Arous (Line 1 terminus)

### Schedule
- Operating hours: ~05:00 – 22:00
- Frequency: 5-10 min peak, 10-15 min off-peak
- Former peak-only lines: Line 12 (10 Décembre → El Ouardia 6), Line 14 (Den Den → El Ouardia 6)

---

## 2. TGM (Tunis-Goulette-Marsa)

| Field | Value |
|-------|-------|
| Type | Commuter rail |
| Route | Tunis Marine → La Marsa via La Goulette |
| Stations | ~10 |
| Operator | SNCFT |
| Data availability | MODERATE in OSM |

### Stations (north to south)
1. Tunis Marine (interchange with Metro Lines 1,3,6)
2. Le Bac
3. La Goulette
4. La Goulette Neuve
5. La Goulette Casino
6. Khereddine
7. L'Aéroport (Tunis-Carthage nearby)
8. Le Kram
9. Carthage-Salammbo
10. Sidi Bou Saïd
11. Sidi Dhrif
12. La Marsa

---

## 3. SNCFT (National Railway)

| Field | Value |
|-------|-------|
| Type | Intercity/regional rail |
| Website | https://www.sncft.com.tn (LIVE) |
| Data availability | HTML timetable pages (scrapable) |

### Lines

**Grandes Lines (Main Lines)**:
1. Tunis – Sousse – Monastir – Mahdia – Sfax – Gabès – Gafsa – Métlaoui – Tozeur
2. Tunis – Béja – Jendouba – Ghardimaou – Souk Ahras (Algeria)
3. Tunis – Manouba – Mateur – Tinja – Bizerte
4. Tunis – Gâafour – Dahmani – Le Kef – Jrissa – Kalâa Khasba
5. Tunis – Nabeul

### Key SNCFT Stations
- Tunis Marine (main hub)
- Tunis Ville
- Bardo
- Manouba
- Mateur
- Tinja
- Bizerte
- Sousse
- Monastir
- Mahdia
- Sfax
- Gabès
- Gafsa
- Tozeur
- Le Kef
- Jendouba
- Béja
- Nabeul
- Ghardimaou (border)

### Schedule
- Tunis-Sousse: ~10 trains/day each way
- Tunis-Sfax: ~6 trains/day each way
- Tunis-Bizerte: ~8 trains/day each way
- Tunis-Nabeul: ~4 trains/day each way

### Fare Examples (approximate)
- Tunis → Sousse: ~12 DT
- Tunis → Sfax: ~22 DT
- Tunis → Bizerte: ~5 DT
- Tunis → Nabeul: ~6 DT

---

## 4. TRANSTU (Tunis Urban Transport)

| Field | Value |
|-------|-------|
| Type | Metro + Bus |
| Website | transtu.com.tn (OFFLINE) |
| Metro lines | 6 (see section 1) |
| Bus lines | ~30 (limited data) |
| Data availability | VERY LOW (manual entry needed) |

### Bus Lines (partial, from Wayback Machine research)
- Bus lines serve areas not covered by metro
- Key routes: Tunis Centre → suburbs (Manouba, Ariana, Ben Arous, El Ouardia)
- Fare: ~0.500 DT for urban bus

---

## 5. BIZETECONNECT (Bizerte Governorate Bus)

| Field | Value |
|-------|-------|
| Type | Intercity + local bus |
| Website | https://www.bizerteconnect.com (LIVE) |
| Lines | 131 |
| Stations | 120+ named locations |
| Data availability | HIGH (visible in filter dropdowns, but schedule data is client-side rendered) |

### Coverage
- Internal Bizerte: 100+ lines
- To Tunis: Multiple lines (Confort, Standard, Commerciale)
- To other governorates: Mateur, Rafraf, Menzel Bourguiba, etc.

### Key Stations
- Bizerte (main hub)
- Menzel Bourguiba
- Menzel Jemil
- Menzel Abderrahmane
- Mateur
- Tinja
- Ras Jebel
- Rafraf
- Ghar El Melh
- Sejnane
- Utique
- El Alia
- Bab Saadoun (Tunis connection)

### Line Types
- **Confort**: Air-conditioned, non-stop, Tunis highway
- **Standard**: Regular service, more stops
- **Commerciale**: Airport connection
- **Scolaire**: School-only routes
- **Dimanche**: Sunday-only routes

---

## 6. LOUAGE (Informal Shared Taxis)

| Field | Value |
|-------|-------|
| Type | Informal shared taxi (minibus, 9 seats) |
| Official data | ZERO |
| Real data source | destination-tunis.fr (reader-verified fares 2015-2026) |
| Data availability | MEDIUM (crowdsourced + field research needed) |

### Types
| Stripe | Scope | Behavior |
|--------|-------|----------|
| White + Red | Inter-governorate | Full-only, no stops, long distance |
| White + Blue | Intra-governorate | Can leave half-full, stops at villages |
| Yellow + Blue | Rural | Very slow, fills at souks ("Doliprane") |

### Operating Hours
- First departure: ~06:00
- Last reliable: 19:00 (summer), 17:00 (winter)
- Summer/Ramadan: Afternoon/evening very calm

### Price Rule
- ~7 DT per hour of travel (regulated by state)

### Major Louage Stations in Tunis
- **Bab Saadoun**: North routes (Bizerte, Le Kef, Tabarka, Béja, Jendouba)
- **Bab Alioua**: South/Cap Bon (Hammamet, Nabeul, Kelibia, Zaghouan)
- **Moncef Bey**: Center & South (Sousse, Monastir, Kairouan, Mahdia, Sfax, Gabès)
- **Tunis Marine**: Coastal/suburban (La Marsa, La Goulette, Carthage)

### Verified Fares (2023-2026, from destination-tunis.fr)

| From | To | Fare (DT) | Verified |
|------|----|-----------|----------|
| Tunis (Bab Saadoun) | Bizerte | 6.500 | Feb 2025 |
| Tunis (Bab Saadoun) | Jendouba | 14.500 | Oct 2025 |
| Tunis (Bab Saadoun) | Tabarka | 15.000 | Sep 2023 |
| Tunis (Bab Saadoun) | Le Kef | 15.000 | Oct 2024 |
| Tunis (Bab Saadoun) | Ras Jebel | 5.700 | Oct 2025 |
| Tunis (Bab Alioua) | Hammamet Nord | 6.800 | Feb 2025 |
| Tunis (Bab Alioua) | Yasmine Hammamet | 4.750 | Aug 2022 |
| Tunis (Bab Alioua) | Zaghouan | 5.350 | Jul 2025 |
| Tunis (Bab Alioua) | Korba | 6.800 | Jul 2023 |
| Tunis (Bab Alioua) | Kélibia | 8.800 | Aug 2022 |
| Tunis (Moncef Bey) | Sousse | 13.500 | Oct 2024 |
| Tunis (Moncef Bey) | Monastir | 14.850 | Feb 2025 |
| Tunis (Moncef Bey) | Kairouan | 14.600 | Dec 2024 |
| Tunis (Moncef Bey) | Mahdia | 17.650 | Aug 2023 |
| Tunis (Moncef Bey) | Médenine | 40.000 | May 2026 |
| Tunis Marine | La Marsa | 1.700 | Oct 2023 |
| Hammamet | Tunis | 6.800 | Apr 2024 |
| Yasmine Hammamet | Tunis | 5.500 | May 2024 |
| Yasmine Hammamet | Sousse | 8.600 | Feb 2023 |
| Yasmine Hammamet | Kairouan | 11.000 | Mar 2024 |
| Yasmine Hammamet | Nabeul | 2.000 | Oct 2024 |
| Médina Hammamet | Yasmine Hammamet | 0.700 | Mar 2024 |
| Nabeul | Tunis | 6.600 | Oct 2025 |
| Nabeul | Sousse | 8.300 | Sep 2022 |
| Nabeul | Kairouan | 10.600 | Oct 2025 |
| Nabeul | Kélibia | 5.350 | Oct 2025 |
| Nabeul | Monastir | 10.900 | Oct 2025 |
| Nabeul | Zaghouan | 6.500 | Oct 2025 |
| Sousse | Tunis | 13.500 | Dec 2025 |
| Sousse | Monastir | 2.400 | Dec 2025 |
| Sousse | Sfax | 12.400 | Feb 2025 |
| Sousse | Gabès | 22.300 | Feb 2025 |
| Sousse | Kairouan | 6.200 | Dec 2024 |
| Sousse | Le Kef | 19.000 | Oct 2024 |
| Sousse | El Jem | 8.600 | Feb 2025 |
| Sousse | Mahdia | 5.900 | Dec 2024 |
| Sousse | Médenine | 27.000 | Jun 2026 |
| Sousse | Béja | 21.000 | Jul 2025 |
| Sousse | Jendouba | 21.000 | Jul 2025 |
| Monastir | Kairouan | 7.950 | Feb 2025 |
| Mahdia | El Jem | 8.000 | Apr 2024 |
| Sfax | Tunis | 22.750 | Mar 2023 |
| Sfax | Kébili | 21.000 | Jan 2025 |
| Gabès | Tunis | ~25.000 | (estimated) |
| Gabès | Sousse | 22.300 | Feb 2025 |
| Gabès | Médenine | 7.050 | Aug 2026 |
| Gabès | Tozeur | 17.600 | Feb 2025 |
| Gabès | Djerba | 14.550 | Feb 2025 |
| Bizerte | Béja | 9.250 | Jul 2025 |
| Béja | Tabarka | 6.500 | Jul 2025 |
| Le Kef | Kasserine | 11.500 | Oct 2023 |
| Jendouba | Bousalem | 1.800 | Oct 2023 |
| Bousalem | Béja | 2.400 | Oct 2023 |

---

## 7. SNTRI (Intercity Bus)

| Field | Value |
|-------|-------|
| Type | Intercity bus |
| Website | NONE FOUND |
| Data availability | ZERO (manual research only) |

### Known Routes (from common knowledge)
- Tunis ↔ Sousse ↔ Sfax ↔ Gabès
- Tunis ↔ Bizerte ↔ Béja ↔ Jendouba
- Tunis ↔ Kairouan ↔ Kasserine
- Tunis ↔ Nabeul ↔ Hammamet
- Tunis ↔ Le Kef ↔ Gafsa

### Estimated Fares
- Tunis → Sousse: ~15 DT
- Tunis → Sfax: ~25 DT
- Tunis → Bizerte: ~7 DT

---

## 8. TAXI

| Field | Value |
|-------|-------|
| Type | Informal metered taxi |
| Ride-hailing apps | Bolt, Yassir (urban Tunisia) |
| Data availability | LOW (informal stands, no published locations) |

### Types
- **Taxi jaune** (yellow): Metered street-hail, urban
- **Taxi longue distance**: Negotiated, intercity
- **Louage privatisé**: Full minibus booking (~200 DT for 8 seats)

### Taxi Stands (known)
- Major louage stations have taxi stands nearby
- Tunis Marine (main hub)
- Bab Saadoun
- Sousse, Sfax, Bizerte city centers

### Urban Fare (Bolt/Yassir)
- Base: ~1.5 DT
- Per km: ~0.5 DT
- Minimum: ~3 DT
- Tunis center to La Marsa: ~15-20 DT

---

## 9. FERRY

| Field | Value |
|-------|-------|
| Operator | Compagnie Tunisienne de Navigation (CTN) |
| Data availability | MODERATE (schedules published) |

### Routes
- **Sfax ↔ Kerkennah**: Daily, ~20 DT, ~1 hour
- **Sfax ↔ Djerba**: Daily, ~30 DT, ~4 hours
- **Tunis ↔ Marseille**: International, weekly

### Kerkennah Ferry
- Sfax Port → Kerkennah (Sidi Fredj)
- Departures: ~07:00, ~14:00 (summer), ~07:00, ~12:00 (winter)
- Duration: 1-1.5 hours
- Fare: ~20 DT

---

## 10. DOMESTIC FLIGHTS

| Field | Value |
|-------|-------|
| Carrier | Tunisair Express |
| Data availability | HIGH (online booking) |

### Routes
- Tunis ↔ Djerba (multiple daily)
- Tunis ↔ Sfax (daily)
- Tunis ↔ Tozeur (seasonal)
- Tunis ↔ Gabès (seasonal)
- Tunis ↔ Tabarka (seasonal)
- Tunis ↔ Gafsa (seasonal)

### Fares
- Tunis → Djerba: ~150-300 DT
- Tunis → Sfax: ~120-250 DT
- Bookable at https://www.tunisair.com

---

## 11. OPENSTREETMAP TUNISIA COVERAGE

| Field | Value |
|-------|-------|
| Download | https://download.geofabrik.de/africa/tunisia.html |
| Format | PBF |
| License | ODbL |

### Coverage Quality
| Category | Coverage |
|----------|----------|
| Roads | GOOD |
| Bus stations | SPARSE (~15 in Greater Tunis) |
| Metro stops | SPARSE (~25 stops mapped) |
| Train stations | MODERATE (major hubs mapped) |
| Louage stations | ZERO |
| Taxi stands | VERY SPARSE |

### Useful OSM Tags for Tunisia
- `amenity=bus_station`
- `public_transport=station`
- `public_transport=stop_position`
- `highway=bus_stop`
- `railway=station`
- `railway=stop`
- `amenity=taxi`
- `amenity=ferry_terminal`
- `railway=light_rail`

---

## 12. DATA ACQUISITION STRATEGY SUMMARY

| Mode | Best Source | Effort | Quality |
|------|-------------|--------|---------|
| Metro | Wikipedia + field verification | Medium | High |
| TGM | OSM + field verification | Low | High |
| SNCFT | sncft.com.tn web scrape | Medium | High |
| Transtu Bus | Wayback Machine + field research | High | Low |
| Bizerte Bus | bizerteconnect.com filter dropdowns | Medium | High |
| Louage | Field research + crowdsourcing | Very High | Medium |
| SNTRI Bus | Field research (no digital source) | Very High | Low |
| Taxi | Bolt/Yassir + field research | Medium | Medium |
| Ferry | CTN website | Low | High |
| Flights | Tunisair website | Low | High |

---

## 13. APIS AND TOOLS

| Tool | URL | Use |
|------|-----|-----|
| Overpass API | https://overpass.kumi.systems/api/interpreter | Query OSM transport data |
| Nominatim | https://nominatim.openstreetmap.org | Geocoding |
| Geofabrik | https://download.geofabrik.de/africa/tunisia.html | Full OSM extract |
| SNCFT | https://www.sncft.com.tn/voyageurs/horaires/ | Train schedules (HTML) |
| BizerteConnect | https://www.bizerteconnect.com/bus-schedules | Bus schedules (JS-rendered) |
| Transtu | https://www.transtu.tn | Metro/bus (OFFLINE) |
| destination-tunis.fr | https://destination-tunis.fr/se-deplacer/principe-fonctionnement-louage-tunisie/ | Louage fares |
| CTN | https://www.ctn.com.tn | Ferry schedules |
| Tunisair | https://www.tunisair.com | Flight booking |
| OSM Tunisia Wiki | https://wiki.openstreetmap.org/wiki/Tunisia | OSM conventions |
| Wikipedia Metro | https://en.wikipedia.org/wiki/Tunis_Light_Metro | Metro line details |

---

*Comprehensive extraction completed: 2026-09-18*
*Next step: Field research at Bab Saadoun + full data entry*
