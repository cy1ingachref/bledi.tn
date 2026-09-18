# Free Tools, APIs & Resources — Tunisia Transport App

## All free or open source. No paid APIs required for MVP.

---

## 1. MAPS & GEOSPATIAL

### OpenStreetMap (OSM)
- **URL**: https://openstreetmap.org
- **License**: ODbL (open, attribution required)
- **Cost**: FREE
- **Use**: Base map, geocoding (Nominatim), POI data
- **Tunisia coverage**: Moderate (urban better, rural sparse)
- **Tile server**: https://tile.openstreetmap.org/{z}/{x}/{y}.png
- **Alternative tile servers**: MapTiler free tier, CARTO (free tier)

### Leaflet / Mapbox GL JS
- **Cost**: FREE
- **Use**: Interactive map in web app
- **Plugins**: Marker clustering, routing, offline tiles

### Overpass API
- **URL**: https://overpass.kumi.systems/api/interpreter
- **Cost**: FREE
- **License**: ODbL
- **Use**: Query OSM data for transport infrastructure
- **Rate limits**: Be polite, batch queries

### Nominatim (OSM Geocoding)
- **URL**: https://nominatim.openstreetmap.org
- **Cost**: FREE (self-host for production)
- **Use**: Address → lat/lng, reverse geocode
- **Rate limit**: 1 req/sec on public instance
- **Self-host**: Docker image available for production

### PostGIS
- **Cost**: FREE (open source)
- **Use**: Geospatial database queries
- **Key features**: ST_DWithin, ST_Distance, nearest-neighbor
- **Host**: Self-host or Railway/Supabase/Neon free tier

---

## 2. MOBILE APP FRAMEWORK

### Flutter
- **Cost**: FREE (open source, Google)
- **Platforms**: iOS + Android + Web + Desktop
- **Language**: Dart
- **Why Flutter over React Native**:
  - Better performance for map-heavy apps
  - Single codebase for all platforms
  - Stronger offline support
  - Built-in internationalization (Arabic RTL support)
  - google_maps_flutter, flutter_map, mapbox_gl packages
- **Map packages**: flutter_map (free OSM), google_maps_flutter (free tier)
- **State management**: Riverpod, Bloc

### Alternative: React Native
- **Cost**: FREE
- **Why not**: JavaScript bridge overhead, weaker offline story, RTL support harder

---

## 3. BACKEND & DATABASE

### PostgreSQL + PostGIS
- **Cost**: FREE
- **Use**: Main database with geospatial queries
- **Free hosting options**:
  - **Neon**: 500MB free, serverless, PostGIS support
  - **Supabase**: 500MB free, PostGIS built-in, Auth + Realtime
  - **Railway**: $5 credit/month free, PostgreSQL with PostGIS
  - **Self-host**: Docker on any VPS ($5/month minimum)

### FastAPI (Python)
- **Cost**: FREE
- **Use**: REST API backend
- **Why**: Async, auto-generated docs, easy to learn
- **ORM**: SQLAlchemy + GeoAlchemy2 for PostGIS
- **Hosting**: Railway, Render, Fly.io free tiers

### Alternative: Node.js + Express/NestJS
- **Cost**: FREE
- **Use**: If team knows JavaScript better

### Redis
- **Cost**: FREE
- **Use**: Caching, session store, pub/sub for realtime
- **Host**: Self-host or Upstash free tier (10k commands/day)

---

## 4. AUTH & USERS

### Firebase Auth
- **Cost**: FREE (Spark plan)
- **Use**: Phone number auth (essential for Tunisia), email auth
- **Limits**: 10k phone auth/month free (enough for MVP)
- **Tunisia context**: Phone > email for Tunisian users

### Supabase Auth
- **Cost**: FREE
- **Use**: Alternative to Firebase, phone auth via SMS provider
- **Limits**: 50k monthly active users free

---

## 5. IMAGE STORAGE & CDN

### Cloudflare R2
- **Cost**: FREE (10GB storage, 1M requests/month free)
- **Use**: User-uploaded photos (place photos, profile pics)
- **Egress**: FREE (unlike S3 which charges for egress)
- **CDN**: Built-in

### Image Compression
- **Client-side**: Flutter image_compress package
- **Server-side**: Pillow (Python) or sharp (Node.js)

---

## 6. REALTIME (Phase 3)

### Supabase Realtime
- **Cost**: FREE (500 concurrent connections)
- **Use**: Live location sharing, friend updates
- **Why**: WebSocket-based, works with PostgreSQL

### Firebase Realtime DB
- **Cost**: FREE (1GB storage, 10GB transfer/month)
- **Use**: Alternative for live location

### Server-Sent Events (SSE)
- **Cost**: FREE (built into HTTP)
- **Use**: Simpler alternative for one-way live updates

---

## 7. PUSH NOTIFICATIONS

### Firebase Cloud Messaging (FCM)
- **Cost**: FREE (unlimited messages)
- **Use**: Push notifications for new places, route alerts, friend requests
- **Tunisia**: Works on Android, limited on iOS (requires APNS setup)

### OneSignal
- **Cost**: FREE (up to 10k subscribers)
- **Use**: Alternative push service, easier iOS setup

---

## 8. HOSTING & DEPLOYMENT

### Backend Hosting
| Provider | Free Tier | PostGIS | Notes |
|----------|-----------|---------|-------|
| Railway | $5 credit/month | Yes | Easy deploy from GitHub |
| Render | 750 hours/month | Manual setup | Auto-deploy from GitHub |
| Fly.io | 3 shared VMs | Yes | Great for multi-region |
| Supabase | 500MB | Built-in | Auth + DB + Storage + Realtime |
| Neon | 500MB | Yes | Serverless Postgres |

### Frontend Hosting (Flutter Web)
- **Firebase Hosting**: FREE (10GB storage, 360MB/day transfer)
- **Vercel**: FREE (100GB bandwidth)
- **GitHub Pages**: FREE (static sites)
- **Netlify**: FREE (100GB bandwidth)

---

## 9. ANALYTICS

### PostHog
- **Cost**: FREE (1M events/month self-hosted, or cloud free tier)
- **Use**: Product analytics, feature flags, session recording
- **Tunisia-friendly**: Self-hosted option (no GDPR concerns)

### Plausible
- **Cost**: FREE self-hosted
- **Use**: Simple privacy-friendly analytics

---

## 10. DESIGN & UI

### Figma
- **Cost**: FREE (3 projects, unlimited files)
- **Use**: UI design, wireframes, prototyping
- **Plugins**: Map maker, icon libraries

### Material Design Icons
- **Cost**: FREE
- **Use**: Transport icons (bus, train, taxi, walk, louage van)

### Google Fonts
- **Cost**: FREE
- **Use**: Arabic fonts (Cairo, Tajawal), French/English fonts

---

## 11. ROUTING ENGINE (Phase 3)

### OSRM (Open Source Routing Machine)
- **Cost**: FREE
- **Use**: Walking/driving routing
- **Data source**: OpenStreetMap
- **Self-host**: Docker, needs ~2GB RAM for Tunisia data
- **Tunisia data**: Download OSM extract, extract with osrm-extract

### GraphHopper
- **Cost**: FREE (open source)
- **Use**: Multi-modal routing (walk + car + public transit)
- **Self-host**: Docker available
- **GTFS support**: Can combine with transit schedules

### Valhalla
- **Cost**: FREE
- **Use**: Multi-modal routing, isochrones
- **Self-host**: Docker, more complex setup

---

## 12. CI/CD & DEVOPS

### GitHub Actions
- **Cost**: FREE (2000 minutes/month)
- **Use**: Automated testing, Flutter build, deployment

### Docker
- **Cost**: FREE
- **Use**: Containerized backend, database, routing engine

---

## 13. LEGAL & PRIVACY

### Terms of Service / Privacy Policy
- **Generator**: https://www.iubenda.com (free basic) or https://www.termly.com
- **GDPR compliance**: Required if EU users
- **Tunisia data protection**: Law n°2004-63 (respect user consent)

---

## 14. ESTIMATED MONTHLY COST (MVP)

| Service | Cost |
|---------|------|
| Map tiles (OSM) | $0 |
| Supabase (DB + Auth + Storage) | $0 |
| Railway (backend hosting) | $0-5 |
| Firebase (Auth + Push) | $0 |
| Cloudflare R2 (photos) | $0 |
| GitHub (CI/CD + repo) | $0 |
| Figma (design) | $0 |
| PostHog (analytics) | $0 |
| **TOTAL** | **$0-5/month** |

---

## 15. RECOMMENDED STACK

| Layer | Choice | Cost |
|-------|--------|------|
| Mobile | Flutter | FREE |
| Backend | FastAPI + Supabase | FREE |
| Database | PostgreSQL + PostGIS (Supabase) | FREE |
| Maps | flutter_map + OSM | FREE |
| Auth | Firebase Auth (phone) | FREE |
| Storage | Supabase Storage | FREE |
| Realtime | Supabase Realtime | FREE |
| Push | Firebase Cloud Messaging | FREE |
| CI/CD | GitHub Actions | FREE |
| Hosting | Railway + Supabase | FREE |
| Analytics | PostHog | FREE |
| Design | Figma + Material Icons | FREE |

**Total MVP cost: $0-10/month**

---

*Document created: 2026-09-18*
*All tools verified as free/open source*
