import type { LouageLink, MapOverlayFeature } from "$lib/domain/transit";
import type { TransitService } from "./transitService";

/**
 * Rail and road base layers, and the louage links, are context around the
 * route. Each one that fails or was never built comes back empty instead of
 * throwing, so it never takes the rest of the map down.
 */
export async function loadBaseLayers(
  transit: TransitService
): Promise<{ rail: MapOverlayFeature[]; roads: MapOverlayFeature[] }> {
  try {
    const [rail, roads] = await Promise.all([transit.railOverlay(), transit.roadOverlay()]);
    return { rail: rail.features ?? [], roads: roads.features ?? [] };
  } catch {
    return { rail: [], roads: [] };
  }
}

export async function loadLouageLinks(transit: TransitService): Promise<LouageLink[]> {
  try {
    return await transit.louageLinks();
  } catch {
    return [];
  }
}

export function louageDestinations(links: LouageLink[], stationId: string): LouageLink[] {
  return links.filter((l) => l.from === stationId);
}
