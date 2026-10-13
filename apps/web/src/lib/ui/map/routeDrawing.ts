import L from "leaflet";
import { isWalkLeg } from "$lib/domain/itinerary";
import { modeKey } from "$lib/domain/modes";
import type { Itinerary } from "$lib/domain/transit";
import { modeColor } from "$lib/ui/modeStyle";
import { prefersReducedMotion, type Resolved } from "$lib/ui/theme";

/** Perpendicular offset at vertex i, so the dot rides parallel to the line. */
function perpAt(pts: [number, number][], i: number): [number, number] {
  const a = pts[Math.max(0, i - 1)];
  const b = pts[Math.min(pts.length - 1, i + 1)];
  const dLat = b[0] - a[0];
  const dLng = (b[1] - a[1]) * Math.cos((a[0] * Math.PI) / 180);
  const len = Math.hypot(dLat, dLng) || 1;
  const m = 5 / 111320;
  return [(-dLng / len) * m, (dLat / len) * m];
}

function riderColor(shade: Resolved): string {
  return shade === "light" ? "#0a7a62" : "#3df2c9";
}

/**
 * The calculated route: each leg in its transport's neon colour, the line
 * drawing itself in, a flowing highlight on top, and a traveller dot walking
 * it. The animations are skipped under prefers-reduced-motion.
 */
export class RouteDrawing {
  private readonly layer: L.LayerGroup;
  private renderer: L.SVG | null = null;
  private rider: L.CircleMarker | null = null;
  private riderRaf = 0;
  /** Pending timeouts that clear the draw-in dash once the animation is over. */
  private drawTimers: number[] = [];

  constructor(private readonly map: L.Map) {
    // The traveller dot lives above the station markers in its own pane, so
    // dimming the rest of the network in focus mode never dims it.
    map.createPane("riderPane");
    const rp = map.getPane("riderPane");
    if (rp) { rp.style.zIndex = "650"; rp.style.pointerEvents = "none"; }

    // Route lines get SVG (not canvas) so each leg can carry a per-mode class
    // and therefore its own neon glow, and so the draw-in animation has a real
    // path element to measure.
    map.createPane("routePane");
    const rt = map.getPane("routePane");
    if (rt) rt.style.zIndex = "420";

    this.layer = L.layerGroup().addTo(map);
  }

  private svg(): L.SVG {
    if (!this.renderer) this.renderer = L.svg({ padding: 0.5, pane: "routePane" });
    return this.renderer;
  }

  setShade(shade: Resolved): void {
    this.rider?.setStyle({ color: riderColor(shade) });
  }

  stopRider(): void {
    if (this.riderRaf) cancelAnimationFrame(this.riderRaf);
    this.riderRaf = 0;
    if (this.rider) {
      this.map.removeLayer(this.rider);
      this.rider = null;
    }
  }

  private clearDrawTimers(): void {
    for (const t of this.drawTimers) clearTimeout(t);
    this.drawTimers = [];
  }

  /**
   * Waits until every leg has its SVG path: the renderer creates them lazily,
   * and the zoom from `fitBounds` re-renders them. The dash is then cleared
   * unconditionally, because an interrupted draw-in (zoom, throttled tab)
   * would leave the line stuck invisible at `stroke-dashoffset: 100%`.
   */
  private animateDrawIn(lines: L.Polyline[]): void {
    this.clearDrawTimers();
    let attempts = 0;
    const apply = () => {
      const els = lines
        .map((l) => (l as unknown as { _path?: SVGPathElement })._path)
        .filter((e): e is SVGPathElement => !!e);
      if (els.length < lines.length && attempts < 40) {
        attempts++;
        requestAnimationFrame(apply);
        return;
      }
      const drawn: SVGPathElement[] = [];
      for (const el of els) {
        const len = el.getTotalLength?.() ?? 0;
        if (!len) continue;
        el.style.strokeDasharray = String(len);
        el.style.strokeDashoffset = String(len);
        el.style.animation = "bledi-draw 1.1s cubic-bezier(.4,0,.2,1) forwards";
        drawn.push(el);
      }
      if (!drawn.length) return;
      this.drawTimers.push(
        window.setTimeout(() => {
          for (const el of drawn) {
            el.style.strokeDasharray = "";
            el.style.strokeDashoffset = "";
            el.style.animation = "";
          }
        }, 1800)
      );
    };
    requestAnimationFrame(apply);
  }

  draw(itin: Itinerary, shade: Resolved): void {
    this.stopRider();
    this.clearDrawTimers();
    this.layer.clearLayers();

    const reduced = prefersReducedMotion();
    const legs = itin.legs ?? [];
    const drawable: L.Polyline[] = [];

    for (const leg of legs) {
      if (!leg.geometry || leg.geometry.length < 2) continue;
      const isWalk = isWalkLeg(leg);
      const key = isWalk ? "walk" : modeKey(leg.mode ?? "bus");
      const pts = leg.geometry.map(([a, b]) => [a, b] as [number, number]);
      const walkColor = shade === "light" ? "#6b7280" : "#8b83a8";
      const color = isWalk ? walkColor : modeColor(leg.mode ?? "bus");

      // Casing keeps the leg legible over same-coloured station dots. It is
      // theme-aware: a dark casing on a light basemap reads as a shadow.
      if (!isWalk) {
        L.polyline(pts, {
          color: shade === "light" ? "rgba(255,252,248,0.92)" : "#04010c",
          weight: 11, opacity: 0.9, lineCap: "round",
          interactive: false, renderer: this.svg(),
        }).addTo(this.layer);
      }
      const main = L.polyline(pts, {
        color,
        weight: isWalk ? 3 : 5.5,
        opacity: isWalk ? 0.85 : 1,
        dashArray: isWalk ? "2 7" : undefined,
        lineCap: "round",
        lineJoin: "round",
        interactive: false,
        className: `route-leg route-leg-${key}${reduced || isWalk ? "" : " route-draw"}`,
        renderer: this.svg(),
      }).addTo(this.layer);

      if (!isWalk && !reduced) {
        L.polyline(pts, {
          color: "#ffffff",
          weight: 2,
          opacity: 0.9,
          dashArray: "2 14",
          lineCap: "round",
          interactive: false,
          className: "route-flow",
          renderer: this.svg(),
        }).addTo(this.layer);
      }

      if (!isWalk) drawable.push(main);
    }

    const all: [number, number][] = [];
    for (const l of legs) if (l.geometry) all.push(...l.geometry);
    if (!all.length) return;

    this.map.fitBounds(L.latLngBounds(all).pad(0.18));
    if (!reduced && drawable.length) this.animateDrawIn(drawable);

    if (reduced || all.length < 2) return;
    this.startRider(all, shade);
  }

  private startRider(all: [number, number][], shade: Resolved): void {
    const MAX_RIDER_POINTS = 220;
    const stride = Math.max(1, Math.ceil(all.length / MAX_RIDER_POINTS));
    const walk: [number, number][] = [];
    for (let i = 0; i < all.length; i += stride) walk.push(all[i]);
    if (walk[walk.length - 1] !== all[all.length - 1]) walk.push(all[all.length - 1]);

    const startPerp = perpAt(walk, 0);
    const rider = L.circleMarker([walk[0][0] + startPerp[0], walk[0][1] + startPerp[1]], {
      pane: "riderPane",
      radius: 6,
      color: riderColor(shade),
      weight: 3,
      fillColor: "#ffffff",
      fillOpacity: 1,
      interactive: false,
    }).addTo(this.map);
    this.rider = rider;

    const DURATION_MS = 4200;
    const start = performance.now();
    const step = (now: number) => {
      if (this.rider !== rider) return;
      const p = Math.min(1, (now - start) / DURATION_MS);
      const e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
      const f = e * (walk.length - 1);
      const i = Math.min(walk.length - 2, Math.floor(f));
      const frac = f - i;
      const a = walk[i];
      const b = walk[i + 1];
      const off = perpAt(walk, i);
      rider.setLatLng([
        a[0] + (b[0] - a[0]) * frac + off[0],
        a[1] + (b[1] - a[1]) * frac + off[1],
      ]);
      this.riderRaf = p < 1 ? requestAnimationFrame(step) : 0;
    };
    this.riderRaf = requestAnimationFrame(step);
  }
}
