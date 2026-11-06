import { describe, expect, it } from "vitest";
import { cardLabel, formatDuration, formatDurationShort, modeWord } from "./labels";
import { T } from "./i18n";
import type { Lang } from "./i18n";
import type { Mode } from "./routing";

const LANGS: Lang[] = ["fr", "ar", "en"];

describe("i18n dictionaries", () => {
  it("have identical keys in every language", () => {
    // A missing key renders as `undefined` in the UI, so parity is the guard.
    const keySets = LANGS.map((l) => new Set(Object.keys(T[l])));
    for (const [i, keys] of keySets.entries()) {
      expect([...keys].sort(), `keys for ${LANGS[i]}`).toEqual([...keySets[0]].sort());
    }
  });

  it("have no empty translations", () => {
    for (const lang of LANGS) {
      for (const [k, v] of Object.entries(T[lang])) {
        expect(v.trim(), `${lang}.${k}`).not.toBe("");
      }
    }
  });
});

describe("cardLabel", () => {
  it("localizes the mode word the API sends in Latin", () => {
    expect(cardLabel({ id: "bus", line: "Bus · 1 h 38 · direct" }, "ar")).toBe("حافلة · 1 h 38 · مباشر");
    expect(cardLabel({ id: "train", line: "Train · 10 h 51 · direct" }, "ar")).toBe("قطار · 10 h 51 · مباشر");
    expect(cardLabel({ id: "bus", line: "Bus · 1 h 38 · direct" }, "en")).toBe("Bus · 1 h 38 · direct");
    expect(cardLabel({ id: "bus", line: "Bus · 1 h 38 · direct" }, "fr")).toBe("Bus · 1 h 38 · direct");
  });

  it("labels walking without inventing a line", () => {
    expect(cardLabel({ id: "walk", line: "Marche · 14 h 02 · direct" }, "ar")).toBe("مشي · مباشر");
    expect(cardLabel({ id: "walk", line: "Marche · 14 h 02 · direct" }, "en")).toBe("Walk · direct");
    expect(cardLabel({ id: "walk", line: "Marche · 14 h 02 · direct" }, "fr")).toBe("Marche · direct");
  });

  it("survives a missing or already-localized line", () => {
    expect(cardLabel({ id: "bus", line: "" }, "ar")).toBe("حافلة · مباشر");
    // An Arabic line must not be double-prefixed with a Latin mode word.
    expect(cardLabel({ id: "bus", line: "حافلة · 1 h 38" }, "ar")).toBe("حافلة · 1 h 38 · مباشر");
  });
});

describe("modeWord", () => {
  it("returns the LED badge word per language", () => {
    expect(modeWord("bus", "ar")).toBe("حافلة");
    expect(modeWord("train", "ar")).toBe("قطار");
    expect(modeWord("walk", "ar")).toBe("مشي");
    expect(modeWord("louage", "ar")).toBe("لواج");
    expect(modeWord("taxi", "ar")).toBe("تاكسي");
    expect(modeWord("tgm", "ar")).toBe("TGM");
  });

  it("falls back to Latin for non-Arabic", () => {
    expect(modeWord("bus", "en")).toBe("Bus");
    expect(modeWord("walk", "fr")).toBe("Marche");
  });

  it("covers every Mode the router can emit", () => {
    const modes: Mode[] = ["tgm", "bus", "train", "louage", "taxi", "walk"];
    for (const m of modes) {
      for (const lang of LANGS) {
        expect(modeWord(m, lang), `${m}/${lang}`).not.toBe("");
      }
    }
  });
});


describe("duration formatting", () => {
  it("stays in minutes below one hour", () => {
    expect(formatDuration(0, "fr")).toBe("0 min");
    expect(formatDuration(59, "fr")).toBe("59 min");
    expect(formatDuration(58, "en")).toBe("58 min");
    expect(formatDuration(58, "ar")).toBe("58 دق");
    expect(formatDurationShort(59, "fr")).toBe("59 min");
  });

  it("shows hours and the remaining minutes once the duration reaches an hour", () => {
    expect(formatDuration(60, "fr")).toBe("1 h");
    expect(formatDuration(98, "fr")).toBe("1 h 38 min");
    expect(formatDuration(120, "ar")).toBe("2 س");
    expect(formatDuration(651, "ar")).toBe("10 س 51 دق");
    expect(formatDuration(651, "en")).toBe("10 h 51 min");
  });

  it("uses the compact form when the locale omits unit words", () => {
    expect(formatDurationShort(98, "fr")).toBe("1 h 38");
    expect(formatDurationShort(120, "fr")).toBe("2 h");
    expect(formatDurationShort(60, "fr")).toBe("1 h");
    expect(formatDurationShort(125, "fr")).toBe("2 h 05");
  });

  it("rounds and clamps malformed durations", () => {
    expect(formatDuration(59.6, "en")).toBe("1 h");
    expect(formatDuration(-5, "fr")).toBe("0 min");
  });
});
