import type {
  LouageLink,
  MapOverlay,
  NetworkSegment,
  Objective,
  PlaceHit,
  RoutePlan,
  Station,
  StationDetail,
  StationsMeta,
} from "$lib/domain/transit";

export interface LatLon {
  lat: number;
  lon: number;
}

export interface RouteQuery {
  start: LatLon;
  end: LatLon;
  /** Comma-separated raw backend modes. */
  modesInclude: string;
  objective: Objective;
}

export interface TransitService {
  stations(): Promise<{ stations: Station[]; meta: StationsMeta }>;
  network(): Promise<NetworkSegment[]>;
  /** Resolves with an empty overlay carrying `error` when the overlay was never built. */
  railOverlay(): Promise<MapOverlay>;
  roadOverlay(): Promise<MapOverlay>;
  louageLinks(): Promise<LouageLink[]>;
  station(id: string): Promise<StationDetail>;
  searchPlaces(q: string, near: LatLon | null): Promise<PlaceHit[]>;
  planRoute(query: RouteQuery): Promise<RoutePlan>;
}
