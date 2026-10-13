import { isWalkMode } from "./modes";
import type { Itinerary, RouteLeg } from "./transit";

export function isWalkLeg(leg: RouteLeg): boolean {
  return isWalkMode(leg.type);
}

/** The fare field differs across API versions; read whichever is present. */
export function fareOf(itin: Itinerary): number {
  const v = itin.fare_estimate_dinars ?? itin.fare_dinars ?? 0;
  return typeof v === "number" ? v : 0;
}

/** The rider-facing number in an internal line id: "rail_19_a" -> "19". */
export function lineNumber(line: string | undefined): string | null {
  const m = (line ?? "").match(/(\d+[A-Za-z]?)/);
  return m ? m[1] : null;
}

/**
 * Collapse consecutive legs that ride the same line into one step.
 *
 * The router emits one leg per hop, splitting a single ride at every stop
 * where a transfer is possible, so a 9-hop bus ride arrives as 9 identical
 * rows. Merging is keyed on (mode, line) plus the walk/ride distinction, so a
 * genuine change of line or mode keeps its own step. Walking legs are never
 * merged: two walks separated by a ride are different streets.
 */
export function mergeLegs(legs: RouteLeg[]): RouteLeg[] {
  const out: RouteLeg[] = [];
  for (const leg of legs) {
    const prev = out[out.length - 1];
    const sameRide =
      prev &&
      !isWalkLeg(leg) &&
      !isWalkLeg(prev) &&
      (prev.mode ?? "") === (leg.mode ?? "") &&
      (prev.line ?? "") === (leg.line ?? "");
    if (sameRide) {
      prev.duration_min = (prev.duration_min ?? 0) + (leg.duration_min ?? 0);
      prev.to_name = leg.to_name ?? prev.to_name;
      prev.to = leg.to ?? prev.to;
      continue;
    }
    out.push({ ...leg });
  }
  return out;
}
