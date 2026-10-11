// Trilingual UI strings — FR / EN / AR.
// The docs identify Tunisian-Arabic support + RTL as a core differentiator
// versus Google Maps / Moovit, and list multi-language as an MVP "should have".

export type Lang = "fr" | "en" | "ar";

export const LANGS: { id: Lang; label: string; short: string }[] = [
  { id: "fr", label: "Français", short: "FR" },
  { id: "en", label: "English", short: "EN" },
  { id: "ar", label: "العربية", short: "ع" },
];

type Dict = Record<string, string>;

const fr: Dict = {
  "app.tagline": "Transports publics · Tunisie",
  "trip.title": "Votre trajet",
  "trip.from": "Départ",
  "trip.to": "Arrivée",
  "trip.myLocation": "Ma position",
  "trip.locating": "Localisation…",
  "trip.lat": "Lat",
  "trip.lon": "Lon",
  "priority.title": "Priorité",
  "priority.fastest": "Le plus rapide",
  "priority.cheapest": "Le moins cher",
  "priority.fewest_transfers": "Moins de changements",
  "modes.title": "Moyens de transport",
  "modes.selectAll": "Tout",
  "modes.clear": "Aucun",
  "modes.bus": "Bus",
  "modes.metro": "Métro",
  "modes.tram": "Tram",
  "modes.train": "Train",
  "modes.rfr": "RFR",
  "modes.louaj": "Louage",
  "modes.taxi": "Taxi",
  "modes.walk": "Marche",
  "action.calculate": "Calculer l'itinéraire",
  "action.calculating": "Calcul en cours…",
  "results.title": "Itinéraires",
  "results.subtitle": "du plus rapide au plus économique",
  "results.option": "Option",
  "results.min": "min",
  "results.hour": "h",
  "results.transfers": "changement",
  "results.transfersPlural": "changements",
  "results.direct": "direct",
  "results.fare": "Tarif estimé",
  "results.none": "Aucun itinéraire trouvé. Essayez d'activer plus de moyens de transport.",
  "results.steps": "Étapes",
  "status.stops": "arrêts",
  "status.routes": "itinéraires",
  "legend.title": "Légende",
  "legend.off": "masqué",
  "error.coords": "Coordonnées invalides.",
  "error.noModes": "Sélectionnez au moins un moyen de transport.",
  "error.geo": "Impossible d'obtenir votre position.",
  "error.geoUnsupported": "Géolocalisation non supportée.",
  "error.stations": "Impossible de charger les arrêts",
  "loading.stations": "Chargement des arrêts…",
  "step.walk": "Marche",
  "step.ride": "Trajet",
  "step.wait": "Attente",
  "search.placeholder": "Ville, quartier, station…",
  "search.searching": "Recherche…",
  "search.noResults": "Aucun lieu trouvé",
  "search.useCoords": "Coordonnées",
  "search.usePlace": "Lieu",
};

const en: Dict = {
  "app.tagline": "Public transport · Tunisia",
  "trip.title": "Your trip",
  "trip.from": "From",
  "trip.to": "To",
  "trip.myLocation": "My location",
  "trip.locating": "Locating…",
  "trip.lat": "Lat",
  "trip.lon": "Lon",
  "priority.title": "Priority",
  "priority.fastest": "Fastest",
  "priority.cheapest": "Cheapest",
  "priority.fewest_transfers": "Fewest changes",
  "modes.title": "Transport modes",
  "modes.selectAll": "All",
  "modes.clear": "None",
  "modes.bus": "Bus",
  "modes.metro": "Metro",
  "modes.tram": "Tram",
  "modes.train": "Train",
  "modes.rfr": "RFR",
  "modes.louaj": "Louage",
  "modes.taxi": "Taxi",
  "modes.walk": "Walk",
  "action.calculate": "Find routes",
  "action.calculating": "Calculating…",
  "results.title": "Routes",
  "results.subtitle": "fastest to cheapest",
  "results.option": "Option",
  "results.min": "min",
  "results.hour": "h",
  "results.transfers": "change",
  "results.transfersPlural": "changes",
  "results.direct": "direct",
  "results.fare": "Est. fare",
  "results.none": "No route found. Try enabling more transport modes.",
  "results.steps": "Steps",
  "status.stops": "stops",
  "status.routes": "routes",
  "legend.title": "Legend",
  "legend.off": "hidden",
  "error.coords": "Invalid coordinates.",
  "error.noModes": "Select at least one transport mode.",
  "error.geo": "Could not get your location.",
  "error.geoUnsupported": "Geolocation is not supported.",
  "error.stations": "Could not load stops",
  "loading.stations": "Loading stops…",
  "step.walk": "Walk",
  "step.ride": "Ride",
  "step.wait": "Wait",
  "search.placeholder": "City, area, station…",
  "search.searching": "Searching…",
  "search.noResults": "No place found",
  "search.useCoords": "Coordinates",
  "search.usePlace": "Place",
};

const ar: Dict = {
  "app.tagline": "النقل العمومي · تونس",
  "trip.title": "رحلتك",
  "trip.from": "من",
  "trip.to": "إلى",
  "trip.myLocation": "موقعي",
  "trip.locating": "جارٍ التحديد…",
  "trip.lat": "خط العرض",
  "trip.lon": "خط الطول",
  "priority.title": "الأولوية",
  "priority.fastest": "الأسرع",
  "priority.cheapest": "الأرخص",
  "priority.fewest_transfers": "أقل تنقلات",
  "modes.title": "وسائل النقل",
  "modes.selectAll": "الكل",
  "modes.clear": "لا شيء",
  "modes.bus": "حافلة",
  "modes.metro": "مترو",
  "modes.tram": "طرامواي",
  "modes.train": "قطار",
  "modes.rfr": "RFR",
  "modes.louaj": "لواج",
  "modes.taxi": "تاكسي",
  "modes.walk": "مشي",
  "action.calculate": "احسب المسار",
  "action.calculating": "جارٍ الحساب…",
  "results.title": "المسارات",
  "results.subtitle": "من الأسرع إلى الأرخص",
  "results.option": "خيار",
  "results.min": "دقيقة",
  "results.hour": "س",
  "results.transfers": "تنقل",
  "results.transfersPlural": "تنقلات",
  "results.direct": "مباشر",
  "results.fare": "التسعيرة التقديرية",
  "results.none": "لا يوجد مسار. جرّب تفعيل وسائل نقل أخرى.",
  "results.steps": "الخطوات",
  "status.stops": "محطة",
  "status.routes": "مسار",
  "legend.title": "المفتاح",
  "legend.off": "مخفي",
  "error.coords": "إحداثيات غير صحيحة.",
  "error.noModes": "اختر وسيلة نقل واحدة على الأقل.",
  "error.geo": "تعذّر تحديد موقعك.",
  "error.geoUnsupported": "تحديد الموقع غير مدعوم.",
  "error.stations": "تعذّر تحميل المحطات",
  "loading.stations": "جارٍ تحميل المحطات…",
  "step.walk": "مشي",
  "step.ride": "تنقل",
  "step.wait": "انتظار",
  "search.placeholder": "مدينة، حي، محطة…",
  "search.searching": "جارٍ البحث…",
  "search.noResults": "لم يتم العثور على مكان",
  "search.useCoords": "إحداثيات",
  "search.usePlace": "مكان",
};

const DICTS: Record<Lang, Dict> = { fr, en, ar };

export function translator(lang: Lang) {
  const d = DICTS[lang] ?? fr;
  return (key: string): string => d[key] ?? fr[key] ?? key;
}

/**
 * Mode label that never leaks a raw i18n key. If a mode id has no translation
 * (e.g. a new mode appears in API data before the dictionary is updated),
 * fall back to a capitalised form of the id instead of returning "modes.xyz".
 */
export function modeLabel(t: (k: string) => string, id: string): string {
  const key = `modes.${id}`;
  const v = t(key);
  if (v !== key) return v;
  return id.charAt(0).toUpperCase() + id.slice(1);
}

export function dirOf(lang: Lang): "rtl" | "ltr" {
  return lang === "ar" ? "rtl" : "ltr";
}

/** "1 h 02" / "62 min" — locale-aware duration formatting. */
export function formatDuration(minutes: number, t: (k: string) => string): string {
  const m = Math.round(minutes);
  if (m < 60) return `${m} ${t("results.min")}`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  return rest === 0 ? `${h} ${t("results.hour")}` : `${h} ${t("results.hour")} ${String(rest).padStart(2, "0")}`;
}
