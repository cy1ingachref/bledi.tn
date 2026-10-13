// Theme preference: auto (follow the OS) / light / dark, persisted and applied
// to <html data-theme> so both the component CSS and the global Leaflet rules
// can key off it.
//
// `auto` is the default so the app respects the OS setting out of the box, but
// an explicit choice always wins and is remembered.
import { writable, get } from "svelte/store";

export type ThemePref = "auto" | "light" | "dark";
export type Resolved = "light" | "dark";

const KEY = "bledi_theme";

const mq =
  typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "auto") return v;
  } catch {
    /* private mode / file:// — fall through to auto */
  }
  return "auto";
}

export const themePref = writable<ThemePref>(readPref());
export const resolvedTheme = writable<Resolved>("dark");

/** Collapse a preference into the concrete theme to render. */
export function resolveTheme(p: ThemePref): Resolved {
  if (p === "auto") return mq?.matches ? "dark" : "light";
  return p;
}

/** Push the resolved theme onto <html> and the browser chrome colour. */
export function applyTheme(p: ThemePref): void {
  const r = resolveTheme(p);
  resolvedTheme.set(r);
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = r;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", r === "light" ? "#fbf4e8" : "#0f0b1a");
}

export function setTheme(p: ThemePref): void {
  themePref.set(p);
  try {
    localStorage.setItem(KEY, p);
  } catch {
    /* ignore */
  }
  applyTheme(p);
}

/** Cycle auto -> light -> dark -> auto. */
export function cycleTheme(): void {
  const order: ThemePref[] = ["auto", "light", "dark"];
  const cur = get(themePref);
  setTheme(order[(order.indexOf(cur) + 1) % order.length]);
}

/** True when the user asked the OS to reduce motion. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

let wired = false;

/** Apply the stored theme and follow OS changes while the pref is `auto`. */
export function initTheme(): void {
  applyTheme(get(themePref));
  if (wired) return;
  wired = true;
  mq?.addEventListener?.("change", () => {
    if (get(themePref) === "auto") applyTheme("auto");
  });
}
