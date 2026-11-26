import { useEffect, useRef, useState } from "react";
import * as ml from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { LogoControl } from "@maptoolkit/maplibre-logo-control";
import "@maptoolkit/maplibre-logo-control/style.css";
import { setupMapLibreWorker } from "../maplibre/setup";
import { TGM, type Place } from "../data";
import { linePathRuns, type LineDetail } from "../catalog";
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

// Maptoolkit Dark is free and needs no API key; their terms require the
// LogoControl below plus the attribution its `mtk` source already carries.
const STYLE = "https://styles.maptoolkit.org/dark.json";
const SOURCES = ["ctx", "track", "stops", "route", "walks", "route-stops"];
const EMPTY = { type: "FeatureCollection" as const, features: [] };

type LL = [number, number];
const xy = ([lat, lon]: LL): [number, number] => [lon, lat];
const ok = ([lat, lon]: LL) => Number.isFinite(lat) && Number.isFinite(lon);

const lineFC = (paths: LL[][], props: Record<string, unknown> = {}) => ({
  type: "FeatureCollection" as const,
  features: paths.filter((p) => p.length > 1).map((path) => ({
    type: "Feature" as const,
    properties: props,
    geometry: { type: "LineString" as const, coordinates: path.filter(ok).map(xy) },
  })),
});

const pointFC = (pts: { pos: LL; label?: string; main?: boolean; color?: string }[]) => ({
  type: "FeatureCollection" as const,
  features: pts.filter((pt) => ok(pt.pos)).map((pt) => ({
    type: "Feature" as const,
    properties: { label: pt.label ?? "", main: pt.main ?? false, color: pt.color ?? "#1f6f8b" },
    geometry: { type: "Point" as const, coordinates: xy(pt.pos) },
  })),
});

const addLine = (m: ml.Map, id: string, source: string, paint: Record<string, unknown>) =>
  m.addLayer({
    id, type: "line", source,
    layout: { "line-cap": "round", "line-join": "round" },
    paint,
  } as never);

let liveMap: ml.Map | null = null; // App.tsx's zoom buttons drive this handle

export default function MapView({ from, to, route, isMobile, sidebarWidth, sheetHeight, line }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<ml.Map | null>(null);
  const readyRef = useRef(false);
  const markers = useRef<ml.Marker[]>([]);
  const [ready, setReady] = useState(false);

  // Held in a ref so the mount effect never re-subscribes when props change.
  const draw = useRef<() => void>(() => {});
  draw.current = () => {
    const m = mapRef.current;
    if (!m || !readyRef.current) return;
    const set = (id: string, data: unknown) =>
      (m.getSource(id) as ml.GeoJSONSource | undefined)?.setData(data as never);

    // Compute the line geometry once and use it for both the source and the fit.
    const runs = line ? linePathRuns(line) : [];
    const stops = line
      ? line.stops
          .filter((s) => s.lat !== null && s.lon !== null)
          .map((s, i) => ({
            pos: [s.lat as number, s.lon as number] as LL,
            label: `${i + 1}. ${s.name || s.stop_id}`,
            main: i === 0 || i === line.stops.length - 1,
          }))
      : [];

    // A selected line and a planned route are mutually exclusive: drawing both
    // would put route dots on stations that are not on the shown line.
    set("ctx", line ? EMPTY : lineFC([TGM.map((s) => s.pos)]));
    set("track", line ? lineFC(runs) : EMPTY);
    set("stops", line ? pointFC(stops) : EMPTY);
    set("route", !line && route ? lineFC([route.path], { color: route.color }) : EMPTY);
    set("walks", !line && route ? lineFC(route.walkPaths) : EMPTY);
    set("route-stops", !line && route
      ? pointFC(route.stopsOnPath.slice(1, -1).map((pos) => ({ pos, color: route.color })))
      : EMPTY);

    // Reuse the app's existing .pin styling for the two endpoints.
    markers.current.forEach((mk) => mk.remove());
    markers.current = [];
    for (const [place, label, color] of [
      [from, "A", "#1f6f8b"],
      [to, "B", "#e03131"],
    ] as const) {
      if (!place) continue;
      const node = document.createElement("div");
      node.innerHTML = `<div class="pin" style="--c:${color}"><span></span><b>${label}</b></div>`;
      node.title = place.fr;
      markers.current.push(
        new ml.Marker({ element: node, anchor: "center" }).setLngLat(xy(place.pos)).addTo(m)
      );
    }

    const pts = [
      ...(from ? [from.pos] : []),
      ...(to ? [to.pos] : []),
      ...(route?.path ?? []),
      ...runs.flat(),
      ...stops.map((s) => s.pos),
    ].filter(ok);
    if (!pts.length) return;
    const b = pts.reduce<[number, number, number, number]>(
      (a, [lat, lon]) => [Math.min(a[0], lon), Math.min(a[1], lat), Math.max(a[2], lon), Math.max(a[3], lat)],
      [Infinity, Infinity, -Infinity, -Infinity]
    );
    m.fitBounds([[b[0], b[1]], [b[2], b[3]]], {
      padding: isMobile
        ? { top: 80, bottom: sheetHeight + 30, left: 30, right: 30 }
        : { top: 60, bottom: 60, left: sidebarWidth + 60, right: 60 },
      duration: 800,
      maxZoom: 15,
    });
  };

  useEffect(() => {
    if (!el.current || mapRef.current) return;
    setupMapLibreWorker();
    const m = new ml.Map({
      container: el.current, style: STYLE,
      center: [10.25, 36.83], zoom: 12, attributionControl: { compact: true },
    });
    m.addControl(new LogoControl({ variant: "com" }), "bottom-left");
    mapRef.current = m;
    liveMap = m;
    (window as unknown as { __map: ml.Map }).__map = m;

    const install = () => {
      if (readyRef.current) return;
      SOURCES.forEach((id) => m.addSource(id, { type: "geojson", data: EMPTY as never }));

      addLine(m, "ctx-line", "ctx", {
        "line-color": "#8fc4d8", "line-width": 2, "line-opacity": 0.35, "line-dasharray": [2, 3],
      });
      addLine(m, "track-casing", "track", { "line-color": "#fff", "line-width": 9, "line-opacity": 0.85 });
      addLine(m, "track-core", "track", { "line-color": "#38bdf8", "line-width": 5 });
      addLine(m, "route-casing", "route", { "line-color": "#fff", "line-width": 10, "line-opacity": 0.9 });
      addLine(m, "route-core", "route", {
        "line-color": ["coalesce", ["get", "color"], "#1f6f8b"], "line-width": 6,
      });
      addLine(m, "route-flow", "route", {
        "line-color": "#fff", "line-width": 2, "line-opacity": 0.75, "line-dasharray": [0.1, 3],
      });
      addLine(m, "walk-line", "walks", {
        "line-color": "#cbd5e1", "line-width": 4, "line-dasharray": [1, 2],
      });

      m.addLayer({
        id: "stops-dots", type: "circle", source: "stops",
        paint: {
          "circle-radius": ["case", ["get", "main"], 7, 5],
          "circle-color": "#38bdf8", "circle-stroke-color": "#0b1220", "circle-stroke-width": 2.5,
        },
      } as never);
      m.addLayer({
        id: "route-stops-dots", type: "circle", source: "route-stops",
        paint: {
          "circle-radius": 4, "circle-color": "#fff",
          "circle-stroke-color": ["coalesce", ["get", "color"], "#1f6f8b"], "circle-stroke-width": 2.5,
        },
      } as never);

      m.on("click", "stops-dots", (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const [lon, lat] = (f.geometry as { coordinates: number[] }).coordinates;
        new ml.Popup({ closeButton: false }).setLngLat([lon, lat])
          .setText(String(f.properties?.label ?? "")).addTo(m);
      });
      m.on("mouseenter", "stops-dots", () => (m.getCanvas().style.cursor = "pointer"));
      m.on("mouseleave", "stops-dots", () => (m.getCanvas().style.cursor = ""));

      readyRef.current = true;
      setReady(true);
    };

    m.on("load", install);
    m.on("error", (e) => console.warn("MapLibre map error:", e.error?.message ?? e));
    return () => {
      m.off("load", install);
      markers.current.forEach((mk) => mk.remove());
      markers.current = [];
      m.remove();
      mapRef.current = null;
      liveMap = null;
      readyRef.current = false;
      setReady(false);
    };
  }, []);

  useEffect(() => { if (ready) draw.current(); },
    [from, to, route, line, isMobile, sidebarWidth, sheetHeight, ready]);

  return <div ref={el} className="map-root absolute inset-0 z-0" />;
}

export function zoom(d: 1 | -1) {
  if (liveMap) liveMap.easeTo({ zoom: liveMap.getZoom() + d, duration: 250 });
}
