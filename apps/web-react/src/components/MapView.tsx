import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { TGM, type Place } from "../data";
import type { LineDetail } from "../catalog";
import { linePathRuns } from "../catalog";
import type { RouteOption } from "../routing";

interface Props {
  from: Place | null;
  to: Place | null;
  route?: RouteOption;
  isMobile: boolean;
  sidebarWidth: number;
  sheetHeight: number;
  dark: boolean;
  /** Line catalog selection: its stops and track, drawn instead of a planned route. */
  line?: LineDetail | null;
}

// OpenStreetMap standard tiles for both themes. OSM's tile-usage policy requires
// an honest User-Agent and a Referer, which Leaflet sends automatically; the
// earlier 403s were from curl, not from a browser. A CSS filter supplies the
// night look (see index.css) because OSM ships no dark variant.
const TILES = {
  light: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  dark: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
};
const ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const pin = (color: string, label: string) =>
  L.divIcon({
    className: "",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html: `<div class="pin" style="--c:${color}"><span></span><b>${label}</b></div>`,
  });

export default function MapView({ from, to, route, isMobile, sidebarWidth, sheetHeight, dark, line }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const tiles = useRef<L.TileLayer | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  // The map is created in an effect, so later effects wait for this flag.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { zoomControl: false, attributionControl: true }).setView([36.83, 10.25], 12);
    m.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    (window as unknown as { __map: L.Map }).__map = m;
    setReady(true);
    return () => {
      m.remove();
      map.current = null;
      setReady(false);
    };
  }, []);

  // tiles
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    tiles.current?.remove();
    const t = L.tileLayer(TILES.light, {
      attribution: ATTR,
      maxZoom: 19,
      detectRetina: false,
    });
    t.addTo(m);
    tiles.current = t;
  }, [ready]);

  // route drawing
  useEffect(() => {
    const m = map.current;
    const g = layer.current;
    if (!m || !g) return;
    g.clearLayers();

    // context: whole TGM line, faint
    L.polyline(
      TGM.map((s) => s.pos),
      { color: dark ? "#5b8fa3" : "#1f6f8b", weight: 3, opacity: 0.18, dashArray: "2 6" }
    ).addTo(g);

    // Line catalog selection: the line's real track and every stop it calls at.
    if (line) {
      const color = dark ? "#38bdf8" : "#0284c7";
      // Draw per continuous run: a line with a missing middle (deep-south SNCFT,
      // where OSM has no track at all) still shows its real rails either side.
      const runs = linePathRuns(line);
      runs.forEach((path) => {
        if (path.length < 2) return;
        L.polyline(path, { color: dark ? "#0b1220" : "#ffffff", weight: 9, opacity: 0.85, lineCap: "round", lineJoin: "round" }).addTo(g);
        L.polyline(path, { color, weight: 5, lineCap: "round", lineJoin: "round" }).addTo(g);
      });
      // Stops: numbered in travel order so the table and the map agree.
      line.stops.forEach((s, i) => {
        if (s.lat === null || s.lon === null) return;
        const pos: [number, number] = [s.lat, s.lon];
        const first = i === 0;
        const last = i === line.stops.length - 1;
        L.circleMarker(pos, {
          radius: first || last ? 7 : 5,
          color,
          weight: 2.5,
          fillColor: first || last ? color : "#fff",
          fillOpacity: 1,
        })
          .bindTooltip(`${i + 1}. ${s.name || s.stop_id}`, { direction: "top", offset: [0, -8], className: "stop-tip" })
          .addTo(g);
      });
      // Stops with no coordinates are listed in the table but cannot be drawn.
    } else if (route) {
      L.polyline(route.path, { color: dark ? "#0b1220" : "#ffffff", weight: 10, opacity: 0.9, lineCap: "round", lineJoin: "round" }).addTo(g);
      L.polyline(route.path, { color: route.color, weight: 6, lineCap: "round", lineJoin: "round" }).addTo(g);
      L.polyline(route.path, { color: "#ffffff", weight: 2, opacity: 0.75, dashArray: "1 14", className: "flow" }).addTo(g);
      route.walkPaths.forEach((p) =>
        L.polyline(p, { color: dark ? "#cbd5e1" : "#475569", weight: 4, dashArray: "1 8", lineCap: "round" }).addTo(g)
      );
      route.stopsOnPath.slice(1, -1).forEach((p) =>
        L.circleMarker(p, { radius: 4, color: route.color, weight: 2.5, fillColor: "#fff", fillOpacity: 1 }).addTo(g)
      );
      if (route.id === "tgm") {
        TGM.filter((s) => route.stopsOnPath.some((p) => p[0] === s.pos[0])).forEach((s) =>
          L.circleMarker(s.pos, { radius: 0, opacity: 0 })
            .bindTooltip(s.fr, { direction: "right", className: "stop-tip", offset: [6, 0] })
            .addTo(g)
        );
      }
    }

    // Markers only make sense for places that exist yet.
    if (from) {
      L.marker(from.pos, { icon: pin("#1f6f8b", "A"), zIndexOffset: 1000 }).bindTooltip(from.fr, { direction: "top", offset: [0, -14] }).addTo(g);
    }
    if (to) {
      L.marker(to.pos, { icon: pin("#e03131", "B"), zIndexOffset: 1000 }).bindTooltip(to.fr, { direction: "top", offset: [0, -14] }).addTo(g);
    }

    // No endpoints chosen: leave the default view alone instead of fitting
    // bounds around an empty set.
    const linePts = line
      ? [
          ...linePathRuns(line).flat(),
          ...line.stops
            .filter((s) => s.lat !== null && s.lon !== null)
            .map((s) => [s.lat as number, s.lon as number] as [number, number]),
        ]
      : [];
    const pts = [from?.pos, to?.pos, ...(route?.path ?? []), ...linePts].filter(Boolean) as [number, number][];
    if (!pts.length) return;
    const bounds = L.latLngBounds(pts);
    m.flyToBounds(bounds, {
      paddingTopLeft: isMobile ? [30, 80] : [sidebarWidth + 60, 60],
      paddingBottomRight: isMobile ? [30, sheetHeight + 30] : [60, 60],
      duration: 0.8,
      maxZoom: 15,
    });
  }, [from, to, route, isMobile, sidebarWidth, sheetHeight, dark, line]);

  return <div ref={el} className="absolute inset-0 z-0" />;
}

export function zoom(d: 1 | -1) {
  const m = (window as unknown as { __map?: L.Map }).__map;
  if (m) d > 0 ? m.zoomIn() : m.zoomOut();
}
