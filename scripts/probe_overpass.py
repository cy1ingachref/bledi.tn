#!/usr/bin/env python3
"""Try multiple Overpass queries to find any bus-related data in Tunisia."""
import json, urllib.request, urllib.parse, time

def query_overpass(ql_code, label):
    url = "https://overpass.kumi.systems/api/interpreter?data=" + urllib.parse.quote(ql_code)
    req = urllib.request.Request(url, headers={"User-Agent": "bledi.tn/1.0"})
    print(f"\n--- {label} ---")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
        elapsed = time.time() - t0
        elements = data.get("elements", [])
        # count element
        count_el = next((e for e in elements if e.get("type") == "count"), None)
        if count_el and "tags" in count_el:
            counts = count_el["tags"]
            print(f"  [{elapsed:.0f}s] counts: {counts}")
            return counts
        types = {}
        for e in elements:
            t = e["type"]
            types[t] = types.get(t, 0) + 1
        print(f"  [{elapsed:.0f}s] elements: {types}")
        return types
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

# Q1: Any public_transport in Tunisia (broader than just bus)
query_overpass(
    '[out:json][timeout:300];area["name"="Tunisia"]["admin_level"="2"]->.a;(node["public_transport"](area.a);way["public_transport"](area.a);relation["public_transport"](area.a););out count;',
    "All public_transport tags in Tunisia"
)

# Q2: highway=bus_stop
query_overpass(
    '[out:json][timeout:300];area["name"="Tunisia"]["admin_level"="2"]->.a;(node["highway"="bus_stop"](area.a);way["highway"="bus_stop"](area.a););out count;',
    "highway=bus_stop in Tunisia"
)

# Q3: route=bus without area (world, then filter) — just count
query_overpass(
    '[out:json][timeout:300];relation["route"="bus"](37.0,8.5,38.0,11.5);out count;',
    "route=bus in Tunisia bbox (37-8.5 to 38-11.5)"
)

# Q4: amenity=bus_station
query_overpass(
    '[out:json][timeout:300];area["name"="Tunisia"]["admin_level"="2"]->.a;node["amenity"="bus_station"](area.a);out count;',
    "amenity=bus_station in Tunisia"
)

# Q5: network tags that exist
query_overpass(
    '[out:json][timeout:300];area["name"="Tunisia"]["admin_level"="2"]->.a;relation["route"~"bus| trolleybus|minibus"](area.a);out count;',
    "route=bus OR trolleybus OR minibus in Tunisia"
)

print("\n=== DONE ===")
