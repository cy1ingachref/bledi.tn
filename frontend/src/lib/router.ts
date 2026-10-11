export interface Station {
  id: string;
  name: string;
  lat: number;
  lon: number;
  mode: string;
  operator?: string;
  lines_served?: unknown[];
}

export interface Line {
  id: string;
  number: string;
  name: string;
  mode: string;
  route_id: string;
  stops_count: number;
}

export interface RoadSummary {
  summary: string;
}

export interface RailSummary {
  summary: string;
}

export interface RoutePlan {
  query: {
    start: { lat: number; lon: number };
    end: { lat: number; lon: number };
    modes_include: string[];
    modes_exclude: string[];
    objective: string;
  };
  itineraries: {
    id: string;
    label: string;
    duration_min: number;
    transfers: number;
    fare_dinars: number;
    modes_used: string[];
    legs: unknown[];
    geometry_complete?: boolean;
    gaps: unknown[];
    alternatives: unknown[];
  }[];
  available_modes: string[];
}

interface GeocodeResult {
  lat: number;
  lon: number;
  display_name: string;
  type?: string;
}

interface Api {
  getStations(): Promise<Station[]>;
  getLines(): Promise<Line[]>;
  getRoads(): Promise<RoadSummary>;
  getRails(): Promise<RailSummary>;
  geocode(q: string): Promise<GeocodeResult[]>;
  routePlan(params: {
    startLat: number;
    startLon: number;
    endLat: number;
    endLon: number;
    modesInclude?: string;
    modesExclude?: string;
    objective?: string;
  }): Promise<RoutePlan>;
}

const BASE = "/api/v1";

export const api: Api = {
  async getStations() {
    const res = await fetch(`${BASE}/stations`);
    if (!res.ok) throw new Error(`GET /api/v1/stations -> ${res.status}`);
    return res.json() as Promise<Station[]>;
  },

  async getLines() {
    const res = await fetch(`${BASE}/lines`);
    if (!res.ok) throw new Error(`GET /api/v1/lines -> ${res.status}`);
    const j = await res.json();
    return j.lines as Line[];
  },

  async getRoads() {
    const res = await fetch(`${BASE}/roads`);
    if (!res.ok) throw new Error(`GET /api/v1/roads -> ${res.status}`);
    return res.json() as Promise<RoadSummary>;
  },

  async getRails() {
    const res = await fetch(`${BASE}/rails`);
    if (!res.ok) throw new Error(`GET /api/v1/rails -> ${res.status}`);
    return res.json() as Promise<RailSummary>;
  },

  async geocode(q) {
    const res = await fetch(`${BASE}/geocode?q=${encodeURIComponent(q)}`);
    if (!res.ok) throw new Error(`GET /api/v1/geocode -> ${res.status}`);
    const j = await res.json();
    return (j.results ?? []) as GeocodeResult[];
  },

  async routePlan(params) {
    const q = new URLSearchParams({
      start_lat: String(params.startLat),
      start_lon: String(params.startLon),
      end_lat: String(params.endLat),
      end_lon: String(params.endLon),
    });
    if (params.modesInclude) q.set("modes_include", params.modesInclude);
    if (params.modesExclude) q.set("modes_exclude", params.modesExclude);
    if (params.objective) q.set("objective", params.objective);
    const res = await fetch(`${BASE}/route/plan?${q.toString()}`);
    if (!res.ok) throw new Error(`GET /api/v1/route/plan -> ${res.status}`);
    return res.json() as Promise<RoutePlan>;
  }
};
