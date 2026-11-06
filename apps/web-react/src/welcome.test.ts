import { describe, expect, it } from "vitest";
import { T } from "./i18n";
import type { Lang } from "./i18n";

const LANGS: Lang[] = ["fr", "ar", "en"];

describe("welcome state", () => {
  it("has a welcome title and hint in every language", () => {
    for (const l of LANGS) {
      expect(T[l].welcomeTitle, `${l}.welcomeTitle`).toBeTruthy();
      expect(T[l].welcomeHint, `${l}.welcomeHint`).toBeTruthy();
    }
  });

  it("replaces the localized welcome word with Marahbe bik", () => {
    // The requested greeting is the same transliteration in French and English.
    expect(T.fr.welcomeTitle).toBe("Marahbe bik");
    expect(T.en.welcomeTitle).toBe("Marahbe bik");
  });

  it("greets in Arabic, including when the UI language is Arabic", () => {
    // The greeting is the product's signature; it must be Arabic.
    expect(T.ar.welcomeTitle).toBe("مرحبا بيك");
    expect(T.ar.marahba).toContain("مرحبا");
  });

  it("keeps the marahba key as the Latin greeting in Latin locales", () => {
    // The badge alternates, so the Latin word must stay Latin.
    expect(T.fr.marahba).toBe("Marahbe bik");
    expect(T.en.marahba).toBe("Marahbe bik");
  });

  it("has distinct placeholders for departure and arrival", () => {
    for (const l of LANGS) {
      expect(T[l].pickFrom, `${l}.pickFrom`).toBeTruthy();
      expect(T[l].pickTo, `${l}.pickTo`).toBeTruthy();
      expect(T[l].pickFrom).not.toBe(T[l].pickTo);
    }
  });

  it("does not reuse the empty-state message as the placeholder", () => {
    // `same` is shown when a route search returns nothing; placeholders must be
    // their own strings so the two states read differently.
    for (const l of LANGS) {
      expect(T[l].pickFrom).not.toBe(T[l].same);
      expect(T[l].pickTo).not.toBe(T[l].same);
    }
  });
});
