# Competitor Landscape & Gap Analysis — Tunisia Transport

## Global Competitors

| App | Type | Tunisia Support | Cost | Strengths | Weaknesses |
|-----|------|-----------------|------|-----------|------------|
| Google Maps | Global mapping | Roads + walk, limited transit | Free (consumer) | Excellent POI, routing, Street View | No louages, no Tunisian transit schedules, English-only UI, high data usage |
| Moivit | Urban transit | Tunis, Sousse (bus + metro) | Free | Multi-modal urban routing | No louages, no intercity, no places/rating, weak Tunisia coverage |
| Rome2rio | Global multi-modal | Tunisia routes visible | Free | Shows transport options | No real-time, inaccurate Tunisia data, no booking |
| Maps.me | Offline maps | Tunisia roads | Free | Offline-first, OSM-based | No transit data |

## Tunisia-Specific Apps

| App | Status | Features | Gap |
|-----|--------|----------|-----|
| Bolt | Active (Tunis, Sousse) | Ride-hailing, food delivery | Only ride-hailing, no intercity, no louages |
| Yassir | Active (urban) | Ride-hailing, delivery | Same as Bolt |
| Uber | NOT in Tunisia | — | — |
| InDrive | Active (some cities) | Ride-hailing | Only ride-hailing |

## TuGo (Open Source — Abandoned)
- **GitHub**: BouajilaHamza/TuGo
- **Stack**: Flutter + MongoDB + FastAPI
- **Status**: Last commit July 2024
- **Was building**: Real-time bus/train schedules, community reports
- **Why it failed**: Probably couldn't solve the data problem (same as us)
- **Lesson**: Data sourcing is the bottleneck, not the tech

---

## Gap Analysis — What Nobody Does

### CRITICAL GAP: Louage Data
- No app has louage routes, stations, or fares
- Google Maps shows roads but no louage stops
- This is the #1 unmet need in Tunisian transport
- Opportunity: First-mover advantage in louage digitization

### SIGNIFICANT GAP: Multi-Modal Intercity
- No app combines louage + bus + train + metro for intercity trips
- Example need: "How do I get from Tunis to Sousse?" → Should show all 4 options
- Current solution: Ask on Facebook groups

### MODERATE GAP: Places + Transport Integration
- No app shows "nearest louage station to this restaurant"
- No app shows "how to reach this place using public transit"
- Google Maps does car routing but not louage/bus

### MODERATE GAP: Tunisian Arabic UI
- Most apps are English-only or French-only
- Local Tunisian Arabic would differentiate
- Requires RTL (right-to-left) support in Flutter

### MINOR GAP: Offline-First
- Many Tunisians have intermittent connectivity
- Offline caching of transport data is a differentiator
- flutter_map supports offline tile caching

---

## Market Opportunity

### Target Users
1. **University students** (largest mobile-first demographic) — need cheap intercity travel
2. **Daily commuters** in Greater Tunis — need metro/bus/louage info
3. **Tourists in Tunisia** — confused by informal transport, need guidance
4. **Working professionals** — commute optimization

### User Pain Points (Ranked)
1. "I don't know which louage station to go to" — BIGGEST
2. "I don't know the fare" — Trust issue
3. "I don't know when the next louage leaves" — Uncertainty
4. "I don't know how to get from A to B using public transit" — Multi-modal
5. "I want to discover new places near me" — Discovery

### Monetization (Phase 4)
- Louage station owners pay for "verified station" badge
- Restaurants pay for "near this louage station" promotion
- Bolt/Yassir affiliate for "book taxi from this station"
- Tourism board partnerships for "Tunisia routes"

---

## Competitive Advantage Strategy

### 1. Own the Louage Niche
- First and only app with comprehensive louage data
- Network effects: More users → more data → better product

### 2. Multi-Modal Superiority
- Combine ALL transport modes in one view
- "Show me the cheapest/fastest way to Sousse"

### 3. Community-Driven
- Users contribute route updates, photos, reviews
- Lower data acquisition cost than competitors

### 4. Offline-First
- Works even with bad 3G in rural Tunisia
- Competitors assume always-online

### 5. Local-First
- Tunisian Arabic UI
- Tunisian-specific features (louage "fill-and-go" times)

---

## Risk: What Competitors Could Do

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Bolt adds louage booking | Medium | High | Bolt doesn't have data, can't bootstrap |
| Google Maps adds Tunisia transit | Low | Medium | Google has ignored Tunisia for years |
| Moovit expands louage coverage | Low | Medium | Moivit is urban-focused, no intercity |
| TuGo or similar revives | Low | Low | Abandoned, but could be forked |

---

*Analysis completed: 2026-09-18*
*Based on actual web research, GitHub repo analysis, and HTTP verification*
