import { modesInclude } from "$lib/domain/modes";
import type { Endpoint, Objective, RoutePlan } from "$lib/domain/transit";
import type { TransitService } from "./transitService";

export type TripProblem = "no_modes" | "missing_endpoints";

export function tripProblem(
  selected: ReadonlySet<string>,
  from: Endpoint | null,
  to: Endpoint | null
): TripProblem | null {
  if (selected.size === 0) return "no_modes";
  if (!from || !to) return "missing_endpoints";
  return null;
}

export function planTrip(
  transit: TransitService,
  trip: { from: Endpoint; to: Endpoint; selected: ReadonlySet<string>; objective: Objective }
): Promise<RoutePlan> {
  return transit.planRoute({
    start: { lat: trip.from.lat, lon: trip.from.lon },
    end: { lat: trip.to.lat, lon: trip.to.lon },
    modesInclude: modesInclude(trip.selected),
    objective: trip.objective,
  });
}
