"""The transit network as loaded once at startup, with its lookup indexes."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

Station = dict[str, Any]
Line = dict[str, Any]
# "a|b" keyed on the unordered stop pair, polyline stored min -> max.
Segments = dict[str, dict[str, Any]]


@dataclass(frozen=True)
class Network:
    stations: list[Station]
    lines: list[Line]
    seed_name: str = ""
    # Louage and taxi hubs come from a separate seed with its own shape
    # (`location`, `governorate`, `routes` with from/to).
    louage_stations: list[dict[str, Any]] = field(default_factory=list)
    louage_routes: list[dict[str, Any]] = field(default_factory=list)
    # None when route_geometry.json was never built, as opposed to built empty.
    segments: Segments | None = None

    @cached_property
    def station_by_id(self) -> dict[str, Station]:
        return {s["id"]: s for s in self.stations if s.get("id")}

    @cached_property
    def line_by_id(self) -> dict[str, Line]:
        return {ln["id"]: ln for ln in self.lines if ln.get("id")}

    @cached_property
    def lines_by_number(self) -> dict[str, list[Line]]:
        out: dict[str, list[Line]] = defaultdict(list)
        for ln in self.lines:
            num = str(ln.get("number") or ln.get("route_id") or "")
            if num:
                out[num].append(ln)
        return out

    @cached_property
    def lines_by_station(self) -> dict[str, list[str]]:
        """Line ids calling at each stop, from the line stop arrays.

        The station's own `lines_served` fragments are direction-oriented and
        often lack a route_short_name, so they are not the source.
        """
        out: dict[str, list[str]] = defaultdict(list)
        for ln in self.lines:
            ln_id = ln.get("id", "") or ""
            if not ln_id:
                continue
            for sid in ln.get("stations") or ln.get("stops") or []:
                if isinstance(sid, str):
                    out[sid].append(ln_id)
        return out

    @cached_property
    def louage_routes_by_stop(self) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in self.louage_routes:
            for endpoint in (r.get("from"), r.get("to")):
                if endpoint:
                    out[endpoint].append(r)
        return out

    def segment_geometry(self, from_id: str | None, to_id: str | None) -> list[list[float]]:
        """Cached polyline between two stops in travel order, [] when there is none."""
        if not from_id or not to_id or not self.segments:
            return []
        entry = self.segments.get(f"{min(from_id, to_id)}|{max(from_id, to_id)}")
        if not entry or not entry.get("geometry"):
            return []
        pts = entry["geometry"]
        return list(reversed(pts)) if from_id > to_id else list(pts)
