"""Shared helpers for the OSM stop-audit tools.

Three audit scripts were grown in parallel and each re-implemented the same
haversine / label / name-normalisation helpers. They live here now so the
audits stay comparable to each other: if two scripts disagree about what counts
as a match, it is a bug in one of them, not a difference in the definitions.

Read-only with respect to the seed and the backend.
"""

from __future__ import annotations

import json
import math
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

# Tried in order; the public instances rate-limit aggressively (HTTP 504).
ENDPOINTS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)

USER_AGENT = "bledi-tn-audit/1.0"
TUNISIA_BBOX = "32.4,7.0,37.7,11.9"  # S,W,N,E

# Stop-like tags. `public_transport=*` is broad on purpose: Tunisian SNCFT halts
# and TGM platforms are tagged `railway=stop` / `public_transport=stop_position`,
# which are NOT bus-exclusive. A narrower list reports correct rail stops as
# missing.
QUERY = """
[out:json][timeout:{timeout}];
(
  node["public_transport"]({bbox});
  node["highway"="bus_stop"]({bbox});
  node["railway"]({bbox});
);
out body;
"""


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return 2 * 6371000.0 * math.asin(
        math.sqrt(
            math.sin((math.radians(lat2) - math.radians(lat1)) / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(math.radians(lon2 - lon1) / 2) ** 2
        )
    )


def label(tags: dict) -> str:
    """Human name for an OSM node, preferring a Latin spelling."""
    for key in ("name:latin", "int_name", "name:fr", "name:en", "name"):
        val = (tags.get(key) or "").strip()
        if val:
            return val
    return "(unnamed)"


def norm(s: str) -> str:
    """Accent/case/punctuation-insensitive key, for name comparison."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return " ".join("".join(c if c.isalnum() or c.isspace() else " " for c in s).split())


def names_match(ours: str, tags: dict) -> bool:
    """True when any of the OSM name variants equals ours after normalisation."""
    target = norm(ours)
    if not target:
        return False
    return target in {norm(label(tags)), norm(tags.get("name", ""))}


def classify(tags: dict) -> str:
    """Coarse mode of an OSM stop node: rail | bus | other.

    `railway=stop` counts as rail — see the module docstring.
    """
    if tags.get("railway") in {"station", "halt", "tram_stop", "stop"}:
        return "rail"
    if tags.get("public_transport") in {"platform", "stop_position", "station"}:
        return "rail" if (tags.get("railway") or tags.get("train") == "yes") else "bus"
    if tags.get("highway") == "bus_stop":
        return "bus"
    return "other"


def is_bus_stop(tags: dict) -> bool:
    return classify(tags) == "bus"


def fetch_osm_nodes(bbox: str = TUNISIA_BBOX, timeout: int = 600) -> list[dict]:
    """Overpass query, retried across endpoints. Returns transport nodes."""
    data = urllib.parse.urlencode(
        {"data": QUERY.format(bbox=bbox, timeout=timeout)}
    ).encode()
    last = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout + 30) as r:
                return [
                    e
                    for e in json.load(r)["elements"]
                    if e.get("type") == "node" and e.get("lat") and e.get("lon")
                ]
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(10)
    raise SystemExit(f"Overpass unavailable: {last}")


def load_osm_cache(cache: str) -> list[dict]:
    """Cached OSM nodes, fetching them on first use.

    The audit is otherwise re-run against the public Overpass instances on every
    invocation, which rate-limits after a handful of calls.
    """
    path = Path(cache)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    nodes = fetch_osm_nodes()
    path.write_text(json.dumps(nodes, ensure_ascii=False), encoding="utf-8")
    print(f"  cached {len(nodes)} OSM nodes to {cache}")
    return nodes


def load_seed(seed: str) -> list[dict]:
    """Seed stations that have coordinates."""
    data = json.loads(Path(seed).read_text(encoding="utf-8"))
    return [s for s in data["stations"] if s.get("lat") and s.get("lon")]


def bucket_index(
    nodes: list[dict], cell_deg: float
) -> dict[tuple[int, int], list[dict]]:
    """Spatial index so nearest-neighbour stays near-linear."""
    out: dict[tuple[int, int], list[dict]] = {}
    for e in nodes:
        out.setdefault((int(e["lat"] // cell_deg), int(e["lon"] // cell_deg)), []).append(e)
    return out


def nearest(
    point: tuple[float, float], index: dict, cell: float
) -> tuple[dict | None, float | None]:
    """Closest OSM node to (lat, lon) and its distance in metres."""
    lat, lon = point
    best, best_d = None, None
    ky, kx = int(lat // cell), int(lon // cell)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            for cand in index.get((ky + dy, kx + dx), []):
                d = haversine_m(lat, lon, cand["lat"], cand["lon"])
                if best_d is None or d < best_d:
                    best, best_d = cand, d
    return best, best_d


def cell_for(tolerance_m: float) -> float:
    return max(tolerance_m / 111320.0, 1e-4)


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    s, w, n, e = (float(x) for x in bbox.split(","))
    return s, w, n, e


def in_bbox(lat: float, lon: float, bb: tuple[float, ...]) -> bool:
    s, w, n, e = bb
    return s <= lat <= n and w <= lon <= e