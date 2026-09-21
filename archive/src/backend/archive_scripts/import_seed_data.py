#!/usr/bin/env python3
"""
Import seed transport data into PostgreSQL/PostGIS database.

Usage:
    python scripts/import_seed_data.py --data-dir ./data --db-url postgresql://...

Reads JSON seed files and inserts into stations, lines, line_stations, and fares tables.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)

# SQL for creating tables (idempotent)
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stations (
    id VARCHAR(100) PRIMARY KEY,
    name_ar VARCHAR(200) NOT NULL,
    name_fr VARCHAR(200),
    name_en VARCHAR(200),
    location GEOGRAPHY(Point, 4326),
    governorate VARCHAR(100),
    station_type VARCHAR(50),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lines (
    id VARCHAR(100) PRIMARY KEY,
    line_number VARCHAR(50),
    line_name VARCHAR(200),
    operator VARCHAR(100),
    mode VARCHAR(20) NOT NULL,
    description TEXT,
    frequency TEXT,
    schedule_type VARCHAR(30),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS line_stations (
    id SERIAL PRIMARY KEY,
    line_id VARCHAR(100) REFERENCES lines(id),
    station_id VARCHAR(100) REFERENCES stations(id),
    stop_order INTEGER NOT NULL,
    is_origin BOOLEAN DEFAULT FALSE,
    is_destination BOOLEAN DEFAULT FALSE,
    distance_from_origin_km FLOAT,
    cumulative_duration_min INTEGER,
    UNIQUE(line_id, stop_order)
);

CREATE TABLE IF NOT EXISTS fares (
    id SERIAL PRIMARY KEY,
    line_id VARCHAR(100) REFERENCES lines(id),
    from_station_id VARCHAR(100) REFERENCES stations(id),
    to_station_id VARCHAR(100) REFERENCES stations(id),
    fare_millesime INTEGER NOT NULL,
    verified_date DATE,
    source VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS departures (
    id SERIAL PRIMARY KEY,
    line_id VARCHAR(100) REFERENCES lines(id),
    direction INTEGER DEFAULT 0,
    departure_time TIME NOT NULL,
    days_of_week INTEGER[] DEFAULT ARRAY[1,2,3,4,5,6,7],
    season VARCHAR(20) DEFAULT 'all',
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_line_stations_line_id ON line_stations(line_id);
CREATE INDEX IF NOT EXISTS idx_line_stations_station_id ON line_stations(station_id);
CREATE INDEX IF NOT EXISTS idx_fares_from_to ON fares(from_station_id, to_station_id);
CREATE INDEX IF NOT EXISTS idx_departures_line_id ON departures(line_id);
"""


def connect_db(db_url: str):
    """Establish database connection."""
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    conn.autocommit = False
    return conn


def create_schema(conn):
    """Create all tables if they don't exist."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()
    log.info("Schema created/verified successfully")


def insert_station(conn, station: dict) -> None:
    """Insert a station if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO stations (id, name_ar, name_fr, name_en, location, governorate, station_type, description)
            VALUES (%(id)s, %(name_ar)s, %(name_fr)s, %(name_en)s,
                    ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
                    %(governorate)s, %(station_type)s, %(description)s)
            ON CONFLICT (id) DO UPDATE SET
                name_ar = EXCLUDED.name_ar,
                name_fr = EXCLUDED.name_fr,
                name_en = EXCLUDED.name_en,
                location = COALESCE(EXCLUDED.location, stations.location),
                governorate = COALESCE(EXCLUDED.governorate, stations.governorate),
                station_type = COALESCE(EXCLUDED.station_type, stations.station_type)
        """, {
            'id': station['id'],
            'name_ar': station.get('name_ar', ''),
            'name_fr': station.get('name_fr'),
            'name_en': station.get('name_en'),
            'lat': station.get('lat'),
            'lon': station.get('lon'),
            'governorate': station.get('governorate'),
            'station_type': station.get('station_type', 'bus_stop'),
            'description': station.get('description'),
        })


def insert_line(conn, line: dict) -> None:
    """Insert a line if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lines (id, line_number, line_name, operator, mode, description, frequency, schedule_type)
            VALUES (%(id)s, %(line_number)s, %(line_name)s, %(operator)s, %(mode)s, %(description)s, %(frequency)s, %(schedule_type)s)
            ON CONFLICT (id) DO UPDATE SET
                line_number = EXCLUDED.line_number,
                line_name = EXCLUDED.line_name,
                operator = EXCLUDED.operator,
                mode = EXCLUDED.mode,
                description = EXCLUDED.description,
                frequency = EXCLUDED.frequency
        """, {
            'id': line['id'],
            'line_number': line.get('line_number'),
            'line_name': line.get('line_name'),
            'operator': line.get('operator'),
            'mode': line.get('mode', 'bus'),
            'description': line.get('description'),
            'frequency': line.get('frequency'),
            'schedule_type': line.get('schedule_type'),
        })


def insert_line_station(conn, line_id: str, station_id: str, order: int,
                        is_origin: bool = False, is_destination: bool = False) -> None:
    """Insert a line-station association."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO line_stations (line_id, station_id, stop_order, is_origin, is_destination)
            VALUES (%(line_id)s, %(station_id)s, %(order)s, %(is_origin)s, %(is_destination)s)
            ON CONFLICT (line_id, stop_order) DO UPDATE SET
                station_id = EXCLUDED.station_id,
                is_origin = EXCLUDED.is_origin,
                is_destination = EXCLUDED.is_destination
        """, {
            'line_id': line_id,
            'station_id': station_id,
            'order': order,
            'is_origin': is_origin,
            'is_destination': is_destination,
        })


def insert_fare(conn, line_id: str, from_id: str, to_id: str,
                fare_millesime: int, source: str = None) -> None:
    """Insert a fare record."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO fares (line_id, from_station_id, to_station_id, fare_millesime, source)
            VALUES (%(line_id)s, %(from_id)s, %(to_id)s, %(fare_millesime)s, %(source)s)
            ON CONFLICT DO NOTHING
        """, {
            'line_id': line_id,
            'from_id': from_id,
            'to_id': to_id,
            'fare_millesime': fare_millesime,
            'source': source,
        })


def import_seed_routes_destination_tunis(conn, data_path: Path) -> None:
    """Import destination-tunis.fr fare data."""
    if not data_path.exists():
        log.warning(f"File not found: {data_path}")
        return
    
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Insert stations
    for station in data.get('stations', []):
        insert_station(conn, station)
    
    # Insert routes as generic lines
    for route in data.get('routes', []):
        line_id = f"louage_{route['from']}_{route['to']}"
        
        # Create a generic line for each route
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO lines (id, line_number, line_name, mode, description, frequency)
                VALUES (%(id)s, %(number)s, %(name)s, 'louage', %(desc)s, %(freq)s)
                ON CONFLICT (id) DO NOTHING
            """, {
                'id': line_id,
                'number': route.get('mode', 'louage_red'),
                'name': f"Louage {route['from']} → {route['to']}",
                'desc': f"Louage route verified {route.get('verified', 'unknown')}",
                'freq': route.get('frequency_description', 'When full'),
            })
        
        # Insert stations if not exists (basic)
        for station_id in [route['from'], route['to']]:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM stations WHERE id = %s", (station_id,))
                if not cur.fetchone():
                    insert_station(conn, {
                        'id': station_id,
                        'name_ar': station_id.replace('_', ' ').title(),
                        'name_fr': station_id.replace('_', ' ').title(),
                        'name_en': station_id.replace('_', ' ').title(),
                        'station_type': 'louage_station',
                    })
        
        # Link stations to line
        insert_line_station(conn, line_id, route['from'], 1, is_origin=True)
        insert_line_station(conn, line_id, route['to'], 2, is_destination=True)
        
        # Insert fare
        fare_millesime = int(route.get('fare', 0))
        insert_fare(conn, line_id, route['from'], route['to'], fare_millesime, 'destination-tunis.fr')
    
    conn.commit()
    log.info(f"Imported {len(data.get('routes', []))} routes from destination-tunis.fr")


def import_seed_lines_bizerte(conn, data_path: Path) -> None:
    """Import BizerteConnect line data."""
    if not data_path.exists():
        log.warning(f"File not found: {data_path}")
        return
    
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Insert all stations first
    for station in data.get('stations', []):
        insert_station(conn, station)
    
    # Insert lines and their stops
    for line in data.get('lines', []):
        insert_line(conn, line)
        
        # Insert stops
        stations = line.get('stations', [])
        for i, station_id in enumerate(stations):
            insert_line_station(
                conn, line['id'], station_id, i + 1,
                is_origin=(i == 0),
                is_destination=(i == len(stations) - 1)
            )
        
        # Insert fares if available
        for fare in line.get('fares', []):
            fare_millesime = int(fare.get('fare_dt', 0))
            insert_fare(conn, line['id'], fare['from'], fare['to'], fare_millesime, 'bizerteconnect.com')
    
    conn.commit()
    log.info(f"Imported {len(data.get('lines', []))} lines from BizerteConnect")


def main():
    parser = argparse.ArgumentParser(description="Import seed transport data")
    parser.add_argument("--data-dir", default="./data", help="Path to data directory")
    parser.add_argument("--db-url", required=True, help="PostgreSQL connection URL")
    parser.add_argument("--create-schema", action="store_true", help="Create tables if not exist")
    args = parser.parse_args()
    
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        log.error(f"Data directory not found: {data_dir}")
        sys.exit(1)
    
    try:
        conn = connect_db(args.db_url)
        log.info("Connected to database")
        
        if args.create_schema:
            create_schema(conn)
        
        # Import destination-tunis.fr fares
        import_seed_routes_destination_tunis(conn, data_dir / "seed_routes_destination_tunis.json")
        
        # Import BizerteConnect lines
        import_seed_lines_bizerte(conn, data_dir / "seed_lines_bizerte.json")
        
        log.info("Seed data import completed successfully")
        
    except psycopg2.Error as e:
        log.error(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Error: {e}")
        raise
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    main()
