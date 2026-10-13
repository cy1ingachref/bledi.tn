import type { LouageLink, MapOverlayFeature } from "$lib/domain/transit";
import type { TransitService } from "./transitService";

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/**
 * Rail and road base layers. A failure is reported as a problem rather than
 * thrown, so a missing overlay never takes the rest of the map down.
 */
export async function loadBaseLayers(
  transit: TransitService
): Promise<{ rail: MapOverlayFeature[]; roads: MapOverlayFeature[]; problems: string[] }> {
  try {
    const [rail, roads] = await Promise.all([transit.railOverlay(), transit.roadOverlay()]);
    const problems: string[] = [];
    if (rail.error) problems.push(`rail: ${rail.error}`);
    if (roads.error) problems.push(`roads: ${roads.error}`);
    return { rail: rail.features ?? [], roads: roads.features ?? [], problems };
  } catch (e) {
    return { rail: [], roads: [], problems: [message(e)] };
  }
}

export async function loadLouageLinks(
  transit: TransitService
): Promise<{ links: LouageLink[]; problems: string[] }> {
  try {
    return { links: await transit.louageLinks(), problems: [] };
  } catch (e) {
    return { links: [], problems: [`louage: ${message(e)}`] };
  }
}

export function louageDestinations(links: LouageLink[], stationId: string): LouageLink[] {
  return links.filter((l) => l.from === stationId);
}
