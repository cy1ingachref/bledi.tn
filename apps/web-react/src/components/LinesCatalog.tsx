import { useEffect, useMemo, useState } from "react";
import { fmt, T, type Lang } from "../i18n";
import {
  fetchLine,
  fetchLines,
  linePath,
  missingSegments,
  orderedStops,
  type LineDetail,
  type LineMode,
  type LineSummary,
} from "../catalog";

interface Props {
  lang: Lang;
  onPickLine: (id: string) => void;
  onClose: () => void;
}

const MODE_TAB: { mode: LineMode | "all"; labelKey: string }[] = [
  { mode: "all", labelKey: "allLines" },
  { mode: "bus", labelKey: "modeBus" },
  { mode: "train", labelKey: "modeTrain" },
  { mode: "metro", labelKey: "modeMetro" },
  { mode: "rail", labelKey: "modeRail" },
  { mode: "louage", labelKey: "modeLouage" },
];

const MODE_COLOR: Record<string, string> = {
  bus: "#059669",
  train: "#2563eb",
  metro: "#0891b2",
  rail: "#7c3aed",
  louage: "#7c3aed",
};

/**
 * The line catalog: pick a mode, then a line number, and the table lists every
 * stop that line calls at in order, with its name and coordinates, and the
 * line's track on the map. A stop served by several lines appears in each.
 */
export default function LinesCatalog({ lang, onPickLine, onClose }: Props) {
  const t = T[lang];
  const [lines, setLines] = useState<LineSummary[]>([]);
  const [tab, setTab] = useState<LineMode | "all">("bus");
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LineDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchLines()
      .then(setLines)
      .catch((e) => setError(String(e.message || e)));
  }, []);

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return lines.filter((l) => {
      if (tab !== "all" && l.mode !== tab) return false;
      // Lines with no stops at all cannot show a stop table; hide them unless
      // the rider is explicitly searching for one.
      if (l.stops_count === 0 && !needle) return false;
      if (!needle) return true;
      const hay = `${l.number || ""} ${l.short_name || ""} ${l.long_name || ""} ${l.id}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [lines, tab, q]);

  const hiddenEmpty = useMemo(
    () => lines.filter((l) => l.stops_count === 0).length,
    [lines]
  );

  useEffect(() => {
    if (!openId) {
      setDetail(null);
      return;
    }
    let alive = true;
    setLoading(true);
    setError("");
    fetchLine(openId)
      .then((d) => {
        if (alive) setDetail(d);
      })
      .catch((e) => {
        if (alive) setError(String(e.message || e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [openId]);

  const open = lines.find((l) => l.id === openId) || null;
  const stops = detail ? orderedStops(detail) : [];
  const path = detail ? linePath(detail) : [];
  const gaps = detail ? missingSegments(detail) : [];
  const missingCoords = stops.filter((s) => s.lat === null || s.lon === null);

  return (
    <div dir={lang === "ar" ? "rtl" : "ltr"} className="flex h-full flex-col bg-slate-50/95 dark:bg-slate-900/95">
      {/* Head */}
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-700">
        <div>
          <div className="text-[26px] font-extrabold tracking-tight text-slate-900 dark:text-white">
            bledi<span className="text-brand dark:text-sky-400">.tn</span>
          </div>
          <div className="mt-0.5 text-xs text-slate-500">{t.lineCatalogHint}</div>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg border border-slate-200 px-2.5 py-1 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          {t.back}
        </button>
      </div>

      {/* Mode tabs */}
      <div className="flex flex-wrap gap-1.5 px-5 pt-4">
        {MODE_TAB.map(({ mode, labelKey }) => {
          const key = labelKey as keyof typeof t;
          const on = tab === mode;
          return (
            <button
              key={mode}
              onClick={() => setTab(mode)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                on
                  ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              }`}
            >
              {t[key]}
              {mode !== "all" && (
                <span className="ms-1.5 tabular-nums opacity-70">
                  {lines.filter((l) => l.mode === mode).length}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Search */}
      <div className="px-5 pt-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t.searchLine}
          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
      </div>

      <div className="mt-3 grid min-h-0 flex-1 grid-cols-1 gap-0 border-t border-slate-200 dark:border-slate-700 md:grid-cols-[minmax(200px,280px)_1fr]">
        {/* Line list */}
        <div className="scroll-thin min-h-0 overflow-y-auto border-e border-slate-200 dark:border-slate-700">
          {error && <div className="px-4 py-3 text-xs text-red-600">{error}</div>}
          {!error && lines.length === 0 && <div className="px-4 py-3 text-xs text-slate-500">{t.loading}</div>}
          {visible.map((l) => {
            const on = l.id === openId;
            const n = l.number || l.id;
            return (
              <button
                key={l.id}
                onClick={() => setOpenId(l.id)}
                className={`flex w-full items-center gap-2.5 border-b border-slate-100 px-4 py-2.5 text-start transition dark:border-slate-800 ${
                  on ? "bg-sky-50 dark:bg-slate-800" : "hover:bg-slate-100 dark:hover:bg-slate-800/60"
                }`}
              >
                <span
                  className="grid h-7 min-w-9 shrink-0 place-items-center rounded-md px-1.5 text-xs font-bold text-white"
                  style={{ background: l.color ? `#${String(l.color).replace("#", "")}` : MODE_COLOR[l.mode] || "#64748b" }}
                >
                  {n}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-slate-800 dark:text-slate-100">
                    {l.long_name || l.short_name || l.number || l.id}
                  </span>
                  <span className="block text-[11px] text-slate-500">
                    {t[l.mode as keyof typeof t] ?? l.mode} ·{" "}
                    {l.stops_count === 0 ? t.noStops : `${l.stops_count} ${t.stopsWord}`}
                  </span>
                </span>
                {l.stops_count === 0 && (
                  <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-400 dark:bg-slate-800">
                    {t.noStopsShort}
                  </span>
                )}
              </button>
            );
          })}
          {visible.length === 0 && !error && lines.length > 0 && (
            <div className="px-4 py-3 text-xs text-slate-500">{t.noLines}</div>
          )}
          {!q && hiddenEmpty > 0 && (
            <div className="border-b border-slate-100 px-4 py-2 text-[11px] text-slate-400 dark:border-slate-800">
              {fmt(t.hiddenEmptyLines, { n: hiddenEmpty })}
            </div>
          )}
        </div>

        {/* Stop table */}
        <div className="scroll-thin min-h-0 overflow-y-auto">
          {!open && <div className="p-5 text-sm text-slate-500">{t.pickLine}</div>}
          {open && loading && <div className="p-5 text-sm text-slate-500">{t.loading}</div>}
          {open && detail && !loading && (
            <>
              <div className="sticky top-0 z-10 border-b border-slate-200 bg-slate-50/95 px-5 py-3 backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className="grid h-8 min-w-10 place-items-center rounded-lg px-2 text-sm font-bold text-white"
                    style={{ background: MODE_COLOR[detail.mode] || "#64748b" }}
                  >
                    {open.number || open.id}
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-slate-900 dark:text-white">
                      {open.long_name || open.short_name || open.id}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      {t[open.mode as keyof typeof t] ?? open.mode} · {open.stops_count} {t.stopsWord}
                    </div>
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                  <button
                    onClick={() => onPickLine(open.id)}
                    className="rounded-full bg-brand px-2.5 py-1 font-semibold text-white hover:opacity-90"
                  >
                    {t.showOnMap}
                  </button>
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-1 font-semibold ${
                      detail.geometry_complete
                        ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                        : "bg-amber-50 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                    }`}
                  >
                    {detail.geometry_complete ? t.geometryComplete : fmt(t.geometryGaps, { n: gaps.length })}
                  </span>
                  {missingCoords.length > 0 && (
                    <span className="inline-flex items-center rounded-full bg-red-50 px-2 py-1 font-semibold text-red-700 dark:bg-red-900/40 dark:text-red-300">
                      {fmt(t.stopsWithoutCoords, { n: missingCoords.length })}
                    </span>
                  )}
                </div>
                {gaps.length > 0 && (
                  <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-[11px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
                    {gaps.map((g, i) => (
                      <div key={i}>
                        {g.from_name} → {g.to_name} · {g.gap_m} m
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <table className="w-full border-collapse text-start text-[13px]">
                <thead className="sticky top-[104px] z-10 bg-slate-100 text-[11px] uppercase tracking-wider text-slate-500 dark:bg-slate-800">
                  <tr>
                    <th className="w-10 px-3 py-2 text-start font-bold">#</th>
                    <th className="px-3 py-2 text-start font-bold">{t.station}</th>
                    <th className="px-3 py-2 text-start font-bold">{t.location}</th>
                    <th className="px-3 py-2 text-start font-bold">{t.otherLines}</th>
                  </tr>
                </thead>
                <tbody>
                  {stops.map((s, i) => {
                    // `lines` holds line ids; resolve them to the number shown on
                    // the network, dropping the line currently displayed.
                    const others = (s.lines || [])
                      .map((lid) => lines.find((x) => x.id === lid))
                      .filter(Boolean)
                      .map((x) => x!.number || x!.id)
                      .filter((n) => n !== open.number);
                    const unique = Array.from(new Set(others));
                    return (
                      <tr key={`${s.stop_id}-${i}`} className="border-t border-slate-100 dark:border-slate-800">
                        <td className="px-3 py-2 tabular-nums text-slate-400">{i + 1}</td>
                        <td className="px-3 py-2 text-slate-800 dark:text-slate-100">{s.name || s.stop_id}</td>
                        <td className="px-3 py-2 tabular-nums text-slate-500" dir="ltr">
                          {s.lat === null || s.lon === null ? (
                            <span className="text-red-500">{t.noLocation}</span>
                          ) : (
                            `${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}`
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {unique.length === 0 ? (
                            <span className="text-slate-400">—</span>
                          ) : (
                            <span className="flex flex-wrap gap-1">
                              {unique.slice(0, 8).map((n: string) => (
                                <span
                                  key={n}
                                  className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                                >
                                  {n}
                                </span>
                              ))}
                              {unique.length > 8 && (
                                <span className="text-[11px] text-slate-400">+{unique.length - 8}</span>
                              )}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {path.length === 0 && (
                <div className="px-5 py-3 text-xs text-slate-500">{t.noTrack}</div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
