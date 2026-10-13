import { describe, expect, it } from "vitest";
import { memoryTransit } from "$lib/adapters/memory/memoryTransit";
import { loadBaseLayers, loadLouageLinks, louageDestinations } from "./mapData";

const link = (from: string, to: string) => ({ from, to, from_name: from, to_name: to, destination_raw: to });

describe("loadBaseLayers", () => {
  it("keeps the built overlay when the other was never built", async () => {
    const road = { kind: "road" as const, properties: { highway: "trunk" }, geometry: [] };
    const transit = memoryTransit({
      rail: { features: [], error: "rail overlay not built" },
      roads: { features: [road] },
    });
    expect(await loadBaseLayers(transit)).toEqual({ rail: [], roads: [road] });
  });

  it("comes back empty instead of throwing", async () => {
    const transit = memoryTransit();
    transit.railOverlay = async () => {
      throw new Error("GET /api/v1/map/rail -> 500");
    };
    expect(await loadBaseLayers(transit)).toEqual({ rail: [], roads: [] });
  });
});

describe("loadLouageLinks", () => {
  it("comes back empty instead of throwing", async () => {
    const transit = memoryTransit();
    transit.louageLinks = async () => {
      throw new Error("down");
    };
    expect(await loadLouageLinks(transit)).toEqual([]);
  });
});

describe("louageDestinations", () => {
  it("lists the places a terminal serves", () => {
    const links = [link("a", "b"), link("b", "a"), link("a", "c")];
    expect(louageDestinations(links, "a").map((l) => l.to)).toEqual(["b", "c"]);
  });
});
