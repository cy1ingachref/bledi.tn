import type { LatLng, Place } from "./data";

export type Mode = "tgm" | "bus" | "train" | "louage" | "taxi" | "walk";

export interface Step {
  kind: "walk" | "tgm" | "bus" | "train" | "louage" | "taxi" | "exit";
  target: Place | { fr: string; ar: string; en: string };
  line?: string;
  minutes: number;
  stops?: number;
}

export interface RouteOption {
  id: Mode;
  label: string;
  line: string;
  color: string;
  minutes: number;
  depart: Date;
  arrive: Date;
  waitMin: number;
  price: number;
  steps: Step[];
  path: LatLng[];
  walkPaths: LatLng[][];
  stopsOnPath: LatLng[];
  headsign: Place;
  estimated: boolean;
}

export async function planRoutes(from: Place, to: Place, now: Date): Promise<RouteOption[]> {
  if (from.id === to.id) return [];
  try {
    const url = `/api/v1/route/plan?start_lat=${from.pos[0]}&start_lon=${from.pos[1]}&end_lat=${to.pos[0]}&end_lon=${to.pos[1]}&modes_include=bus,train,louage,taxi&max_itineraries=6`;
    const res = await fetch(url);
    if (!res.ok) return fallbackRoutes(from, to, now);
    const data = await res.json();
    const its = Array.isArray(data.itineraries) ? data.itineraries : [];
    if (!its.length) return fallbackRoutes(from, to, now);
    return its.map((it: any, idx: number) => toRouteOption(from, to, now, it, idx));
  } catch {
    return fallbackRoutes(from, to, now);
  }
}

function toRouteOption(from: Place, to: Place, now: Date, it: any, _idx: number): RouteOption {
  const modesUsed = Array.isArray(it.modes_used) ? it.modes_used : [];
  // A pure-walk itinerary has no modes_used. Defaulting it to "bus" made it
  // collide with the real bus card (same id => same React key, wrong badge).
  const mode: Mode = (modesUsed[0] as Mode) || "walk";
  const label = modeLabels(mode);
  const color = modeColors(mode);
  const line = String(it.label || it.route_short_name || mode.toUpperCase());
  const depart = new Date(now);
  const arrive = new Date(depart.getTime() + (Number(it.duration_min || 0) || 15) * 60000);
  const waitMin = Math.max(0, Math.round((it.wait_min || 0) || 0));
  const price = Number(it.fare_estimate_dinars || 0) || 0.7;
  const steps: Step[] = [];
  const legs = Array.isArray(it.legs) ? it.legs : [];
  for (const leg of legs) {
    if (leg.type === "walk") {
      steps.push({
        kind: "walk",
        target: to,
        minutes: Math.round(Number(leg.duration_min || 0) || 0),
      });
    } else if (leg.type === "ride") {
      const m = leg.mode === "train" || leg.mode === "tgm" || leg.mode === "metro" ? "train" : leg.mode === "louage" ? "louage" : leg.mode === "taxi" ? "taxi" : "bus";
      const targetName = { fr: leg.to_name || to.fr, ar: leg.to_name || to.ar, en: leg.to_name || to.en };
      steps.push({
        kind: m,
        target: targetName,
        line: leg.line ? String(leg.line) : undefined,
        minutes: Math.round(Number(leg.duration_min || 0) || 0),
        stops: leg.stops ? Math.round(Number(leg.stops)) : undefined,
      });
    }
  }
  if (!steps.length) steps.push({ kind: (mode === "walk" ? "walk" : mode) as Step["kind"], target: to, minutes: Math.round(Number(it.duration_min || 0) || 15) });
  const path = points(from.pos, legs) || [from.pos, to.pos];
  const walkPaths: LatLng[][] = [];
  const stopsOnPath = path.slice(1, -1);
  return {
    id: mode,
    label,
    line,
    color,
    minutes: Math.round(Number(it.duration_min || 0) || 15),
    depart,
    arrive,
    waitMin,
    price,
    steps,
    path,
    walkPaths,
    stopsOnPath,
    headsign: to,
    estimated: it.estimated === true,
  };
}

function fallbackRoutes(from: Place, to: Place, now: Date): RouteOption[] {
  const R: RouteOption[] = [];
  const addBus = () => {
    const ride = 18;
    const dep = new Date(now);
    dep.setMinutes(dep.getMinutes() + 4, 0, 0);
    const arrive = new Date(dep.getTime() + (ride + 3) * 60000);
    R.push({
      id: "bus", label: "Bus", line: "Bus", color: "#2e9e5b", minutes: ride + 7, depart: dep, arrive, waitMin: 4, price: 0.5,
      steps: [
        { kind: "walk", target: to, minutes: 3 },
        { kind: "bus", target: to, line: "Bus", minutes: ride, stops: 8 },
        { kind: "exit", target: to, minutes: 2 },
      ],
      path: [from.pos, to.pos], walkPaths: [], stopsOnPath: [], headsign: to, estimated: true,
    });
  };
  const addTaxi = () => {
    const ride = 12;
    const dep = new Date(now);
    dep.setMinutes(dep.getMinutes() + 1, 0, 0);
    const arrive = new Date(dep.getTime() + ride * 60000);
    R.push({
      id: "taxi", label: "Taxi", line: "Taxi", color: "#e0a800", minutes: ride, depart: dep, arrive, waitMin: 1, price: 4.5,
      steps: [{ kind: "taxi", target: to, minutes: ride }],
      path: [from.pos, to.pos], walkPaths: [], stopsOnPath: [], headsign: to, estimated: true,
    });
  };
  addBus();
  addTaxi();
  return R;
}

function points(from: LatLng, legs: any[]): LatLng[] {
  const out: LatLng[] = [from];
  for (const leg of legs) {
    if (leg.geometry && Array.isArray(leg.geometry)) {
      for (const p of leg.geometry) {
        if (Array.isArray(p) && p.length >= 2) out.push([Number(p[0]), Number(p[1])]);
      }
    }
  }
  return out;
}

function modeLabels(m: string) {
  if (m === "tgm" || m === "train" || m === "metro") return "TGM";
  if (m === "louage") return "Louage";
  if (m === "taxi") return "Taxi";
  if (m === "walk") return "Marche";
  return "Bus";
}
function modeColors(m: string) {
  if (m === "tgm" || m === "train" || m === "metro") return "#1f6f8b";
  if (m === "louage") return "#7c3aed";
  if (m === "taxi") return "#e0a800";
  if (m === "walk") return "#94a3b8";
  return "#2e9e5b";
}

export const hhmm = (d: Date) =>
  `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
