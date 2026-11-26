/**
 * Line catalog: one table per line, listing every stop in travel order with its
 * name and coordinates, plus the line's real track.
 *
 * Sourced from the backend (`/api/v1/lines`, `/api/v1/lines/{id}`), not from the
 * router: the route planner only returns stops for a journey between two places,
 * so it cannot show "every stop this bus number calls at".
 */

export type LineMode = "bus" | "train" | "metro" | "rail" | "louage";

export interface LineSummary {
  id: string;
  number: string | null;
  short_name: string | null;
  long_name: string | null;
  mode: LineMode;
  color: string | null;
  route_id: string | null;
  stops_count: number;
}

export interface LineStop {
  stop_id: string;
  name: string;
  lat: number | null;
  lon: number | null;
  /** Line ids calling at this stop, from the network's line -> stops index. */
  lines: unknown[] | null;
}

export interface LineGeometrySegment {
  from_stop_id: string | null;
  to_stop_id: string | null;
  from_name: string | null;
  to_name: string | null;
  has_geometry: boolean;
  needs_geometry: boolean;
  gap_m: number | null;
  geometry: [number, number][];
}

export interface LineGap {
  from_stop_id: string | null;
  to_stop_id: string | null;
  from_name: string | null;
  to_name: string | null;
  gap_m: number;
  reason?: string;
}

export interface LineDetail {
  line: {
    id: string;
    number?: string | null;
    name?: string | null;
    operator?: string | null;
    mode?: string;
    type?: string | null;
    route_id?: string | null;
    stations?: string[];
  };
  stops: LineStop[];
  count: number;
  mode: string;
  mode_label: string | null;
  geometry: { type: string; coordinates: number[][] } | null;
  geometry_complete: boolean;
  geometry_segments: LineGeometrySegment[];
  gaps: LineGap[];
}

const MODE_ORDER: LineMode[] = ["bus", "train", "metro", "rail", "louage"];

function apiBase(): string {
  // Same origin in dev (Vite proxies /api/v1) and in the single-file build.
  return "/api/v1";
}

export async function fetchLines(): Promise<LineSummary[]> {
  const r = await fetch(`${apiBase()}/lines`);
  if (!r.ok) throw new Error(`lines ${r.status}`);
  const d = await r.json();
  const lines = (d.lines || []) as LineSummary[];
  // Stable order: mode, then line number (numeric where possible), then id.
  return lines.sort((a, b) => {
    const m = MODE_ORDER.indexOf(a.mode) - MODE_ORDER.indexOf(b.mode);
    if (m) return m;
    const na = Number(a.number);
    const nb = Number(b.number);
    if (Number.isFinite(na) && Number.isFinite(nb) && na !== nb) return na - nb;
    return (a.number || a.id).localeCompare(b.number || b.id, undefined, { numeric: true });
  });
}

export async function fetchLine(id: string): Promise<LineDetail> {
  const r = await fetch(`${apiBase()}/lines/${encodeURIComponent(id)}`);
  if (!r.ok) throw new Error(`line ${r.status}`);
  return (await r.json()) as LineDetail;
}

/** Stops in travel order, each paired with the coordinates the map should use. */
export function orderedStops(detail: LineDetail): (LineStop & { order: number })[] {
  return detail.stops.map((s, i) => ({ ...s, order: i }));
}

/** The line's track as a [lat, lon] list, or [] when incomplete. */
export function linePath(detail: LineDetail): [number, number][] {
  const coords = detail.geometry?.coordinates;
  if (!Array.isArray(coords) || coords.length < 2) return [];
  // The API returns GeoJSON [lon, lat]; the app works in [lat, lon].
  return coords.map((c) => [c[1], c[0]] as [number, number]);
}

/**
 * The line's track split into continuous runs, so a line with a missing middle
 * still draws its real track on both sides of the gap instead of vanishing.
 */
export function linePathRuns(detail: LineDetail): [number, number][][] {
  const runs: [number, number][][] = [];
  let cur: [number, number][] = [];
  for (const seg of detail.geometry_segments || []) {
    const pts = seg.geometry || [];
    if (pts.length < 2) {
      // A break in the track ends the current run.
      if (cur.length >= 2) runs.push(cur);
      cur = [];
      continue;
    }
    // Segment geometry is already [lat, lon] (the API stores it that way).
    const run: [number, number][] = pts.map((p) => [p[0], p[1]]);
    if (!cur.length) {
      cur = run;
    } else {
      // Join only when the segments actually meet; otherwise start a new run.
      const tail = cur[cur.length - 1];
      const head = run[0];
      const joined = Math.abs(tail[0] - head[0]) < 1e-6 && Math.abs(tail[1] - head[1]) < 1e-6;
      cur = joined ? cur.concat(run.slice(1)) : cur;
      if (!joined) {
        runs.push(cur);
        cur = run;
      }
    }
  }
  if (cur.length >= 2) runs.push(cur);
  return runs;
}

/** Missing-track pairs, with their endpoints, so the UI can say what is omitted. */
export function missingSegments(detail: LineDetail): LineGap[] {
  return detail.gaps || [];
}
