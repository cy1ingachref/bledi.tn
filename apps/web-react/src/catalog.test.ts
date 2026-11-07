import { describe, expect, it } from "vitest";
import { T } from "./i18n";

/**
 * The line catalog screen: every locale must carry the keys the catalog reads,
 * in all three languages, or the UI falls back to a raw key name.
 */
const REQUIRED = [
  "lineCatalog",
  "allLines",
  "lineCatalogHint",
  "back",
  "searchLine",
  "loading",
  "noLines",
  "pickLine",
  "showOnMap",
  "geometryComplete",
  "geometryGaps",
  "stopsWithoutCoords",
  "station",
  "location",
  "otherLines",
  "noLocation",
  "noTrack",
  "stopsWord",
  "modeMetro",
  "modeRail",
  "noStops",
  "noStopsShort",
  "hiddenEmptyLines",
];

describe("line catalog i18n", () => {
  it("has every catalog key in every locale", () => {
    for (const lang of ["fr", "ar", "en"] as const) {
      for (const k of REQUIRED) {
        expect(T[lang][k as keyof typeof T.fr], `${lang}.${k}`).toBeTruthy();
      }
    }
  });

  it("keeps the mode names distinct from the generic ones", () => {
    // Metro and suburban rail are separate modes in the seed and must not
    // collapse into the train label.
    expect(T.fr.modeMetro).toBe("Métro");
    expect(T.fr.modeRail).toBe("Train de banlieue");
    expect(T.ar.modeMetro).toBe("مترو");
    expect(T.en.modeRail).toBe("Suburban rail");
  });

  it("uses a real sentence for the empty-lines note", () => {
    // The note interpolates a count; it must carry the placeholder.
    expect(T.fr.hiddenEmptyLines).toContain("{n}");
    expect(T.ar.hiddenEmptyLines).toContain("{n}");
    expect(T.en.hiddenEmptyLines).toContain("{n}");
  });
});
