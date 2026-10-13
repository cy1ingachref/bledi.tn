import type { RouteQuery, TransitService } from "$lib/application/transitService";
import type {
  LouageLink,
  MapOverlay,
  NetworkSegment,
  PlaceHit,
  RoutePlan,
  Station,
  StationDetail,
  StationsMeta,
} from "$lib/domain/transit";

export interface MemoryTransitData {
  stations: Station[];
  meta: StationsMeta;
  network: NetworkSegment[];
  rail: MapOverlay;
  roads: MapOverlay;
  louageLinks: LouageLink[];
  details: Record<string, StationDetail>;
  places: PlaceHit[];
  plan: RoutePlan;
}

const EMPTY_PLAN: RoutePlan = {
  query: { start: { lat: 0, lon: 0 }, end: { lat: 0, lon: 0 }, modes_include: [], modes_exclude: [], objective: "fastest" },
  itineraries: [],
  available_modes: [],
};

export function memoryTransit(
  data: Partial<MemoryTransitData> = {}
): TransitService & { routeQueries: RouteQuery[] } {
  const routeQueries: RouteQuery[] = [];
  return {
    routeQueries,
    stations: async () => ({
      stations: data.stations ?? [],
      meta: data.meta ?? { count: 0, total: 0, by_mode: {} },
    }),
    network: async () => data.network ?? [],
    railOverlay: async () => data.rail ?? { features: [] },
    roadOverlay: async () => data.roads ?? { features: [] },
    louageLinks: async () => data.louageLinks ?? [],
    async station(id) {
      const d = data.details?.[id];
      if (!d) throw new Error(`station ${id} not found`);
      return d;
    },
    searchPlaces: async (q) =>
      (data.places ?? []).filter((p) => p.name.toLowerCase().includes(q.toLowerCase())),
    async planRoute(query) {
      routeQueries.push(query);
      return data.plan ?? EMPTY_PLAN;
    },
  };
}
