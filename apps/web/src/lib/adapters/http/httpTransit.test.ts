import { describe, expect, it } from "vitest";
import { httpTransit } from "./httpTransit";

function stubFetch(status: number, body: unknown) {
  const urls: string[] = [];
  const fetchFn = async (url: string) => {
    urls.push(url);
    return new Response(JSON.stringify(body), { status });
  };
  return { urls, transit: httpTransit(fetchFn) };
}

describe("httpTransit", () => {
  it("plans a route with the router's query parameters", async () => {
    const { urls, transit } = stubFetch(200, { itineraries: [] });
    await transit.planRoute({
      start: { lat: 36.8, lon: 10.18 },
      end: { lat: 36.85, lon: 10.2 },
      modesInclude: "bus,taxi,louaj",
      objective: "cheapest",
    });
    expect(urls).toEqual([
      "/api/v1/route/plan?start_lat=36.8&start_lon=10.18&end_lat=36.85&end_lon=10.2&modes_include=bus%2Ctaxi%2Clouaj&objective=cheapest",
    ]);
  });

  it("parses station features and drops those without coordinates", async () => {
    const { urls, transit } = stubFetch(200, {
      features: [
        {
          properties: { id: "s1", name: " Barcelone ", mode: "metro", lines: ["m1"] },
          geometry: { coordinates: [10.18, 36.79] },
        },
        { properties: { id: "s2", name: "Nowhere" }, geometry: { coordinates: [0, 0] } },
      ],
      metadata: { count: 1, total: 2, by_mode: { metro: 1 } },
    });
    const { stations, meta } = await transit.stations();
    expect(urls).toEqual(["/api/v1/stations"]);
    expect(stations).toEqual([
      {
        id: "s1", name: "Barcelone", lat: 36.79, lon: 10.18, mode: "metro", modes: ["metro"],
        mode_raw: undefined, operator: undefined, city: undefined, source: undefined, lines_served: ["m1"],
      },
    ]);
    expect(meta.by_mode).toEqual({ metro: 1 });
  });

  it("searches near the start point and encodes station ids", async () => {
    const { urls, transit } = stubFetch(200, { results: [] });
    await transit.searchPlaces("bab saadoun", { lat: 36.8, lon: 10.1 });
    await transit.station("a/b");
    expect(urls).toEqual([
      "/api/v1/search?q=bab+saadoun&near_lat=36.8&near_lon=10.1",
      "/api/v1/stations/a%2Fb",
    ]);
  });

  it("turns an unbuilt overlay into an empty layer with its reason", async () => {
    expect(await stubFetch(503, { detail: "run the build" }).transit.railOverlay()).toEqual({
      features: [],
      error: "run the build",
    });
    expect(await stubFetch(503, {}).transit.roadOverlay()).toEqual({
      features: [],
      error: "road overlay not built",
    });
  });

  it("names the failing path without its query string", async () => {
    const { transit } = stubFetch(500, { error: "internal" });
    await expect(transit.searchPlaces("x", null)).rejects.toThrow("GET /api/v1/search -> 500");
    await expect(transit.network()).rejects.toThrow("GET /api/v1/network -> 500");
    await expect(transit.roadOverlay()).rejects.toThrow("GET /api/v1/map/roads -> 500");
  });
});
