import { useEffect, useState } from "react";
import MapView, { zoom } from "./components/MapView";
import LedBoard from "./components/LedBoard";
import LinesCatalog from "./components/LinesCatalog";
import PlaceInput from "./components/PlaceInput";
import WelcomeBoard from "./components/WelcomeBoard";
import { fetchLine, type LineDetail } from "./catalog";
import { byId, type Place } from "./data";
import { T, fmt, type Lang } from "./i18n";
import { cardLabel, formatDuration } from "./labels";
import { hhmm, planRoutes, type Mode, type RouteOption, type Step } from "./routing";

const SIDEBAR_W = 440;

function useIsMobile() {
  const [m, setM] = useState(() => window.innerWidth < 768);
  useEffect(() => {
    const f = () => setM(window.innerWidth < 768);
    window.addEventListener("resize", f);
    return () => window.removeEventListener("resize", f);
  }, []);
  return m;
}

const POPULAR: [string, string][] = [
  ["tunis-marine", "la-marsa"],
  ["barcelone", "sidi-bou-said"],
  ["aeroport", "medina"],
  ["lac2", "salammbo"],
];

const modeStyle: Record<Mode, { bg: string; text: string; ring: string }> = {
  tgm: { bg: "bg-brand", text: "text-brand", ring: "ring-brand" },
  train: { bg: "bg-blue-600", text: "text-blue-600", ring: "ring-blue-600" },
  bus: { bg: "bg-emerald-600", text: "text-emerald-600", ring: "ring-emerald-600" },
  louage: { bg: "bg-violet-600", text: "text-violet-600", ring: "ring-violet-600" },
  taxi: { bg: "bg-amber-500", text: "text-amber-600", ring: "ring-amber-500" },
  walk: { bg: "bg-slate-400", text: "text-slate-500", ring: "ring-slate-400" },
};

const modeIcon = (m: Mode) => (m === "tgm" || m === "train" ? "train" : m === "walk" ? "walk" : m);

function Icon({ name, className = "h-4 w-4" }: { name: string; className?: string }) {
  const p: Record<string, React.ReactNode> = {
    swap: <path d="M7 4v16M7 4 3 8m4-4 4 4M17 20V4m0 16-4-4m4 4 4-4" />,
    walk: <><circle cx="13" cy="4" r="2" /><path d="m9 20 3-6 3 3v4M6 12l3-3 4 1 3 3M10 9l-1 5" /></>,
    train: <><rect x="5" y="3" width="14" height="14" rx="3" /><path d="M5 11h14M8 21l2-4M16 21l-2-4" /><circle cx="9" cy="14" r=".5" /><circle cx="15" cy="14" r=".5" /></>,
    bus: <><rect x="4" y="3" width="16" height="15" rx="3" /><path d="M4 11h16M7 21v-3M17 21v-3" /><circle cx="8" cy="14.5" r=".5" /><circle cx="16" cy="14.5" r=".5" /></>,
    taxi: <><path d="M5 17h14v-5l-2-5H7l-2 5v5ZM5 12h14M9 4h6v3" /><circle cx="8" cy="17" r="2" /><circle cx="16" cy="17" r="2" /></>,
    flag: <path d="M5 21V4h11l-2 4 2 4H5" />,
    plus: <path d="M12 5v14M5 12h14" />,
    minus: <path d="M5 12h14" />,
    moon: <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" />,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
    leaf: <path d="M5 21c0-9 6-15 15-16-1 9-7 15-15 16Zm0 0 8-8" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className}>
      {p[name]}
    </svg>
  );
}

export default function App() {
  const [lang, setLang] = useState<Lang>("fr");
  // No default route: the app opens on the welcome state so the first thing the
  // rider sees is the greeting, not a pre-filled Tunis Marine -> La Marsa trip.
  const [from, setFrom] = useState<Place | null>(null);
  const [to, setTo] = useState<Place | null>(null);
  const [now, setNow] = useState(new Date());
  const [sel, setSel] = useState<Mode>("tgm");
  const [dark, setDark] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(true);
  const [spin, setSpin] = useState(false);
  // The line catalog is a separate screen; `catalogLine` is the line whose stops
  // and track are drawn on the map behind it.
  const [view, setView] = useState<"plan" | "lines">("plan");
  const [catalogLine, setCatalogLine] = useState<string | null>(null);
  const [lineDetail, setLineDetail] = useState<LineDetail | null>(null);
  const isMobile = useIsMobile();
  const t = T[lang];
  const rtl = lang === "ar";

  useEffect(() => {
    if (!catalogLine) {
      setLineDetail(null);
      return;
    }
    let alive = true;
    fetchLine(catalogLine)
      .then((d) => {
        if (alive) setLineDetail(d);
      })
      .catch(() => {
        if (alive) setLineDetail(null);
      });
    return () => {
      alive = false;
    };
  }, [catalogLine]);

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 20000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    // Set dir on <html> too, not just the panel: without it the document has no
    // base direction and bidi-neutral runs (times, prices) resolve LTR.
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    document.documentElement.classList.toggle("dark", dark);
  }, [lang, dark]);

  const [routes, setRoutes] = useState<RouteOption[]>([]);

  // planRoutes is async (it calls the backend); useMemo cannot hold a Promise.
  // It only runs once both ends are chosen: with no origin/destination there is
  // nothing to plan, and the app shows the welcome state instead.
  useEffect(() => {
    if (!from || !to) {
      setRoutes([]);
      return;
    }
    let alive = true;
    planRoutes(from, to, now)
      .then((r) => {
        if (alive) setRoutes(r);
      })
      .catch(() => {
        if (alive) setRoutes([]);
      });
    return () => {
      alive = false;
    };
  }, [from, to, now]);

  const hasRoute = !!(from && to);
  const route = routes.find((r) => r.id === sel) ?? routes[0];
  // "Fastest"/"cheapest" compare durations and prices, not list order. Walking is
  // never the fastest option, so it is excluded from that badge.
  const fastest = [...routes]
    .filter((r) => r.id !== "walk")
    .sort((a, b) => a.minutes - b.minutes)[0]?.id;
  const cheapest = [...routes].sort((a, b) => a.price - b.price)[0]?.id;

  const swap = () => {
    setSpin((s) => !s);
    setFrom(to);
    setTo(from);
  };

  const name = (x: Step["target"]) => x[lang];

  const stepText = (s: Step) => {
    switch (s.kind) {
      case "walk": return fmt(t.walkTo, { x: name(s.target) });
      case "tgm": return fmt(t.take, { l: t.modeTgm, x: name(s.target) });
      case "bus": return fmt(t.takeBus, { l: s.line ?? t.modeBus, x: name(s.target) });
      case "train": return fmt(t.takeTrain, { l: s.line ?? t.modeTrain, x: name(s.target) });
      case "louage": return fmt(t.takeLouage, { l: s.line ?? t.modeLouage, x: name(s.target) });
      case "taxi": return fmt(t.taxi, { x: name(s.target) });
      case "exit": return fmt(t.exit, { x: name(s.target) });
    }
    return "";
  };

  const sheetH = isMobile ? (sheetOpen ? Math.round(window.innerHeight * 0.62) : 150) : 0;

  const panel = (
    <div dir={rtl ? "rtl" : "ltr"} className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pb-4 pt-5">
        <a href="#" className="flex items-baseline text-[26px] font-extrabold tracking-tight text-slate-900 dark:text-white" dir="ltr">
          bledi<span className="text-brand dark:text-sky-400">.tn</span>
        </a>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setView(view === "lines" ? "plan" : "lines")}
            className={`rounded-xl px-2.5 py-1.5 text-xs font-semibold transition ${
              view === "lines"
                ? "bg-brand text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            }`}
          >
            {t.lineCatalog}
          </button>
          <div className="flex rounded-xl bg-slate-100 p-1 dark:bg-slate-800">
            {(["fr", "ar", "en"] as Lang[]).map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                className={`h-8 min-w-9 rounded-lg px-2 text-sm font-semibold transition ${
                  lang === l ? "bg-slate-900 text-white shadow dark:bg-white dark:text-slate-900" : "text-slate-500 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                {l === "ar" ? "ع" : l.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {view === "lines" ? (
        <div className="min-h-0 flex-1">
          <LinesCatalog
            lang={lang}
            onPickLine={(id) => {
              setCatalogLine(id);
              setView("plan");
            }}
            onClose={() => setView("plan")}
          />
        </div>
      ) : (
      <div className="scroll-thin flex-1 space-y-4 overflow-y-auto px-5 pb-5">
        {/* Inputs */}
        <div className="relative">
          <div className="pointer-events-none absolute top-[38px] bottom-[38px] z-20 w-px border-s-2 border-dotted border-slate-300 start-[20px] dark:border-slate-600" />
          <PlaceInput value={from} onChange={setFrom} lang={lang} dot="#1f6f8b" label={t.from} rounded="rounded-t-2xl" placeholder={t.pickFrom} />
          <div className="-mt-px">
            <PlaceInput value={to} onChange={setTo} lang={lang} dot="#e03131" label={t.to} rounded="rounded-b-2xl" placeholder={t.pickTo} />
          </div>
          <button
            onClick={swap}
            title={t.swap}
            className="absolute top-1/2 z-20 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-md transition hover:scale-105 hover:text-brand active:scale-95 end-4 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100"
          >
            <span className={`transition-transform duration-300 ${spin ? "rotate-180" : ""}`}>
              <Icon name="swap" className="h-[18px] w-[18px]" />
            </span>
          </button>
        </div>

        {/* Selected line from the catalog: keep it visible while planning. */}
        {lineDetail && view === "plan" && (
          <div className="flex items-center justify-between gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 dark:border-sky-800 dark:bg-sky-900/20">
            <span className="min-w-0 truncate text-xs font-semibold text-sky-800 dark:text-sky-200">
              {lineDetail.line.number || lineDetail.line.id} · {lineDetail.line.name || lineDetail.line.id}
            </span>
            <button
              onClick={() => setCatalogLine(null)}
              className="shrink-0 rounded-md px-1.5 py-0.5 text-xs font-bold text-sky-700 hover:bg-sky-100 dark:text-sky-300 dark:hover:bg-sky-900/40"
              aria-label={t.back}
            >
              ✕
            </button>
          </div>
        )}

        {/* Time chip */}
        <div className="flex items-center gap-2 text-sm">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            <Icon name="clock" className="h-3.5 w-3.5" /> {t.leaveNow} · <span className="tabular-nums" dir="ltr">{hhmm(now)}</span>
          </span>
        </div>

        {hasRoute && routes.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-slate-700">{t.same}</div>
        ) : !hasRoute ? (
          <WelcomeBoard lang={lang} title={t.welcomeTitle} hint={t.welcomeHint} />
        ) : (
          <>
            <LedBoard route={route} lang={lang} now={now} />

            {/* Options */}
            <div>
              <div className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-400">{t.options}</div>
              <div className="grid grid-cols-3 gap-2">
                {routes.map((r: RouteOption, i: number) => {
                  const on = r.id === route?.id;
                  const st = modeStyle[r.id];
                  return (
                    <button
                      // The mode id repeats across options (bus, bus, walk...), so
                      // key on it alone collides; add the index.
                      key={`${r.id}-${i}`}
                      onClick={() => setSel(r.id)}
                      className={`relative rounded-2xl border bg-white p-3 text-start transition hover:-translate-y-0.5 hover:shadow-md dark:bg-slate-800 ${
                        on ? `border-transparent ring-2 ${st.ring} shadow-md` : "border-slate-200 dark:border-slate-700"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className={`${st.bg} inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-bold text-white`}>
                          <Icon name={modeIcon(r.id)} className="h-3.5 w-3.5" />
                          {cardLabel(r, lang)}
                        </span>
                      </div>
                      <div className="mt-2 text-xl font-bold text-slate-900 dark:text-white">
                        {formatDuration(r.minutes, lang)}
                      </div>
                      <div className="text-[11px] tabular-nums text-slate-500" dir="ltr">
                        {hhmm(r.depart)}–{hhmm(r.arrive)}
                      </div>
                      <div className="mt-1 text-xs font-semibold text-slate-700 dark:text-slate-300">
                        {r.price.toFixed(r.price < 1 ? 3 : 1)} {t.dt}
                      </div>
                      {(r.id === fastest || r.id === cheapest) && (
                        <div className="absolute -top-2 end-2 rounded-full bg-slate-900 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white dark:bg-white dark:text-slate-900">
                          {r.id === fastest ? t.fastest : t.cheapest}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Steps */}
            {route && (
              <div key={route.id + from.id + to.id} className="fade-up rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
                <div className="mb-3 flex items-center justify-between">
                  <div className="text-xs font-bold uppercase tracking-wider text-slate-400">{t.steps}</div>
                  <div className="flex items-center gap-2">
                    {route.estimated && (
                      <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300" title={t.estimated}>
                        {t.estimated}
                      </span>
                    )}
                    {route.id !== "taxi" && (
                    <div className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                      <Icon name="leaf" className="h-3 w-3" /> {t.co2} · {Math.round(route.minutes * 0.09 * 10) / 10} kg
                    </div>
                  )}
                  </div>
                </div>
                <ol className="relative">
                  {route.steps.map((s, i) => {
                    const last = i === route.steps.length - 1;
                    const ride = s.kind === "tgm" || s.kind === "bus" || s.kind === "taxi";
                    const color = s.kind === "tgm" ? "#1f6f8b" : s.kind === "bus" ? "#059669" : s.kind === "taxi" ? "#f59e0b" : "#94a3b8";
                    return (
                      <li key={i} className="relative flex gap-3 pb-4 last:pb-0">
                        {!last && (
                          <span
                            className="absolute top-8 bottom-0 start-[13px] w-0"
                            style={{ borderInlineStart: ride ? `3px solid ${color}` : `2px dotted ${color}` }}
                          />
                        )}
                        <span
                          className="relative z-10 grid h-7 w-7 shrink-0 place-items-center rounded-full border-2 bg-white dark:bg-slate-800"
                          style={{ borderColor: color, color }}
                        >
                          <Icon name={s.kind === "walk" ? "walk" : s.kind === "exit" ? "flag" : modeIcon(s.kind as Mode)} className="h-3.5 w-3.5" />
                        </span>
                        <div className="min-w-0 flex-1 pt-0.5">
                          <div className="text-[15px] font-medium leading-snug text-slate-800 dark:text-slate-100">{stepText(s)}</div>
                          {s.stops && (
                            <div className="mt-0.5 text-xs text-slate-500">{fmt(t.stops, { n: s.stops })}</div>
                          )}
                        </div>
                        <span className="shrink-0 pt-1 text-xs font-medium tabular-nums text-slate-500">
                          {formatDuration(s.minutes, lang)}
                        </span>
                      </li>
                    );
                  })}
                </ol>
                <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 text-sm dark:border-slate-700">
                  <span className="text-slate-500">{t.arrival}</span>
                  <span className="font-bold tabular-nums text-slate-900 dark:text-white" dir="ltr">{hhmm(route.arrive)}</span>
                </div>
              </div>
            )}
          </>
        )}

        {/* Popular */}
        <div>
          <div className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-400">{t.recent}</div>
          <div className="flex flex-wrap gap-2">
            {POPULAR.map(([a, b]) => (
              <button
                key={a + b}
                onClick={() => {
                  setFrom(byId(a));
                  setTo(byId(b));
                }}
                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-brand hover:text-brand dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
              >
                {byId(a)[lang]} {rtl ? "←" : "→"} {byId(b)[lang]}
              </button>
            ))}
          </div>
        </div>
      </div>
      )}
    </div>
  );

  return (
    <div className="relative h-full w-full overflow-hidden bg-slate-100 dark:bg-slate-950">
      <MapView from={from} to={to} route={route} isMobile={isMobile} sidebarWidth={SIDEBAR_W} sheetHeight={sheetH} dark={dark} line={lineDetail} />
      {/* Map controls */}
      <div className="absolute end-4 top-4 z-[500] flex flex-col items-end gap-2">
        <div className="hidden rounded-xl bg-slate-900/85 px-3 py-1.5 text-xs font-semibold text-white shadow-lg backdrop-blur sm:block">
          {t.preview} · bledi.tn
        </div>
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-800">
          <button onClick={() => zoom(1)} className="grid h-10 w-10 place-items-center text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700" aria-label="Zoom in">
            <Icon name="plus" />
          </button>
          <div className="h-px bg-slate-200 dark:bg-slate-700" />
          <button onClick={() => zoom(-1)} className="grid h-10 w-10 place-items-center text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700" aria-label="Zoom out">
            <Icon name="minus" />
          </button>
        </div>
        <button
          onClick={() => setDark((d) => !d)}
          className="grid h-10 w-10 place-items-center rounded-xl border border-slate-200 bg-white text-slate-700 shadow-lg hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-amber-300"
          aria-label="Theme"
        >
          <Icon name={dark ? "sun" : "moon"} />
        </button>
      </div>

      {isMobile ? (
        <div
          className="absolute inset-x-0 bottom-0 z-[600] rounded-t-3xl bg-slate-50/95 shadow-[0_-10px_40px_-10px_rgba(0,0,0,.3)] backdrop-blur-xl transition-[height] duration-300 dark:bg-slate-900/95"
          style={{ height: sheetH }}
        >
          <button onClick={() => setSheetOpen((o) => !o)} className="flex w-full justify-center pt-2.5 pb-1" aria-label="Toggle panel">
            <span className="h-1.5 w-12 rounded-full bg-slate-300 dark:bg-slate-600" />
          </button>
          <div className="h-[calc(100%-20px)]">{panel}</div>
        </div>
      ) : (
        <aside
          // In Arabic the whole panel mirrors to the right edge, not just the text.
          className={`absolute top-4 bottom-4 z-[600] overflow-hidden rounded-3xl border border-white/60 bg-slate-50/90 shadow-2xl shadow-slate-900/20 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/90 ${
            rtl ? "end-4" : "start-4"
          }`}
          style={{ width: SIDEBAR_W }}
        >
          {panel}
        </aside>
      )}
    </div>
  );
}
