export interface Station {
  id: string;
  name: string;
  lat: number;
  lon: number;
  /** Canonical rider-facing mode (bus / tram / metro / train / louaj / taxi / unclassified). */
  mode: string;
  modes: string[];
  /** The seed's own provenance tag, kept for audit. */
  mode_raw?: string;
  operator?: string;
  city?: string;
  source?: string;
  lines_served?: unknown[];
}

export interface StationsMeta {
  count: number;
  total: number;
  /** Canonical mode -> number of features serving it. */
  by_mode: Record<string, number>;
}

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

export interface StationLine {
  line_id: string;
  number: string | null;
  name: string | null;
  mode: string;
  mode_label: string;
  operator: string | null;
  color: string | null;
  /** The line's two termini, e.g. "Tunis Ville - Lycee Technique Rades". */
  direction: string | null;
  stops_count: number;
  stop_index?: number | null;
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
  /** [[lat, lon], ...], Leaflet's native order. */
  geometry: [number, number][];
  from_stop_id?: string;
  to_stop_id?: string;
  straight_m?: number;
}

export interface RouteLeg {
  type?: string;
  mode?: string;
  /** Internal line id such as "rail_19_a". */
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
  fare_estimate_dinars?: number;
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

/**
 * A built map overlay (rail or road alignment), in Leaflet order.
 * `properties.mode` is train/metro for rail; `properties.highway` and `ref`
 * carry the road class and number (RN1, A1) for roads.
 */
export interface MapOverlayFeature {
  kind: "rail" | "road";
  properties: {
    mode?: string;
    railway?: string;
    highway?: string;
    ref?: string;
    name?: string;
    operator?: string;
    lanes?: string;
    oneway?: string;
  };
  geometry: [number, number][];
}

/** `error` is set, with no features, when the overlay was never built. */
export interface MapOverlay {
  features: MapOverlayFeature[];
  error?: string;
}

export interface LouageLink {
  from: string;
  to: string;
  from_name: string;
  to_name: string;
  destination_raw: string;
}

export type Objective = "fastest" | "cheapest" | "fewest_transfers";

export const OBJECTIVES: Objective[] = ["fastest", "cheapest", "fewest_transfers"];

/** A named place the rider picked; latitude and longitude are never typed in. */
export interface Endpoint {
  kind: "stop" | "city" | "map" | "gps";
  name: string;
  lat: number;
  lon: number;
  id?: string;
  modes?: string[];
}
