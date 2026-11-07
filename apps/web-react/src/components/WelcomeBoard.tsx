import { useEffect, useState } from "react";
import type { Lang } from "../i18n";

interface Props {
  lang: Lang;
  title: string;
  hint: string;
}

/**
 * Opening state: no origin/destination chosen yet.
 *
 * Alternates the greeting between the active language and Arabic so "مرحبا بيك"
 * shows in every locale, the same way the Svelte app's board does.
 */
export default function WelcomeBoard({ lang, title, hint }: Props) {
  const [showAr, setShowAr] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setShowAr((v) => !v), 3500);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="led-board led-scan relative overflow-hidden rounded-2xl px-4 py-3.5" dir="ltr">
      <div className="flex items-center gap-4">
        <div className="grid h-11 min-w-16 shrink-0 place-items-center rounded-lg bg-brand px-3 text-base font-bold leading-tight tracking-wide text-white shadow-inner">
          {lang === "ar" ? "مرحبا" : "MARHBA"}
        </div>
        <div className="min-w-0 flex-1">
          <div key={showAr ? "ar" : lang} className="led-in">
            {showAr ? (
              <div className="led-ar truncate text-right text-2xl leading-tight" dir="rtl">مرحبا بيك</div>
            ) : (
              <div className="led truncate text-2xl leading-tight">{title}</div>
            )}
          </div>
          <div className="led mt-1 truncate text-xs opacity-70">{hint}</div>
        </div>
      </div>
    </div>
  );
}
