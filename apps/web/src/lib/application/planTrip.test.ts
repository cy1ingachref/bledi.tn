import { describe, expect, it } from "vitest";
import { memoryTransit } from "$lib/adapters/memory/memoryTransit";
import type { Endpoint } from "$lib/domain/transit";
import { planTrip, tripProblem } from "./planTrip";

const from: Endpoint = { kind: "stop", name: "Barcelone", lat: 36.79, lon: 10.18 };
const to: Endpoint = { kind: "city", name: "Sousse", lat: 35.83, lon: 10.64 };

describe("tripProblem", () => {
  it("asks for a mode before asking for endpoints", () => {
    expect(tripProblem(new Set(), null, null)).toBe("no_modes");
    expect(tripProblem(new Set(["bus"]), from, null)).toBe("missing_endpoints");
    expect(tripProblem(new Set(["bus"]), from, to)).toBeNull();
  });
});

describe("planTrip", () => {
  it("sends the endpoints and the expanded mode list", async () => {
    const transit = memoryTransit();
    await planTrip(transit, { from, to, selected: new Set(["taxi_louage", "train"]), objective: "fastest" });
    expect(transit.routeQueries).toEqual([
      {
        start: { lat: 36.79, lon: 10.18 },
        end: { lat: 35.83, lon: 10.64 },
        modesInclude: "train,taxi,louaj",
        objective: "fastest",
      },
    ]);
  });
});
