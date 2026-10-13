"""Read-only queries over the network: stops, lines, cities, track and search."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from bledi_transit.application.errors import AppError
from bledi_transit.application.network import Network
from bledi_transit.application.ports import MapLayers
from bledi_transit.domain.cities import CITY_SEATS, nearest_city
from bledi_transit.domain.geo import haversine_m, simplify as simplify_path
from bledi_transit.domain.modes import USER_MODES, canonical_mode, mode_label_fr
from bledi_transit.domain.stations import UNCLASSIFIED, primary_station_mode, station_modes
from bledi_transit.domain.tunables import GEOMETRY_REQUIRED_M

log = logging.getLogger("bledi")

Json = dict[str, Any]


def _by_count(counts: dict[str, int]) -> dict[str, int]:
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


class Catalog:
    def __init__(self, network: Network, layers: MapLayers) -> None:
        self.network = network
        self.layers = layers

    def stations(self) -> Json:
        """Every stop as a GeoJSON feature, louage hubs appended after the transit stops."""
        features: list[Json] = []
        for s in self.network.stations:
            lat, lon = s.get("lat"), s.get("lon")
            if not lat or not lon:
                log.warning("Station %s has no/zero coordinates: %s", s.get("id"), s.get("name"))
                continue
            features.append(
                {
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "id": s.get("id"),
                        "name": s.get("name"),
                        "name_en": s.get("name_en"),
                        "mode": primary_station_mode(s),
                        "modes": station_modes(s),
                        "mode_raw": s.get("mode"),
                        "operator": s.get("operator"),
                        "route_type": s.get("route_type"),
                        "license_status": s.get("license_status"),
                        "city": nearest_city(lat, lon),
                        "source": s.get("source"),
                        "lines": s.get("lines_served", []),
                    },
                }
            )

        for s in self.network.louage_stations:
            loc = s.get("location") or {}
            lat, lon = loc.get("lat"), loc.get("lon")
            if not lat or not lon:
                continue
            routes = self.network.louage_routes_by_stop.get(s.get("id", ""), [])
            raw_modes = sorted({r.get("mode") for r in routes if r.get("mode")})
            canon = sorted({canonical_mode(m) for m in raw_modes}) or ["louaj"]
            features.append(
                {
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        # Prefixed so hub ids never collide with transit stop ids.
                        "id": f"louage_{s.get('id')}",
                        "name": s.get("name_fr") or s.get("name_en") or s.get("id"),
                        "name_en": s.get("name_en"),
                        "mode": canon[0],
                        "modes": canon,
                        "mode_raw": raw_modes[0] if len(raw_modes) == 1 else "louage",
                        "operator": "Louage",
                        "route_type": s.get("type"),
                        "license_status": "unknown-third-party",
                        "city": s.get("governorate") or nearest_city(lat, lon),
                        "source": "louage",
                        "fare_display": s.get("fare_display"),
                        "lines": [
                            {
                                "route_short_name": r.get("mode"),
                                "route_color": None,
                                "direction": f"{r.get('from')} → {r.get('to')}",
                                "route_id": r.get("from"),
                            }
                            for r in routes
                        ],
                    },
                }
            )

        by_mode: dict[str, int] = defaultdict(int)
        for f in features:
            for m in f["properties"].get("modes") or [f["properties"].get("mode")]:
                if m:
                    by_mode[m] += 1
        return {
            "features": features,
            "metadata": {
                "count": len(features),
                "total": len(self.network.stations),
                "by_mode": _by_count(by_mode),
            },
        }

    def track(self, modes: str | None, bbox: str | None, simplify: float) -> Json | None:
        """Physical track per stop pair, or None when route geometry was never built.

        A pair with no traced track is reported with `has_geometry: false` and
        its straight length instead of being drawn as a straight line across
        the country. Geometry is [[lat, lon]], the order the routing legs use.
        """
        wanted: set[str] | None = None
        if modes:
            wanted = {canonical_mode(m.strip().lower()) for m in modes.split(",") if m.strip()} or None

        box: tuple[float, float, float, float] | None = None
        if bbox:
            parts = bbox.split(",")
            if len(parts) != 4:
                raise AppError("invalid_request", "bbox must be min_lon,min_lat,max_lon,max_lat")
            try:
                box = (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
            except ValueError as exc:
                raise AppError("invalid_request", "bbox values must be numbers") from exc

        if self.network.segments is None:
            return None

        def in_box(la: float, lo: float) -> bool:
            return box is None or (box[1] <= la <= box[3] and box[0] <= lo <= box[2])

        out: list[Json] = []
        by_mode: dict[str, int] = defaultdict(int)
        missing = 0
        for key, seg in self.network.segments.items():
            seg_mode = canonical_mode(seg.get("mode"))
            if wanted is not None and seg_mode not in wanted:
                continue
            pts = seg.get("geometry") or []
            if simplify > 0 and len(pts) > 2:
                pts = simplify_path(pts, simplify)
            if len(pts) < 2:
                a, b = key.split("|", 1) if "|" in key else (key, "")
                pa = self.network.station_by_id.get(a) or {}
                pb = self.network.station_by_id.get(b) or {}
                if not (pa.get("lat") and pb.get("lat")):
                    continue
                # Bbox still applies, via the endpoints, or a city view would
                # drag in every gap in the network.
                if not (in_box(pa["lat"], pa["lon"]) or in_box(pb["lat"], pb["lon"])):
                    continue
                missing += 1
                out.append(
                    {
                        "id": key,
                        "mode": seg_mode,
                        "source": seg.get("source"),
                        "has_geometry": False,
                        "geometry": [],
                        "from_stop_id": a,
                        "to_stop_id": b,
                        "straight_m": round(haversine_m(pa["lat"], pa["lon"], pb["lat"], pb["lon"])),
                    }
                )
                continue
            if not any(in_box(la, lo) for la, lo in pts):
                continue
            by_mode[seg_mode] += 1
            out.append(
                {"id": key, "mode": seg_mode, "source": seg.get("source"), "has_geometry": True, "geometry": pts}
            )

        return {
            "segments": out,
            "metadata": {
                "count": len(out),
                "by_mode": _by_count(by_mode),
                "missing_geometry": missing,
                "available_modes": sorted(by_mode),
            },
        }

    def map_layer(self, name: str, kind: str) -> Json:
        """LineString features of a prebuilt overlay, converted to [lat, lon]."""
        data = self.layers.map_layer(name)
        feats: list[Json] = []
        for f in data.get("features", []):
            geom = f.get("geometry") or {}
            if geom.get("type") != "LineString":
                continue
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            feats.append(
                {
                    "kind": kind,
                    "properties": f.get("properties") or {},
                    "geometry": [[c[1], c[0]] for c in coords],
                }
            )
        return {"features": feats, "metadata": {**(data.get("metadata") or {}), "returned": len(feats)}}

    def louage_links(self) -> Json:
        return self.layers.louage_links()

    def cities(self) -> Json:
        counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        centres: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])

        def bucket(city: str, mode: str | None, lat: float, lon: float) -> None:
            counts[city][mode or "unknown"] += 1
            acc = centres[city]
            acc[0] += lat
            acc[1] += lon
            acc[2] += 1

        for s in self.network.stations:
            lat, lon = s.get("lat"), s.get("lon")
            if not lat or not lon:
                continue
            bucket(nearest_city(lat, lon), s.get("mode"), lat, lon)
        for s in self.network.louage_stations:
            loc = s.get("location") or {}
            lat, lon = loc.get("lat"), loc.get("lon")
            if not lat or not lon:
                continue
            bucket(s.get("governorate") or nearest_city(lat, lon), "louage", lat, lon)

        cities = [
            {
                "name": name,
                "lat": acc[0] / acc[2],
                "lon": acc[1] / acc[2],
                "station_count": acc[2],
                "by_mode": dict(counts[name]),
            }
            for name, acc in centres.items()
            if acc[2] > 0
        ]
        cities.sort(key=lambda c: -c["station_count"])
        return {"cities": cities, "count": len(cities)}

    def near(self, lat: float, lon: float, limit: int) -> Json:
        candidates = [s for s in self.network.stations if s.get("lat") and s.get("lon")]
        ranked = sorted(candidates, key=lambda s: haversine_m(lat, lon, s["lat"], s["lon"]))
        return {
            "near": [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "lat": s["lat"],
                    "lon": s["lon"],
                    "dist_m": round(haversine_m(lat, lon, s["lat"], s["lon"])),
                    "lines": s.get("lines_served", []),
                }
                for s in ranked[:limit]
            ],
            "query": {"lat": lat, "lon": lon},
        }

    def station(self, station_id: str) -> Json:
        """Every line calling at a stop, with where on the line the stop sits."""
        net = self.network
        st = net.station_by_id.get(station_id)
        if st is None:
            raise AppError("not_found", f"Station '{station_id}' not found")

        infos: list[Json] = []
        for lid in dict.fromkeys(net.lines_by_station.get(station_id, [])):
            ln = net.line_by_id.get(lid)
            if ln is None:
                continue
            stops = ln.get("stations") or ln.get("stops") or []
            mode = canonical_mode(ln.get("mode") or "bus")
            # A loop service lists a stop twice; the first one is where a rider boards.
            idx = stops.index(station_id) if isinstance(stops, list) and station_id in stops else None
            role = "through"
            if idx == 0:
                role = "origin"
            elif idx is not None and idx == len(stops) - 1:
                role = "terminus"
            direction = None
            termini = ln.get("terminus") or ln.get("ends")
            if isinstance(termini, list) and len(termini) >= 2:
                direction = f"{termini[0]} - {termini[1]}"
            else:
                tail = stops[-1] if stops else None
                tail_st = net.station_by_id.get(tail) if isinstance(tail, str) else None
                if tail_st is not None and tail_st.get("name"):
                    head_st = net.station_by_id.get(stops[0]) if stops else None
                    direction = f"{(head_st or {}).get('name') or '?'} - {tail_st['name']}"
            infos.append(
                {
                    "line_id": lid,
                    "number": ln.get("number") or ln.get("route_id") or None,
                    "name": ln.get("name") or None,
                    "mode": mode,
                    "mode_label": mode_label_fr(mode),
                    "operator": ln.get("operator") or None,
                    "color": ln.get("color") or ln.get("route_color") or None,
                    "direction": direction,
                    "stops_count": len(stops),
                    "stop_index": idx,
                    "role": role,
                }
            )

        order = {m: i for i, m in enumerate(USER_MODES)}
        infos.sort(key=lambda li: (order.get(li["mode"], 99), (li["number"] or "").zfill(4), li["name"] or ""))

        # The declared mode is the baseline and line modes are added: only
        # 1 562 of 7 452 stops are on a line's stop array, and a bus stop that
        # is on none must not read "Non classé" while its map dot says bus.
        declared = station_modes(st)
        merged = [m for m in USER_MODES if m in declared or any(li["mode"] == m for li in infos)]
        if UNCLASSIFIED in declared and not merged:
            merged.append(UNCLASSIFIED)

        return {
            "id": st.get("id") or station_id,
            "name": st.get("name"),
            "lat": st.get("lat"),
            "lon": st.get("lon"),
            "city": st.get("city") or nearest_city(st["lat"], st["lon"]) if st.get("lat") and st.get("lon") else None,
            "modes": merged,
            "lines": infos,
            "count": len(infos),
            "lines_known": len(infos) > 0,
        }

    def lines(self) -> Json:
        return {
            "lines": [
                {
                    "id": ln.get("id", ""),
                    "number": ln.get("number"),
                    "short_name": ln.get("short_name"),
                    "long_name": ln.get("long_name"),
                    "mode": ln.get("mode", "bus"),
                    "color": ln.get("color"),
                    "route_id": ln.get("route_id"),
                    "stops_count": len(ln.get("stations") or ln.get("stops") or []),
                }
                for ln in self.network.lines
            ],
            "count": len(self.network.lines),
        }

    def line(self, identifier: str) -> Json:
        """A line by id, else the first line with that number (numbers repeat)."""
        line = self.network.line_by_id.get(identifier)
        if line is None:
            by_num = self.network.lines_by_number.get(identifier)
            if not by_num:
                raise AppError("not_found", f"Line '{identifier}' not found")
            line = by_num[0]
            log.info(
                "Line lookup by number '%s' returned %d matches; using first: %s",
                identifier, len(by_num), line.get("id"),
            )
        return self._line_detail(line, self._stops(line))

    def _stops(self, line: Json) -> list[Json]:
        listed = line.get("stations") or line.get("stops") or []
        if listed and isinstance(listed[0], (int, str)):
            stops = []
            for sid in listed:
                st = self.network.station_by_id.get(sid)
                if st is None:
                    log.warning("Stop id %s in line %s not found in station index", sid, line.get("id"))
                    continue
                stops.append(
                    {
                        "stop_id": st.get("id"),
                        "name": st.get("name"),
                        "lat": st.get("lat"),
                        "lon": st.get("lon"),
                        "lines": st.get("lines_served"),
                    }
                )
            return stops
        if listed and isinstance(listed[0], dict):
            return [
                {
                    "name": s.get("name", s.get("station", "")),
                    "lat": s.get("lat", s.get("latitude")),
                    "lon": s.get("lon", s.get("longitude")),
                    "order": s.get("order"),
                    "schedule": s.get("schedule"),
                }
                for s in listed
            ]
        return [
            {
                "name": s.get("name"),
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "order": s.get("order"),
                "schedule": s.get("schedule"),
                "stop_id": s.get("stop_id"),
            }
            for s in line.get("stops", [])
        ]

    def _line_detail(self, line: Json, stops: list[Json]) -> Json:
        """The line with each stop pair's track, never stitched across a missing pair.

        A pair without track lands in `gaps` with its straight length, so the
        client draws a dashed placeholder instead of a line crossing the country.
        """
        mode = canonical_mode(line.get("mode") or "bus")
        segs: list[Json] = []
        gaps: list[Json] = []
        stitched: list[list[float]] = []
        complete = True
        for a, b in zip(stops, stops[1:]):
            if a.get("lat") is None or a.get("lon") is None or b.get("lat") is None or b.get("lon") is None:
                continue
            pts = self.network.segment_geometry(a.get("stop_id"), b.get("stop_id"))
            gap_m = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            pair = {
                "from_stop_id": a.get("stop_id"),
                "to_stop_id": b.get("stop_id"),
                "from_name": a.get("name"),
                "to_name": b.get("name"),
            }
            segs.append(
                {
                    **pair,
                    "has_geometry": bool(pts),
                    "needs_geometry": (not pts) and gap_m >= GEOMETRY_REQUIRED_M,
                    "gap_m": round(gap_m),
                    "geometry": pts,
                }
            )
            if pts:
                stitched.extend(pts if not stitched else pts[1:])
            elif gap_m >= GEOMETRY_REQUIRED_M:
                complete = False
                gaps.append({**pair, "gap_m": round(gap_m), "reason": "no_cached_geometry"})

        geometry = None
        if complete and len(stitched) >= 2:
            geometry = {"type": "LineString", "coordinates": [[p[1], p[0]] for p in stitched]}
        return {
            "line": line,
            "stops": stops,
            "count": len(stops),
            "mode": mode,
            "mode_label": mode_label_fr(mode),
            "geometry": geometry,
            "geometry_complete": complete,
            "geometry_segments": segs,
            "gaps": gaps,
        }

    def search(self, q: str, limit: int, near_lat: float | None, near_lon: float | None) -> Json:
        """Stops, louage hubs and governorate seats whose name contains `q`.

        Exact match, then prefix, then substring, with distance to the
        reference point as the tiebreak so two stops named "20 Mars" resolve
        to the one near the rider.
        """
        needle = q.strip().lower()
        if len(needle) < 2:
            return {"results": [], "query": q, "count": 0}

        def score(name: str) -> int:
            n = name.strip().lower()
            if n == needle:
                return 0
            return 1 if n.startswith(needle) else 2

        results: list[Json] = []
        seen_ids: set[str] = set()
        for s in self.network.stations:
            lat, lon = s.get("lat"), s.get("lon")
            name = s.get("name") or ""
            sid = s.get("id") or ""
            if not lat or not lon or needle not in name.lower() or sid in seen_ids:
                continue
            seen_ids.add(sid)
            city = nearest_city(lat, lon)
            results.append(
                {
                    "kind": "stop",
                    "id": sid,
                    "name": name.strip(),
                    "lat": lat,
                    "lon": lon,
                    "modes": station_modes(s),
                    "city": city,
                    "score": score(name),
                    "display_name": f"{name.strip()} · {city}",
                }
            )
        for s in self.network.louage_stations:
            loc = s.get("location") or {}
            lat, lon = loc.get("lat"), loc.get("lon")
            name = s.get("name_fr") or s.get("name_en") or s.get("id") or ""
            sid = f"louage_{s.get('id')}"
            if not lat or not lon or needle not in name.lower() or sid in seen_ids:
                continue
            seen_ids.add(sid)
            results.append(
                {
                    "kind": "stop",
                    "id": sid,
                    "name": name.strip(),
                    "lat": lat,
                    "lon": lon,
                    "modes": ["louaj"],
                    "city": s.get("governorate") or nearest_city(lat, lon),
                    "score": score(name),
                    "display_name": f"{name.strip()} · Taxi / Louage",
                }
            )
        for name, slat, slon in CITY_SEATS:
            if needle not in name.lower():
                continue
            results.append(
                {
                    "kind": "city",
                    "id": f"city_{name}",
                    "name": name,
                    "lat": slat,
                    "lon": slon,
                    "modes": [],
                    "city": name,
                    "score": score(name),
                    "display_name": name,
                }
            )

        def dist(r: Json) -> float:
            if near_lat is None or near_lon is None:
                return 0.0
            return haversine_m(near_lat, near_lon, r["lat"], r["lon"])

        results.sort(key=lambda r: (r["score"], dist(r), r["name"]))
        return {
            "results": [{k: v for k, v in r.items() if k != "score"} for r in results[:limit]],
            "query": q,
            "count": len(results),
        }
