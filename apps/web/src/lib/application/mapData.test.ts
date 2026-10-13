import { describe, expect, it } from "vitest";
import { memoryTransit } from "$lib/adapters/memory/memoryTransit";
import { loadBaseLayers, loadLouageLinks, louageDestinations } from "./mapData";

const link = (from: string, to: string) => ({ from, to, from_name: from, to_name: to, destination_raw: to });

describe("loadBaseLayers", () => {
  it("reports an unbuilt overlay and keeps the other", async () => {
    const road = { kind: "road" as const, properties: { highway: "trunk" }, geometry: [] };
    const transit = memoryTransit({
      rail: { features: [], error: "rail overlay not built" },
      roads: { features: [road] },
    });
    expect(await loadBaseLayers(transit)).toEqual({
      rail: [],
      roads: [road],
      problems: ["rail: rail overlay not built"],
    });
  });

  it("reports a failed request instead of throwing", async () => {
    const transit = memoryTransit();
    transit.railOverlay = async () => {
      throw new Error("GET /api/v1/map/rail -> 500");
    };
    expect(await loadBaseLayers(transit)).toEqual({
      rail: [],
      roads: [],
      problems: ["GET /api/v1/map/rail -> 500"],
    });
  });
});

describe("loadLouageLinks", () => {
  it("prefixes a failure with its source", async () => {
    const transit = memoryTransit();
    transit.louageLinks = async () => {
      throw new Error("down");
    };
    expect(await loadLouageLinks(transit)).toEqual({ links: [], problems: ["louage: down"] });
  });
});

describe("louageDestinations", () => {
  it("lists the places a terminal serves", () => {
    const links = [link("a", "b"), link("b", "a"), link("a", "c")];
    expect(louageDestinations(links, "a").map((l) => l.to)).toEqual(["b", "c"]);
  });
});
