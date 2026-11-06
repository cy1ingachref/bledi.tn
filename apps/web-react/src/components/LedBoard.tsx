import { useEffect, useState } from "react";
import type { RouteOption } from "../routing";
import { hhmm } from "../routing";
import type { Lang } from "../i18n";
import { modeWord } from "../labels";

export default function LedBoard({ route, lang, now }: { route?: RouteOption; lang: Lang; now: Date }) {
  const [showAr, setShowAr] = useState(false);
  useEffect(() => {
    const id = setInterval(() => setShowAr((v) => !v), 3500);
    return () => clearInterval(id);
  }, []);

  if (!route) return null;
  const wait = route.waitMin;
  const badgeBg =
    route.id === "tgm" ? "bg-brand"
    : route.id === "bus" ? "bg-emerald-600"
    : route.id === "train" ? "bg-blue-600"
    : route.id === "louage" ? "bg-violet-600"
    : route.id === "walk" ? "bg-slate-400"
    : "bg-amber-500";

  return (
    <div className="led-board led-scan relative overflow-hidden rounded-2xl px-4 py-3.5" dir="ltr">
      <div className="flex items-center gap-4">
        <div className={`${badgeBg} grid h-11 min-w-16 place-items-center rounded-lg px-3 text-lg font-bold tracking-wide text-white shadow-inner`}>
          {modeWord(route.id, lang)}
        </div>
        <div className="min-w-0 flex-1">
          <div key={route.headsign.id + (showAr ? "ar" : "fr")} className="led-in">
            {showAr ? (
              <div className="led-ar truncate text-right text-2xl leading-tight" dir="rtl">{route.headsign.ar}</div>
            ) : (
              <div className="led truncate text-2xl leading-tight">{lang === "en" ? route.headsign.en : route.headsign.fr}</div>
            )}
          </div>
          <div className="led mt-1 text-xs opacity-70">
            {hhmm(route.depart)} → {hhmm(route.arrive)} <span className="blink">·</span> {hhmm(now)}
          </div>
        </div>
        <div className="text-right">
          {wait <= 1 ? (
            <div className="led blink text-3xl leading-none">◆◆</div>
          ) : (
            <div className="led text-4xl leading-none tabular-nums">{wait}</div>
          )}
          <div className="led mt-1 text-xs opacity-80">{lang === "ar" ? "دق" : "min"}</div>
        </div>
      </div>
    </div>
  );
}
