import { describe, expect, it } from "vitest";
import {
  defaultSelection,
  isStationShown,
  modeKey,
  modesInclude,
  servedModes,
  uniqueModes,
} from "./modes";
import type { Station } from "./transit";

describe("modeKey", () => {
  it("folds every taxi and louage variant into one category", () => {
    for (const raw of ["taxi", "louaj", "louage", "louage_red", "louage_blue", "louage_green"]) {
      expect(modeKey(raw)).toBe("taxi_louage");
    }
  });

  it("keeps unclassified apart and defaults unknown modes to bus", () => {
    expect(modeKey("unclassified")).toBe("unclassified");
    expect(modeKey("rfr")).toBe("bus");
    expect(modeKey("metro")).toBe("metro");
  });
});

describe("modesInclude", () => {
  it("expands taxi_louage to both raw modes, in display order", () => {
    expect(modesInclude(new Set(["taxi_louage", "bus", "walk"]))).toBe("bus,taxi,louaj,walk");
  });

  it("ignores ids that are not categories", () => {
    expect(modesInclude(new Set(["unclassified"]))).toBe("");
  });
});

describe("servedModes", () => {
  it("offers only served categories, plus walking", () => {
    expect(servedModes({ bus: 10, louaj: 2, taxi: 3, unclassified: 76, tram: 0 })).toEqual([
      { id: "bus", count: 10 },
      { id: "taxi_louage", count: 5 },
      { id: "walk", count: 0 },
    ]);
  });
});

describe("defaultSelection", () => {
  it("keeps the scheduled modes the inventory has", () => {
    expect([...defaultSelection({ bus: 4, train: 1, metro: 0, louaj: 9 })]).toEqual(["bus", "train"]);
  });
});

describe("uniqueModes", () => {
  it("dedupes raw modes into display order", () => {
    expect(uniqueModes(["walk", "louaj", "bus", "taxi", "bus"])).toEqual(["bus", "taxi_louage", "walk"]);
  });
});

describe("isStationShown", () => {
  const station = (mode: string): Station => ({ id: "s", name: "S", lat: 36.8, lon: 10.1, mode, modes: [mode] });

  it("shows unclassified stops only when asked", () => {
    expect(isStationShown(station("unclassified"), new Set(["bus"]), false)).toBe(false);
    expect(isStationShown(station("unclassified"), new Set(), true)).toBe(true);
  });

  it("follows the selected category", () => {
    expect(isStationShown(station("louaj"), new Set(["taxi_louage"]), false)).toBe(true);
    expect(isStationShown(station("metro"), new Set(["bus"]), false)).toBe(false);
  });
});
