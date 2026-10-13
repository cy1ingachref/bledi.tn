import type { Station } from "./transit";

/**
 * Rider-facing transport categories, in display order.
 *
 * Taxi and louage are ONE category: both are road-for-hire and a rider picks
 * between them on price at the roadside. The backend keeps them as distinct
 * raw modes ("taxi" / "louaj"), so the category expands back to both on the
 * wire (see modesInclude).
 *
 * `unclassified` is deliberately not a category. It tags geocoded sweep stops
 * whose operator export carried no mode: they have no lines and are not
 * routable, so it is a map-visibility filter only. Sending it to the router
 * would be silently rewritten to "bus" by the backend's unknown -> bus default.
 */
export const MODES = ["bus", "tram", "metro", "train", "taxi_louage", "walk"] as const;

export type ModeId = (typeof MODES)[number];

const TAXI_LOUAGE = new Set(["taxi", "louaj", "louage", "louage_red", "louage_blue", "louage_green"]);

/** Scheduled modes, the most common Tunisian combination. */
export const DEFAULT_MODES: ModeId[] = ["bus", "metro", "train", "tram"];

export function modeKey(raw: string): ModeId | "unclassified" {
  if (raw === "unclassified") return "unclassified";
  if (TAXI_LOUAGE.has(raw)) return "taxi_louage";
  return (MODES as readonly string[]).includes(raw) ? (raw as ModeId) : "bus";
}

export function isWalkMode(raw: string | undefined): boolean {
  return (raw ?? "").toLowerCase() === "walk";
}

/** Unique categories present in a raw mode list, in display order. */
export function uniqueModes(raws: string[]): ModeId[] {
  const seen = new Set<string>();
  for (const r of raws) seen.add(modeKey(r));
  return MODES.filter((m) => seen.has(m));
}

/** The router's `modes_include` value for a selection of categories. */
export function modesInclude(selected: ReadonlySet<string>): string {
  const out: string[] = [];
  for (const id of MODES) {
    if (!selected.has(id)) continue;
    if (id === "taxi_louage") out.push("taxi", "louaj");
    else out.push(id);
  }
  return out.join(",");
}

/**
 * The selectable categories the network actually serves, with stop counts.
 *
 * Read from the inventory rather than hardcoded: the seed carries no tram
 * lines and folds the suburban lines into `train`, so a fixed list offered
 * modes that could never return a result. Walking is always offered.
 */
export function servedModes(byMode: Record<string, number>): { id: ModeId; count: number }[] {
  const counts: Record<string, number> = {};
  for (const [raw, n] of Object.entries(byMode)) {
    const k = modeKey(raw);
    if (k === "unclassified") continue;
    counts[k] = (counts[k] ?? 0) + n;
  }
  return MODES.filter((id) => (counts[id] ?? 0) > 0 || id === "walk").map((id) => ({
    id,
    count: counts[id] ?? 0,
  }));
}

/** The default categories, limited to those the inventory serves. */
export function defaultSelection(byMode: Record<string, number>): Set<string> {
  const present = new Set<string>();
  for (const [raw, n] of Object.entries(byMode)) {
    if (n > 0) present.add(modeKey(raw));
  }
  return new Set(DEFAULT_MODES.filter((m) => present.has(m)));
}

export function isStationShown(s: Station, selected: ReadonlySet<string>, showUnclassified: boolean): boolean {
  return s.mode === "unclassified" ? showUnclassified : selected.has(modeKey(s.mode));
}
