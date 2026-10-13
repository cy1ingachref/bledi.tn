import L from "leaflet";
import "leaflet.markercluster";
import { modeKey } from "$lib/domain/modes";
import type { Endpoint, MapOverlayFeature, NetworkSegment, Station } from "$lib/domain/transit";
import { modeColor } from "$lib/ui/modeStyle";
import { prefersReducedMotion, type Resolved } from "$lib/ui/theme";
import { RouteDrawing } from "./routeDrawing";

// Two real basemaps, swapped by theme. Both are Esri's no-key tile services.
const TILES = {
  dark: {
    base: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    ref: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
  },
  light: {
    base: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    ref: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
  },
};
const TILE_ATTR = "Esri, HERE, Garmin, © OpenStreetMap contributors";

/**
 * One canvas pane per network mode, so each transport type can carry its own
 * neon glow (a CSS drop-shadow on that pane's canvas). A single canvas holding
 * every mode could only take one glow colour. Ordered so rail sits above road.
 */
const NET_PANES: { mode: string; z: number }[] = [
  { mode: "bus", z: 380 },
  { mode: "taxi_louage", z: 381 },
  { mode: "tram", z: 382 },
  { mode: "metro", z: 383 },
  { mode: "train", z: 384 },
];

// The physical network, drawn UNDER the per-route network: every motorway,
// trunk and primary road, and every rail/light-rail alignment in the country.
const BASE_PANES: { key: "roads" | "rail"; z: number }[] = [
  { key: "roads", z: 360 },
  { key: "rail", z: 370 },
];

function isRail(mode: string): boolean {
  return mode === "train" || mode === "metro" || mode === "tram";
}

function stationIcon(mode: string) {
  const c = modeColor(mode);
  const dim = modeKey(mode) === "unclassified";
  return L.divIcon({
    className: "",
    html: `<span style="display:block;width:9px;height:9px;border-radius:50%;
      background:${c};border:1.5px solid rgba(3,1,10,.92);
      box-shadow:0 0 0 2px ${c}2e${dim ? "" : `,0 0 7px ${c}99`};"></span>`,
    iconSize: [9, 9],
    iconAnchor: [4.5, 4.5],
  });
}

function endpointIcon(label: string, color: string) {
  return L.divIcon({
    className: "",
    html: `<span style="display:flex;width:30px;height:30px;border-radius:50%;
      align-items:center;justify-content:center;
      background:${color};color:#05020e;font-weight:800;font-size:13px;
      border:2.5px solid #f4f0ff;box-shadow:0 0 14px ${color}cc,0 3px 16px rgba(0,0,0,.8);">${label}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

function setPaneStyle(map: L.Map, name: string, z: number): void {
  map.createPane(name);
  const el = map.getPane(name);
  if (el) { el.style.zIndex = String(z); el.style.pointerEvents = "none"; }
}

/** The Leaflet map behind the planner: basemap, network, stops, endpoints and route. */
export class TransitMap {
  readonly route: RouteDrawing;
  private readonly map: L.Map;
  private readonly baseLayer: L.TileLayer;
  private readonly refLayer: L.TileLayer;
  private readonly stationLayer: L.LayerGroup;
  private readonly netLayers: Record<string, L.LayerGroup> = {};
  private readonly baseLayers: Record<"roads" | "rail", L.LayerGroup>;
  private startMarker: L.Marker | null = null;
  private endMarker: L.Marker | null = null;
  private visibility = { roads: true, rails: true };

  constructor(el: HTMLElement, onClick: (lat: number, lon: number) => void) {
    const map = L.map(el, {
      center: [36.8065, 10.1815],
      zoom: 12,
      zoomControl: false,
      attributionControl: true,
      // Thousands of station markers as SVG would be thousands of DOM nodes.
      preferCanvas: true,
    });
    this.map = map;
    L.control.zoom({ position: "bottomright" }).addTo(map);

    this.baseLayer = L.tileLayer(TILES.dark.base, { maxZoom: 16, attribution: TILE_ATTR }).addTo(map);
    this.refLayer = L.tileLayer(TILES.dark.ref, { maxZoom: 16, pane: "shadowPane" }).addTo(map);

    // The A/B endpoints live above the station markers in their own pane, so
    // dimming the rest of the network in focus mode never dims them.
    setPaneStyle(map, "endpointPane", 660);
    this.route = new RouteDrawing(map);

    for (const p of NET_PANES) {
      setPaneStyle(map, `net_${p.mode}`, p.z);
      this.netLayers[p.mode] = L.layerGroup().addTo(map);
    }
    for (const p of BASE_PANES) setPaneStyle(map, `base_${p.key}`, p.z);
    this.baseLayers = { roads: L.layerGroup().addTo(map), rail: L.layerGroup().addTo(map) };

    this.stationLayer = L.layerGroup().addTo(map);

    map.on("click", (e: L.LeafletMouseEvent) => onClick(e.latlng.lat, e.latlng.lng));
  }

  setBasemap(shade: Resolved): void {
    const which = shade === "light" ? "light" : "dark";
    this.baseLayer.setUrl(TILES[which].base);
    this.refLayer.setUrl(TILES[which].ref);
  }

  drawNetwork(network: NetworkSegment[]): void {
    for (const p of NET_PANES) this.netLayers[p.mode]?.clearLayers();

    const byMode: Record<string, NetworkSegment[]> = {};
    for (const seg of network) {
      if (!seg.has_geometry || seg.geometry.length < 2) continue;
      const k = modeKey(seg.mode);
      if (!(k in this.netLayers)) continue;
      (byMode[k] ??= []).push(seg);
    }

    for (const [mode, segs] of Object.entries(byMode)) {
      const layer = this.netLayers[mode];
      const renderer = L.canvas({ padding: 0.5, pane: `net_${mode}` });
      const rail = isRail(mode);
      for (const seg of segs) {
        L.polyline(seg.geometry, {
          color: modeColor(mode),
          weight: rail ? 2.4 : 1.7,
          opacity: rail ? 0.8 : 0.5,
          lineCap: "round",
          lineJoin: "round",
          interactive: false,
          renderer,
        }).addTo(layer);
      }
    }
  }

  setNetworkVisibility(roads: boolean, rails: boolean): void {
    this.visibility = { roads, rails };
    for (const p of NET_PANES) {
      const el = this.map.getPane(`net_${p.mode}`);
      if (el) el.style.display = (isRail(p.mode) ? rails : roads) ? "" : "none";
    }
    for (const p of BASE_PANES) {
      const el = this.map.getPane(`base_${p.key}`);
      if (el) el.style.display = (p.key === "rail" ? rails : roads) ? "" : "none";
    }
  }

  /**
   * The country's rail and road alignments, styled quieter than the route
   * network because they are context, not the answer. Rail is coloured by
   * mode so light rail reads differently from mainline; roads are one muted
   * grey so the road numbers stay legible.
   */
  drawBaseLayers(rail: MapOverlayFeature[], roads: MapOverlayFeature[]): void {
    this.baseLayers.rail.clearLayers();
    this.baseLayers.roads.clearLayers();

    const railRenderer = L.canvas({ padding: 0.5, pane: "base_rail" });
    for (const f of rail) {
      if (!f.geometry || f.geometry.length < 2) continue;
      const isMetro = (f.properties?.mode ?? "") === "metro";
      L.polyline(f.geometry, {
        color: isMetro ? modeColor("metro") : modeColor("train"),
        weight: isMetro ? 1.9 : 2.3,
        opacity: isMetro ? 0.6 : 0.72,
        lineCap: "round",
        lineJoin: "round",
        interactive: false,
        renderer: railRenderer,
      }).addTo(this.baseLayers.rail);
    }

    const roadRenderer = L.canvas({ padding: 0.5, pane: "base_roads" });
    for (const f of roads) {
      if (!f.geometry || f.geometry.length < 2) continue;
      const hw = f.properties?.highway ?? "";
      L.polyline(f.geometry, {
        color: "#6b6f8a",
        weight: hw === "motorway" ? 1.9 : hw === "trunk" ? 1.5 : 1.1,
        opacity: hw === "primary" ? 0.3 : 0.42,
        lineCap: "round",
        lineJoin: "round",
        interactive: false,
        renderer: roadRenderer,
      }).addTo(this.baseLayers.roads);
    }
    this.setNetworkVisibility(this.visibility.roads, this.visibility.rails);
  }

  /**
   * Every stop goes into a marker cluster. A silent stride (drawing every Nth
   * marker) makes a large dataset render identically to a small one, so all of
   * them are added and clustering keeps the DOM cost down.
   */
  drawStations(stations: Station[], label: (mode: string) => string, onClick: (s: Station) => void): void {
    this.stationLayer.clearLayers();
    const cluster = L.markerClusterGroup({
      maxClusterRadius: 55,
      disableClusteringAtZoom: 15,
      showCoverageOnHover: false,
      chunkedLoading: true,
      chunkInterval: 120,
      iconCreateFunction: (c) => {
        const n = c.getChildCount();
        const size = n < 10 ? "small" : n < 100 ? "medium" : "large";
        const reduced = prefersReducedMotion();
        return L.divIcon({
          html: `<div class="bl-cluster ${reduced ? "no-pulse" : ""}"><span class="bl-halo"></span><span class="bl-n">${n}</span></div>`,
          className: `marker-cluster marker-cluster-${size}`,
          iconSize: L.point(40, 40),
        });
      },
    });

    const markers: L.Marker[] = [];
    for (const s of stations) {
      const mk = L.marker([s.lat, s.lon], { icon: stationIcon(s.mode), title: s.name })
        .bindTooltip(`<b>${s.name}</b><span class="tt-sub">${label(s.mode)}</span>`, {
          direction: "top",
          offset: [0, -7],
        })
        .on("click", () => onClick(s));
      markers.push(mk);
    }
    cluster.addLayers(markers);
    this.stationLayer.addLayer(cluster);
  }

  placeEndpoints(from: Endpoint | null, to: Endpoint | null, labels: { from: string; to: string }): void {
    if (this.startMarker) { this.map.removeLayer(this.startMarker); this.startMarker = null; }
    if (this.endMarker) { this.map.removeLayer(this.endMarker); this.endMarker = null; }
    if (from)
      this.startMarker = L.marker([from.lat, from.lon], {
        icon: endpointIcon("A", "#22d3ee"),
        pane: "endpointPane",
        interactive: false,
      })
        .bindTooltip(labels.from, { direction: "top" })
        .addTo(this.map);
    if (to)
      this.endMarker = L.marker([to.lat, to.lon], {
        icon: endpointIcon("B", "#f472b6"),
        pane: "endpointPane",
        interactive: false,
      })
        .bindTooltip(labels.to, { direction: "top" })
        .addTo(this.map);
  }

  /** Centre on a point without zooming out past `minZoom`. */
  focus(lat: number, lon: number, minZoom: number): void {
    this.map.setView([lat, lon], Math.max(this.map.getZoom(), minZoom));
  }

  destroy(): void {
    this.route.stopRider();
    this.map.remove();
  }
}
