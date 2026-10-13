export interface Station {
  id: string;
  name: string;
  lat: number;
  lon: number;
  /** Canonical rider-facing mode (bus / tram / metro / train / louaj / taxi / unclassified). */
  mode: string;
  /** Every canonical mode this stop serves. */
  modes: string[];
  /** The seed's own provenance tag, kept for audit. */
  mode_raw?: string;
  operator?: string;
  city?: string;
  source?: string;
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

/** A stop or city returned by /api/v1/search — pickable by name. */
export interface PlaceHit {
  kind: "stop" | "city";
  id: string;
  name: string;
  lat: number;
  lon: number;
  modes: string[];
  city: string;
  display_name: string;
}

/** One line serving a station, with the direction it runs in. */
export interface StationLine {
  line_id: string;
  number: string | null;
  name: string | null;
  mode: string;
  mode_label: string;
  operator: string | null;
  color: string | null;
  /** "Tunis Ville - Lycee Technique Rades" — the line's two termini. */
  direction: string | null;
  stops_count: number;
  /** Index of this station within the line's stop list. */
  stop_index?: number | null;
  /** origin = line starts here, terminus = line ends here, through = calls here. */
  role?: "origin" | "terminus" | "through";
}

export interface StationDetail {
  id: string;
  name: string | null;
  lat: number | null;
  lon: number | null;
  city: string | null;
  modes: string[];
  lines: StationLine[];
  count: number;
  /** False when no line lists this stop, so its mode is the operator's tag only. */
  lines_known?: boolean;
}

/** A physical track segment: rail/metro alignment or the road a bus follows. */
export interface NetworkSegment {
  id: string;
  mode: string;
  source: string | null;
  has_geometry: boolean;
  /** [[lat, lon], ...] — Leaflet's native order. */
  geometry: [number, number][];
  from_stop_id?: string;
  to_stop_id?: string;
  straight_m?: number;
}

export interface NetworkResponse {
  segments: NetworkSegment[];
  metadata: {
    count: number;
    by_mode: Record<string, number>;
    missing_geometry: number;
    available_modes: string[];
  };
}

export interface StationsMeta {
  count: number;
  total: number;
  /** Canonical mode -> number of features serving it. */
  by_mode: Record<string, number>;
}

export interface RoadSummary {
  summary: string;
}

export interface RailSummary {
  summary: string;
}

export interface RouteLeg {
  type?: string;
  mode?: string;
  line?: string;
  label?: string;
  from?: { lat: number; lon: number };
  to?: { lat: number; lon: number };
  from_name?: string;
  to_name?: string;
  geometry?: [number, number][];
  duration_min?: number;
  wait_min?: number;
  distance_m?: number;
}

export interface Itinerary {
  id: string;
  label: string;
  duration_min: number;
  transfers: number;
  fare_dinars: number;
  modes_used: string[];
  legs: RouteLeg[];
  geometry_complete?: boolean;
  gaps?: unknown[];
  alternatives?: unknown[];
}

export interface RoutePlan {
  query: {
    start: { lat: number; lon: number };
    end: { lat: number; lon: number };
    modes_include: string[];
    modes_exclude: string[];
    objective: string;
  };
  itineraries: Itinerary[];
  available_modes: string[];
  message?: string;
}

interface GeocodeResult {
  lat: number;
  lon: number;
  display_name: string;
  type?: string;
}

interface Api {
  getStations(): Promise<{ features: unknown[]; metadata: StationsMeta }>;
  getLines(): Promise<Line[]>;
  getNetwork(modes?: string): Promise<NetworkResponse>;
  getStation(id: string): Promise<StationDetail>;
  searchPlaces(
    q: string,
    near?: { lat: number; lon: number } | null
  ): Promise<PlaceHit[]>;
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
    const j = await res.json();
    return {
      features: (j.features ?? []) as unknown[],
      metadata: (j.metadata ?? { count: 0, total: 0, by_mode: {} }) as StationsMeta,
    };
  },

  async getLines() {
    const res = await fetch(`${BASE}/lines`);
    if (!res.ok) throw new Error(`GET /api/v1/lines -> ${res.status}`);
    const j = await res.json();
    return j.lines as Line[];
  },

  async getNetwork(modes) {
    const q = new URLSearchParams();
    if (modes) q.set("modes", modes);
    const res = await fetch(`${BASE}/network?${q.toString()}`);
    if (!res.ok) throw new Error(`GET /api/v1/network -> ${res.status}`);
    return res.json() as Promise<NetworkResponse>;
  },

  async getStation(id) {
    const res = await fetch(`${BASE}/stations/${encodeURIComponent(id)}`);
    if (!res.ok) throw new Error(`GET /api/v1/stations/${id} -> ${res.status}`);
    return res.json() as Promise<StationDetail>;
  },

  async searchPlaces(q, near) {
    const p = new URLSearchParams({ q });
    if (near) {
      p.set("near_lat", String(near.lat));
      p.set("near_lon", String(near.lon));
    }
    const res = await fetch(`${BASE}/search?${p.toString()}`);
    if (!res.ok) throw new Error(`GET /api/v1/search -> ${res.status}`);
    const j = await res.json();
    return (j.results ?? []) as PlaceHit[];
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

/** Extract the station fields from a GeoJSON feature. */
export function stationFromFeature(f: unknown): Station | null {
  const feat = f as {
    properties?: Record<string, unknown>;
    geometry?: { coordinates?: [number, number] };
  };
  const p = feat.properties ?? {};
  const coords = feat.geometry?.coordinates;
  const lat = coords?.[1] ?? 0;
  const lon = coords?.[0] ?? 0;
  if (!lat || !lon) return null;
  const modes = (p.modes as string[] | undefined) ?? [String(p.mode ?? "unclassified")];
  return {
    id: String(p.id ?? ""),
    name: String(p.name ?? "").trim(),
    lat,
    lon,
    mode: String(p.mode ?? modes[0] ?? "unclassified"),
    modes,
    mode_raw: p.mode_raw ? String(p.mode_raw) : undefined,
    operator: p.operator ? String(p.operator) : undefined,
    city: p.city ? String(p.city) : undefined,
    source: p.source ? String(p.source) : undefined,
    lines_served: (p.lines as unknown[]) ?? []
  };
}
