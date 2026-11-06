import type { Lang } from "./i18n";
import { T, fmt } from "./i18n";
import type { Mode, RouteOption } from "./routing";

/** Latin mode words the API prefixes to `route.line`; stripped before re-labeling. */
const LATIN_MODE = /^(Bus|Train|Louage|Taxi|Marche|TGM)\s*·\s*/i;
const LATIN_DIRECT = /\s*·\s*direct\s*$/i;

/**
 * Drop a leading mode word already present in `line`, in Latin or in the active
 * language, so an already-localized label is not prefixed twice.
 */
function stripModeWord(line: string, lang: Lang): string {
  let out = line.replace(LATIN_MODE, "").replace(LATIN_DIRECT, "");
  const localized: Record<Mode, string> = {
    tgm: T[lang].modeTgm,
    bus: T[lang].modeBus,
    train: T[lang].modeTrain,
    louage: T[lang].modeLouage,
    walk: T[lang].modeWalk,
    taxi: T[lang].modeTaxi,
  };
  for (const w of Object.values(localized)) {
    if (!w) continue;
    out = out.replace(new RegExp(`^${escapeRe(w)}\\s*·\\s*`), "");
  }
  return out;
}

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * The card label comes from the API as "Bus · 1 h 38 · direct" — Latin in every
 * language. Rebuild the mode word in the active language and keep the rest.
 */
export function cardLabel(r: Pick<RouteOption, "id" | "line">, lang: Lang): string {
  const t = T[lang];
  if (r.id === "walk") return `${t.modeWalk} · ${t.direct}`;
  const mode: string =
    r.id === "tgm" ? t.modeTgm
    : r.id === "bus" ? t.modeBus
    : r.id === "train" ? t.modeTrain
    : r.id === "louage" ? t.modeLouage
    : t.modeTaxi;
  const rest = stripModeWord(r.line || "", lang);
  return [mode, rest, t.direct].filter(Boolean).join(" · ");
}

/** Mode word for the LED board badge; `route.line` is Latin in every language. */
export function modeWord(id: Mode, lang: Lang): string {
  const t = T[lang];
  switch (id) {
    case "tgm": return t.modeTgm;
    case "bus": return t.modeBus;
    case "train": return t.modeTrain;
    case "louage": return t.modeLouage;
    case "walk": return t.modeWalk;
    default: return t.modeTaxi;
  }
}


/**
 * Format a route duration for the current locale.
 *
 * Values below one hour stay in minutes. Longer journeys use hours and the
 * remaining whole minutes, omitting a zero remainder: 58 min, 1 h 38 min, 2 h.
 * A negative input is clamped to zero rather than rendered.
 */
export function formatDuration(minutes: number, lang: Lang): string {
  const t = T[lang];
  const rounded = Math.max(0, Math.round(minutes));
  if (rounded < 60) return fmt(t.durationUnderHour, { n: rounded });
  const h = Math.floor(rounded / 60);
  const m = rounded - h * 60;
  if (m === 0) return fmt(t.durationHours, { h });
  return fmt(t.durationHoursAndMinutes, { h, m });
}

/** Compact form for one-segment labels, which omit the locale's unit words. */
export function formatDurationShort(minutes: number, lang: Lang): string {
  const t = T[lang];
  const rounded = Math.max(0, Math.round(minutes));
  if (rounded < 60) return fmt(t.durationUnderHour, { n: rounded });
  const h = Math.floor(rounded / 60);
  const m = rounded - h * 60;
  if (m === 0) return fmt(t.durationHoursShort, { h });
  return fmt(t.durationHoursAndMinutesShort, { h, m });
}
