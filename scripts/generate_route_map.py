#!/usr/bin/env python3
"""Generate an HTML map showing a computed route using Leaflet.js.

Takes routing engine output and renders it on an OpenStreetMap tile layer.
"""
import json
from pathlib import Path

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")


def generate_route_map(route_data, output_path):
    """Generate HTML map from route data."""
    legs = route_data["legs"]

    # Build JavaScript arrays for each leg type
    walk_coords = []
    transit_coords = []

    for leg in legs:
        if leg["type"] == "walk":
            walk_coords.append({
                "from": leg["from"],
                "to": leg["to"],
                "duration": leg["duration"],
                "distance": leg["distance"],
            })
        elif leg["type"] == "transit":
            transit_coords.append({
                "from": [0, 0],  # placeholder
                "to": [0, 0],
                "line": leg.get("line", "?"),
                "mode": leg.get("mode", "?"),
                "from_station": leg.get("from_station", "?"),
                "to_station": leg.get("to_station", "?"),
                "duration": leg["duration"],
                "distance": leg["distance"],
            })

    # Get all coordinates for bounds
    all_coords = []
    for leg in legs:
        if leg["type"] == "walk":
            all_coords.append(leg["from"])
            all_coords.append(leg["to"])

    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BLEDI.TN — Route Map</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; padding: 0; font-family: sans-serif; }}
        #map {{ width: 100%; height: 80vh; }}
        .info-panel {{
            padding: 15px;
            background: #f5f5f5;
            border-top: 2px solid #333;
        }}
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
        .legend-color {{ width: 20px; height: 4px; margin-right: 8px; }}
        .stats {{
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 0 10px rgba(0,0,0,0.3);
            position: absolute;
            bottom: 10px;
            left: 10px;
            z-index: 1000;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="info-panel">
        <h2>Route: {route_data.get('start_station', '?')} → {route_data.get('end_station', '?')}</h2>
        <div class="legend">
            <h3>Legs</h3>
            <div class="legend-item"><div class="legend-color" style="background: #8E8E93;"></div>Walk</div>
            <div class="legend-item"><div class="legend-color" style="background: #FFCF06;"></div>Metro</div>
            <div class="legend-item"><div class="legend-color" style="background: #407E15;"></div>Bus</div>
            <div class="legend-item"><div class="legend-color" style="background: #FF9500;"></div>Train</div>
        </div>
        <div class="stats">
            <strong>Total:</strong> {route_data['total_duration']} min |
            {route_data['total_distance']} km |
            {route_data['transfers']} transfer(s)
        </div>
    </div>
    <script>
        var map = L.map('map').setView([34.5, 9.5], 10);

        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '&copy; OpenStreetMap contributors'
        }}).addTo(map);

        // Draw legs
        var legs = {json.dumps(legs, ensure_ascii=False)};
        var allCoords = [];

        legs.forEach(function(leg) {{
            if (leg.type === 'walk') {{
                var latlngs = [leg.from, leg.to];
                L.polyline(latlngs, {{
                    color: '#8E8E93',
                    weight: 3,
                    opacity: 0.7,
                    dashArray: '5, 10'
                }}).addTo(map);
                allCoords = allCoords.concat(latlngs);
            }} else if (leg.type === 'transit') {{
                var color = '#FFCF06';
                if (leg.mode === 'bus') color = '#407E15';
                else if (leg.mode === 'train') color = '#FF9500';
                else if (leg.mode === 'metro') color = '#FFCF06';
                var latlngs = [leg.from, leg.to];
                L.polyline(latlngs, {{
                    color: color,
                    weight: 4,
                    opacity: 0.8
                }}).addTo(map);
                allCoords = allCoords.concat(latlngs);
            }}
        }});

        // Fit bounds
        if (allCoords.length > 0) {{
            map.fitBounds(allCoords, {{ padding: [50, 50] }});
        }}
    </script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Route map saved -> {output_path}")


if __name__ == "__main__":
    # Example usage
    route = {
        "legs": [
            {"type": "walk", "from": [36.8151533, 10.0568158], "to": [36.81533, 10.05678], "distance": 0.02, "duration": 0.24},
            {"type": "transit", "from": [36.81533, 10.05678], "to": [36.80986, 10.16219], "line": "4", "mode": "metro", "from_station": "KHAIREDDINE", "to_station": "BAB SAADOUN", "distance": 12.5, "duration": 30},
            {"type": "transit", "from": [36.80986, 10.16219], "to": [36.8585478, 10.1682756], "line": "460", "mode": "bus", "from_station": "BAB SAADOUN", "to_station": "Cite Ennasr 1", "distance": 7.0, "duration": 17},
        ],
        "total_duration": 47.0,
        "total_distance": 19.5,
        "transfers": 2,
        "start_station": "KHAIREDDINE",
        "end_station": "Cite Ennasr 1"
    }
    generate_route_map(route, BASE / "scripts/route_map.html")
