import { modeKey, type ModeId } from "$lib/domain/modes";

/**
 * One neon colour per transport category. The same colour marks the mode
 * chip, the network line on the map and the route leg, so a rider learns one
 * colour per transport and can then read the whole map. The hex values match
 * the dark-theme --n-<mode> tokens; Leaflet needs literal colours.
 */
export const MODE_STYLE: Record<ModeId, { icon: string; color: string }> = {
  bus: { icon: "bus", color: "#ff3d81" },
  tram: { icon: "tram", color: "#ffc400" },
  metro: { icon: "metro", color: "#2f7bff" },
  train: { icon: "train", color: "#a855f7" },
  taxi_louage: { icon: "taxi", color: "#00e5c0" },
  walk: { icon: "walk", color: "#8b83a8" },
};

export interface ModeChip {
  id: ModeId;
  count: number;
  icon: string;
  color: string;
}

export function modeColor(raw: string): string {
  const k = modeKey(raw);
  return k === "unclassified" ? "#5a5473" : MODE_STYLE[k].color;
}

export function modeIcon(raw: string): string {
  const k = modeKey(raw);
  return k === "unclassified" ? "pin" : MODE_STYLE[k].icon;
}
