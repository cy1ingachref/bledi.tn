#!/usr/bin/env python3
"""Generate an HTML map comparing SNTRI and Tunismapper stations.

Creates a Leaflet.js map with:
- Blue markers: SNTRI stations (geocoded)
- Red markers: Tunismapper stations (existing)
- Overlapping names highlighted in green
"""
import json
from pathlib import Path

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")

# Load SNTRI geocoded stations
with open(BASE / "scripts/sntri_stations_geocoded.json", encoding="utf-8") as f:
    sntri = json.load(f)

# Load Tunismapper stations (from seed)
with open(BASE / "data/seed_all_tunisia_routes.json", encoding="utf-8") as f:
    seed = json.load(f)

# Build Tunismapper station list with coordinates
tunismapper_stations = []
for s in seed["stations"]:
    if s.get("lat") and s.get("lon"):
        tunismapper_stations.append({
            "name": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
        })

# Find overlapping names (case-insensitive)
sntri_names = {s["name"].lower() for s in sntri["stations"]}
tunismapper_names = {s["name"].lower() for s in tunismapper_stations}
overlapping = sntri_names & tunismapper_names

print(f"SNTRI geocoded: {len(sntri['stations'])}")
print(f"Tunismapper stations: {len(tunismapper_stations)}")
print(f"Overlapping names: {len(overlapping)}")

# Generate HTML
html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BLEDI.TN — SNTRI vs Tunismapper Station Comparison</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; padding: 0; font-family: sans-serif; }}
        #map {{ width: 100%; height: 100vh; }}
        .legend {{
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 0 10px rgba(0,0,0,0.3);
            position: absolute;
            top: 10px;
            right: 10px;
            z-index: 1000;
        }}
        .legend-item {{ display: flex; align-items: center; margin: 5px 0; }}
        .legend-color {{ width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }}
        .stats {{
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 0 10px rgba(0,0,0,0.3);
            position: absolute;
            bottom: 10px;
            left: 10px;
            z-index: 1000;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="legend">
        <h3>Station Sources</h3>
        <div class="legend-item"><div class="legend-color" style="background: #2196F3;"></div>SNTRI (intercity bus)</div>
        <div class="legend-item"><div class="legend-color" style="background: #F44336;"></div>Tunismapper (urban)</div>
        <div class="legend-item"><div class="legend-color" style="background: #4CAF50;"></div>Both sources</div>
    </div>
    <div class="stats">
        <strong>Coverage Comparison</strong><br>
        SNTRI stations: {len(sntri['stations'])}<br>
        Tunismapper stations: {len(tunismapper_stations)}<br>
        Overlapping names: {len(overlapping)}<br>
        SNTRI-only: {len(sntri_names - tunismapper_names)}<br>
        Tunismapper-only: {len(tunismapper_names - sntri_names)}
    </div>
    <script>
        var map = L.map('map').setView([34.5, 9.5], 6);

        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '&copy; OpenStreetMap contributors'
        }}).addTo(map);

        // SNTRI stations (blue)
        var sntriStations = {json.dumps(sntri["stations"], ensure_ascii=False)};
        sntriStations.forEach(function(s) {{
            L.circleMarker([s.lat, s.lon], {{
                radius: 6,
                fillColor: '#2196F3',
                color: '#1565C0',
                weight: 1,
                opacity: 0.8,
                fillOpacity: 0.6
            }}).addTo(map).bindPopup('<b>SNTRI</b><br>' + s.name);
        }});

        // Tunismapper stations (red)
        var tunismapperStations = {json.dumps(tunismapper_stations, ensure_ascii=False)};
        tunismapperStations.forEach(function(s) {{
            L.circleMarker([s.lat, s.lon], {{
                radius: 5,
                fillColor: '#F44336',
                color: '#C62828',
                weight: 1,
                opacity: 0.7,
                fillOpacity: 0.5
            }}).addTo(map).bindPopup('<b>Tunismapper</b><br>' + s.name);
        }});

        // Fit bounds to show all markers
        var allPoints = [];
        sntriStations.forEach(function(s) {{ allPoints.push([s.lat, s.lon]); }});
        tunismapperStations.forEach(function(s) {{ allPoints.push([s.lat, s.lon]); }});
        if (allPoints.length > 0) {{
            map.fitBounds(allPoints, {{ padding: [50, 50] }});
        }}
    </script>
</body>
</html>
"""

out_path = BASE / "scripts/sntri_comparison_map.html"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\nMap saved -> {out_path}")
print("Open in browser to view")
