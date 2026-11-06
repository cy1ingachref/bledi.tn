import { useEffect, useMemo, useRef, useState } from "react";
import { PLACES, type Place } from "../data";
import { T, type Lang } from "../i18n";

const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");

/** Mode letter for the station badge; the backend sends raw mode strings. */
const MODE_BADGE: Record<string, string> = {
  metro: "M",
  train: "T",
  bus: "B",
  louage: "L",
  louaj: "L",
  taxi: "T",
  rural: "R",
};

interface Props {
  value: Place | null;
  onChange: (p: Place) => void;
  lang: Lang;
  dot: string;
  label: string;
  rounded: string;
  placeholder: string;
}

/** Local, offline fallback so the box still resolves curated places with no backend. */
function localSearch(q: string): Place[] {
  const n = norm(q);
  return PLACES.filter(
    (p) => !n || norm(p.fr).includes(n) || norm(p.en).includes(n) || p.ar.includes(q)
  );
}

/**
 * Search the backend station index. Falls back to the curated PLACES list when
 * the API is unreachable, so the input is never a dead end.
 */
async function searchBackend(q: string, signal: AbortSignal): Promise<Place[]> {
  const res = await fetch(`/api/v1/search?q=${encodeURIComponent(q)}&limit=8`, { signal });
  if (!res.ok) throw new Error(`search ${res.status}`);
  const data = await res.json();
  const rows = Array.isArray(data.results) ? data.results : [];
  return rows.map((r: any) => ({
    id: String(r.id),
    fr: String(r.display_name || r.name || q),
    ar: String(r.display_name || r.name || q),
    en: String(r.display_name || r.name || q),
    pos: [Number(r.lat), Number(r.lon)] as [number, number],
    kind: r.kind === "stop" ? ("station" as const) : ("place" as const),
    mode: Array.isArray(r.modes) ? r.modes[0] : undefined,
    operator: "",
  }));
}

export default function PlaceInput({ value, onChange, lang, dot, label, rounded, placeholder }: Props) {
  const [q, setQ] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [results, setResults] = useState<Place[]>([]);
  const ref = useRef<HTMLInputElement>(null);
  const t = T[lang];
  const open = q !== null;

  useEffect(() => {
    const raw = q ?? "";
    if (raw.length < 2) {
      setResults([]);
      return;
    }
    const ctrl = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const rows = await searchBackend(raw, ctrl.signal);
        // Dedupe on id: the backend can return the same stop twice under
        // different names, and duplicate React keys break the list.
        setResults(Array.from(new Map(rows.map((p) => [p.id, p])).values()));
      } catch (e) {
        if ((e as Error).name !== "AbortError") setResults(localSearch(raw));
      }
    }, 200);
    return () => {
      window.clearTimeout(timer);
      ctrl.abort();
    };
  }, [q]);

  const pick = (p: Place) => {
    onChange(p);
    setQ(null);
    ref.current?.blur();
  };

  const stations = results.filter((r) => r.kind === "station");
  const places = results.filter((r) => !stations.includes(r));
  const flat = useMemo(() => [...places, ...stations], [results]);

  return (
    <div className="relative">
      <label
        className={`flex items-center gap-3 border border-slate-200 bg-white px-4 py-3 transition focus-within:z-10 focus-within:border-brand focus-within:ring-4 focus-within:ring-brand/10 dark:border-slate-700 dark:bg-slate-800 ${rounded}`}
      >
        <span className="h-2.5 w-2.5 shrink-0 rounded-full ring-4" style={{ background: dot, boxShadow: `0 0 0 4px ${dot}22` }} />
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{label}</div>
          <input
            ref={ref}
            id={`place-input-${label}`}
            name={`place-${label}`}
            aria-label={label}
            value={open ? q! : (value?.[lang] ?? "")}
            onFocus={() => {
              setQ("");
              setActive(0);
            }}
            onBlur={() => setTimeout(() => setQ(null), 150)}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(flat.length - 1, a + 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
              if (e.key === "Enter" && flat[active]) pick(flat[active]);
              if (e.key === "Escape") ref.current?.blur();
            }}
            placeholder={placeholder}
            className="w-full bg-transparent text-[15px] font-medium text-slate-800 outline-none placeholder:text-slate-400 dark:text-slate-100"
          />
        </div>
      </label>
      {open && (
        <div className="fade-up absolute inset-x-0 top-full z-30 mt-2 max-h-72 overflow-auto rounded-2xl border border-slate-200 bg-white p-1.5 shadow-2xl scroll-thin dark:border-slate-700 dark:bg-slate-800">
          {flat.length === 0 && <div className="p-4 text-center text-sm text-slate-400">{t.noResults}</div>}
          {[
            { title: t.places, items: places },
            { title: t.stations, items: stations },
          ].map(
            (g) =>
              g.items.length > 0 && (
                <div key={g.title}>
                  <div className="px-3 pb-1 pt-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">{g.title}</div>
                  {g.items.map((p) => {
                    const idx = flat.indexOf(p);
                    return (
                      <button
                        key={p.id}
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => pick(p)}
                        onMouseEnter={() => setActive(idx)}
                        className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-start transition ${
                          idx === active ? "bg-slate-100 dark:bg-slate-700" : ""
                        }`}
                      >
                        <span
                          className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg text-[10px] font-bold ${
                            p.kind === "station" ? "bg-brand text-white" : "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-300"
                          }`}
                        >
                          {/* The badge is a mode letter, not a literal "TGM": the
                              station index holds bus, louage and taxi stands too. */}
                          {p.kind === "station" ? MODE_BADGE[p.mode ?? ""] ?? "TGM" : "●"}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-slate-800 dark:text-slate-100">{p[lang]}</span>
                          <span className="block truncate text-xs text-slate-400" dir={lang === "ar" ? "ltr" : "rtl"}>
                            {lang === "ar" ? p.fr : p.ar}
                          </span>
                        </span>
                        {value && p.id === value.id && <span className="text-brand">✓</span>}
                      </button>
                    );
                  })}
                </div>
              )
          )}
        </div>
      )}
    </div>
  );
}
