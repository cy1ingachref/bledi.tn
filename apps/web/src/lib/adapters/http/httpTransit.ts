import type { TransitService } from "$lib/application/transitService";
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

type Fetch = (url: string) => Promise<Response>;

function stationFromFeature(f: unknown): Station | null {
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
    lines_served: (p.lines as unknown[]) ?? [],
  };
}

export function httpTransit(fetchFn: Fetch = (url) => fetch(url), base = "/api/v1"): TransitService {
  /** `label` is the path the error names, without the query string. */
  async function get(path: string, label = path): Promise<Response> {
    const res = await fetchFn(`${base}${path}`);
    if (!res.ok) throw new Error(`GET ${base}${label} -> ${res.status}`);
    return res;
  }

  async function overlay(path: string, notBuilt: string): Promise<MapOverlay> {
    const res = await fetchFn(`${base}${path}`);
    if (res.status === 503) {
      const j = await res.json().catch(() => ({}));
      return { features: [], error: j.detail ?? notBuilt };
    }
    if (!res.ok) throw new Error(`GET ${base}${path} -> ${res.status}`);
    return res.json();
  }

  return {
    async stations() {
      const j = await (await get("/stations")).json();
      const features: unknown[] = j.features ?? [];
      return {
        stations: features.map(stationFromFeature).filter((s): s is Station => !!s),
        meta: (j.metadata ?? { count: 0, total: 0, by_mode: {} }) as StationsMeta,
      };
    },

    async network() {
      const j = await (await get("/network")).json();
      return j.segments as NetworkSegment[];
    },

    railOverlay: () => overlay("/map/rail", "rail overlay not built"),
    roadOverlay: () => overlay("/map/roads", "road overlay not built"),

    async louageLinks() {
      const j = await (await get("/louage/links")).json();
      return (j.links ?? []) as LouageLink[];
    },

    async station(id) {
      return (await get(`/stations/${encodeURIComponent(id)}`, `/stations/${id}`)).json() as Promise<StationDetail>;
    },

    async searchPlaces(q, near) {
      const p = new URLSearchParams({ q });
      if (near) {
        p.set("near_lat", String(near.lat));
        p.set("near_lon", String(near.lon));
      }
      const j = await (await get(`/search?${p}`, "/search")).json();
      return (j.results ?? []) as PlaceHit[];
    },

    async planRoute(query) {
      const p = new URLSearchParams({
        start_lat: String(query.start.lat),
        start_lon: String(query.start.lon),
        end_lat: String(query.end.lat),
        end_lon: String(query.end.lon),
      });
      if (query.modesInclude) p.set("modes_include", query.modesInclude);
      p.set("objective", query.objective);
      return (await get(`/route/plan?${p}`, "/route/plan")).json() as Promise<RoutePlan>;
    },
  };
}
