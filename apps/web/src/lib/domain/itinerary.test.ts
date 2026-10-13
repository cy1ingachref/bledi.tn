import { describe, expect, it } from "vitest";
import { fareOf, lineNumber, mergeLegs } from "./itinerary";
import type { Itinerary, RouteLeg } from "./transit";

describe("mergeLegs", () => {
  it("collapses consecutive hops on the same line", () => {
    const legs: RouteLeg[] = [
      { type: "ride", mode: "bus", line: "bus_75", duration_min: 3, to_name: "B" },
      { type: "ride", mode: "bus", line: "bus_75", duration_min: 4, to_name: "C" },
      { type: "ride", mode: "metro", line: "metro_1", duration_min: 5, to_name: "D" },
    ];
    expect(mergeLegs(legs)).toEqual([
      { type: "ride", mode: "bus", line: "bus_75", duration_min: 7, to_name: "C" },
      { type: "ride", mode: "metro", line: "metro_1", duration_min: 5, to_name: "D" },
    ]);
  });

  it("never merges walks and leaves the input untouched", () => {
    const legs: RouteLeg[] = [
      { type: "walk", duration_min: 2 },
      { type: "Walk", duration_min: 3 },
    ];
    expect(mergeLegs(legs)).toHaveLength(2);
    const rides: RouteLeg[] = [
      { mode: "bus", line: "x", duration_min: 1 },
      { mode: "bus", line: "x", duration_min: 1 },
    ];
    mergeLegs(rides);
    expect(rides[0].duration_min).toBe(1);
  });
});

describe("fareOf", () => {
  const itin = (extra: Partial<Itinerary>): Itinerary => ({
    id: "1", label: "", duration_min: 10, transfers: 0, fare_dinars: 0.5, modes_used: [], legs: [], ...extra,
  });

  it("prefers the estimate when the API sends it", () => {
    expect(fareOf(itin({ fare_estimate_dinars: 1.2 }))).toBe(1.2);
    expect(fareOf(itin({}))).toBe(0.5);
  });
});

describe("lineNumber", () => {
  it("extracts the rider-facing number", () => {
    expect(lineNumber("rail_19_a")).toBe("19");
    expect(lineNumber("bus_32b")).toBe("32b");
    expect(lineNumber("tgm")).toBeNull();
    expect(lineNumber(undefined)).toBeNull();
  });
});
