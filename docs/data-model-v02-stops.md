# Transport Data Model — Stops & Midway Stations Support

## Current State (MVP v0.1)
Simple origin→destination routes with fare and duration.

## Problem
User wants: "Show me the closest transport to my location, then the lines from where I am to where I'm going, with all midway stops."

This requires modeling:
1. **Stations** (already have)
2. **Lines** (routes with ordered stop sequences)
3. **Stops** (each station on a line, with order/position)
4. **Departures** (schedule times per line per direction)
5. **User queries** (from my location → to destination → show best options)

---

## Data Model v0.2 — Line-Based with Stops

### Core Entities

#### 1. Station (Transport Stop)
```sql
CREATE TABLE stations (
    id SERIAL PRIMARY KEY,
    name_ar VARCHAR(200) NOT NULL,
    name_fr VARCHAR(200),
    name_en VARCHAR(200),
    location GEOGRAPHY(Point, 4326),
    governorate VARCHAR(100),
    station_type VARCHAR(20), -- 'bus_stop', 'louage_station', 'train_station', 'metro', 'taxi_stand'
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### 2. Line (Route)
```sql
CREATE TABLE lines (
    id SERIAL PRIMARY KEY,
    line_number VARCHAR(50), -- "23", "7/4", "Confort"
    line_name VARCHAR(200), -- "Ligne Ain El Berda"
    operator VARCHAR(100), -- "BizerteConnect", "SNCFT", "Transtu"
    mode VARCHAR(20), -- 'bus', 'louage', 'train', 'metro', 'taxi'
    description TEXT, -- "Inter-governorate", "Internal Bizerte", "Confort service"
    is_active BOOLEAN DEFAULT TRUE,
    schedule_type VARCHAR(30), -- 'fixed', 'when_fill', 'on_demand'
    frequency_description TEXT, -- "Every 30 min", "When full"
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### 3. Line Station (Stop Sequence)
```sql
CREATE TABLE line_stations (
    id SERIAL PRIMARY KEY,
    line_id INT REFERENCES lines(id),
    station_id INT REFERENCES stations(id),
    stop_order INT NOT NULL, -- 1, 2, 3... along the line
    is_origin BOOLEAN DEFAULT FALSE,
    is_destination BOOLEAN DEFAULT FALSE,
    distance_from_origin_km FLOAT,
    cumulative_duration_min INT,
    UNIQUE(line_id, stop_order)
);
```

#### 4. Departure (Schedule)
```sql
CREATE TABLE departures (
    id SERIAL PRIMARY KEY,
    line_id INT REFERENCES lines(id),
    direction INT, -- 0 = outbound, 1 = return
    departure_time TIME,
    days_of_week INT[], -- {1,2,3,4,5} for weekdays, etc.
    season VARCHAR(20), -- 'summer', 'winter', 'all'
    is_active BOOLEAN DEFAULT TRUE
);
```

#### 5. Fare (Price between any two stops on a line)
```sql
CREATE TABLE fares (
    id SERIAL PRIMARY KEY,
    line_id INT REFERENCES lines(id),
    from_station_id INT REFERENCES stations(id),
    to_station_id INT REFERENCES stations(id),
    fare_millesime INT, -- fare in millimes (1000 = 1 DT)
    verified_date DATE,
    source VARCHAR(50)
);
```

#### 6. User Contribution
```sql
CREATE TABLE contributions (
    id SERIAL PRIMARY KEY,
    contributor_id UUID,
    contribution_type VARCHAR(20), -- 'new_line', 'new_station', 'correction', 'fare_update'
    data JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    reviewed_by INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Algorithm: "How do I get from A to B?"

### Input
- User's current location (lat, lng) — from GPS or manual selection
- Desired destination (lat, lng or station name)
- Optional: preferred mode (bus/louage/train/metro/any), max walking distance

### Output
- List of options, each containing:
  - Closest station(s) to user with walking distance
  - Line(s) available from that station
  - Stops along the way (ordered)
  - Destination station
  - Next departure times
  - Total estimated duration (walk + wait + ride)
  - Fare

### Algorithm Steps

```
FIND_ROUTES(user_location, destination, preferences):
    
    # Step 1: Find nearest stations to user (within max_walk_km)
    user_nearby = QUERY:
        SELECT id, name, location, 
               ST_Distance(location, user_location) as walk_distance
        FROM stations
        WHERE ST_DWithin(location, user_location, max_walk_km)
        ORDER BY walk_distance
        LIMIT 5
    
    # Step 2: Find nearest stations to destination
    dest_nearby = QUERY:
        SELECT id, name, location,
               ST_Distance(location, destination) as walk_distance
        FROM stations
        WHERE ST_DWithin(location, destination, max_walk_km)
        ORDER BY walk_distance
        LIMIT 5
    
    # Step 3: Find lines connecting user's nearby stations to destination's nearby stations
    # For bus/louage: same line must contain both origin and dest stations
    # with origin_order < dest_order (correct direction)
    connections = QUERY:
        SELECT 
            l.id as line_id,
            l.line_number,
            l.line_name,
            l.mode,
            l.frequency_description,
            ls_origin.stop_order as origin_order,
            ls_dest.stop_order as dest_order,
            s_origin.name as origin_station,
            s_dest.name as dest_station,
            user_nearby.walk_distance as walk_to_origin,
            dest_nearby.walk_distance as walk_to_dest
        FROM lines l
        JOIN line_stations ls_origin ON l.id = ls_origin.line_id
        JOIN line_stations ls_dest ON l.id = ls_dest.line_id
        JOIN stations s_origin ON ls_origin.station_id = s_origin.id
        JOIN stations s_dest ON ls_dest.station_id = s_dest.id
        WHERE ls_origin.stop_order < ls_dest.stop_order
          AND ls_origin.station_id IN (SELECT id FROM user_nearby)
          AND ls_dest.station_id IN (SELECT id FROM dest_nearby)
        ORDER BY (user_nearby.walk_distance + dest_nearby.walk_distance)
    
    # Step 4: For each connection, get the midway stops
    FOR EACH connection IN connections:
        midway_stops = QUERY:
            SELECT s.name, ls.stop_order, ls.cumulative_duration_min
            FROM line_stations ls
            JOIN stations s ON ls.station_id = s.id
            WHERE ls.line_id = connection.line_id
              AND ls.stop_order BETWEEN connection.origin_order AND connection.dest_order
            ORDER BY ls.stop_order
        
        departures = QUERY:
            SELECT departure_time
            FROM departures
            WHERE line_id = connection.line_id
              AND direction = (connection.origin_order < connection.dest_order ? 0 : 1)
              AND is_active = TRUE
            ORDER BY departure_time
            LIMIT 3  -- next 3 departures
        
        fare = QUERY:
            SELECT fare_millesime
            FROM fares
            WHERE line_id = connection.line_id
              AND from_station_id = connection.origin_station_id
              AND to_station_id = connection.dest_station_id
        
        total_duration = walk_to_origin_time + wait_time + ride_duration
        
        ADD to results
    
    # Step 5: Sort and return
    RETURN results sorted by (total_duration, walk_distance, fare)
```

### Performance Optimizations
- Spatial index on stations.location (PostGIS GiST)
- Cache nearby stations results
- Pre-compute line connectivity graph
- Limit search radius progressively (1km → 5km → 10km)

---

## Example: Bizerte → Tunis

**User at**: Bizerte city center (37.274, 9.874)
**Destination**: Tunis Marine (36.8003, 10.1904)

**Result**:
```
Option 1: Bus Confort Bizerte → Tunis
  Walk to: Bizerte Bus Station (0.3 km, 4 min)
  Line: Confort Bizerte - Bab Saâdoun - Bizerte
  Departures: 06:30, 07:00, 07:30 (every 30 min)
  Duration: 2h 15min (ride) + 4min walk + 8min wait = ~2h 27min
  Fare: ~6.500 DT
  Stops (12 total):
    1. Bizerte Bus Station (origin)
    2. Menzel Bourguiba
    3. Tinja
    4. Ras Jebel
    5. ...
    12. Bab Saadoun (destination)
  Get off at: Bab Saadoun (louage interchange for other destinations)

Option 2: Louage Bizerte → Tunis
  Walk to: Bizerte Louage Station (0.5 km, 6 min)
  Line: Louage Bizerte-Tunis (white/red stripe)
  Departures: When full (~every 20 min)
  Duration: 1h 45min (ride) + 6min walk + 10min wait = ~2h 01min
  Fare: 6.500 DT
  Stops: Direct (no intermediate stops for red stripe)
  Get off at: Bab Saadoun

Option 3: Bus Standard Bizerte → Tunis
  ...
```

---

## Seed Data Requirements

For each line we need:
1. Origin station (with GPS)
2. Destination station (with GPS)
3. All intermediate stations (with GPS, in order)
4. Schedule (departure times or frequency)
5. Fare (or distance-based estimate)

---

## Implementation Priority

### Sprint 1: Core Data Model
- [ ] Create new schema with lines, stops, fares, departures
- [ ] Add BizerteConnect lines as seed data (~50 lines)
- [ ] Add louage routes from destination-tunis.fr

### Sprint 2: Routing Algorithm
- [ ] Implement nearby stations query
- [ ] Implement line-finding query
- [ ] Implement full "find my route" endpoint
- [ ] Test with Bizerte → Tunis route

### Sprint 3: Mobile Integration
- [ ] Map shows user location + nearby stations
- [ ] Tap destination → shows route options
- [ ] Each option shows: walk to station, line, stops, get off at
- [ ] "View stops" expands full stop list

---

*Model designed: 2026-09-18*
*Supports: Bus, louage, train, metro, taxi*
*Scale: 131+ lines from BizerteConnect alone*
