export type LatLng = [number, number];

export interface Place {
  id: string;
  fr: string;
  ar: string;
  en: string;
  pos: LatLng;
  tgm?: boolean;
  kind: "station" | "place";
  mode?: string;
  operator?: string;
}

let _stations: Place[] | null = null;

async function api(path: string): Promise<any> {
  const res = await fetch(`/api/v1${path}`);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

/** Backend station id -> the id the seeded TGM/places list uses. */
const TGM_ID: Record<string, string> = {
  "tunis_marine": "tunis-marine",
  "tunis_marine_nord": "tunis-marine",
  "le_bac": "le-bac",
  "la_goulette": "goulette-vieille",
  "goulette_neuve": "goulette-neuve",
  "goulette_casino": "goulette-neuve",
  "khiareddine": "kheireddine",
  "kheireddine": "kheireddine",
  "a_roport": "kheireddine",
  "le_kram": "le-kram",
  "carthage_salambo": "salammbo",
  "carthage_byrsa": "byrsa",
  "carthage_dermech": "byrsa",
  "carthage_hannibal": "hannibal",
  "carthage_pr_sidence": "hannibal",
  "carthage_amilcar": "hannibal",
  "sidi_bousaid": "sidi-bou-said",
  "sidi_dhrif": "sidi-bou-said",
  "la_corniche": "marsa-plage",
  "marsa_plage": "marsa-plage",
};

export async function loadStations(): Promise<Place[]> {
  if (_stations) return _stations;
  try {
    const geojson = await api("/stations?limit=10000");
    const features = Array.isArray(geojson?.features) ? geojson.features : [];
    _stations = features
      .filter((f: any) => f?.geometry?.type === "Point")
      .map((f: any) => {
        const coords = f.geometry.coordinates as [number, number];
        const p = f.properties || {};
        const name = String(p.name || p.name_en || "");
        const id = TGM_ID[String(p.id)] ?? `st_${String(p.id)}`;
        return {
          id,
          fr: name,
          ar: name,
          en: String(p.name_en || name),
          pos: [Number(coords[1]), Number(coords[0])] as LatLng,
          kind: "station" as const,
          mode: p.mode || p.mode_raw || "unknown",
          operator: p.operator || "",
        };
      });
  } catch {
    _stations = [];
  }
  return _stations ?? [];
}


// Geocoding is deliberately not wired into autocomplete: Nominatim's public
// usage policy forbids as-you-type queries. The backend /api/v1/geocode
// endpoint remains available for an explicit address-search action.
// TGM line (Tunis–Goulette–Marsa), ordered. Curated: this is the reference the
// map and the popular-trip chips use, and the backend has no Arabic names.
export const TGM: Place[] = [
  { id: "tunis-marine", fr: "Tunis Marine", ar: "تونس البحرية", en: "Tunis Marine", pos: [36.7997, 10.1882], tgm: true, kind: "station" },
  { id: "le-bac", fr: "Le Bac", ar: "الباك", en: "Le Bac", pos: [36.8136, 10.2985], tgm: true, kind: "station" },
  { id: "goulette-vieille", fr: "La Goulette Vieille", ar: "حلق الوادي القديمة", en: "La Goulette Vieille", pos: [36.8180, 10.3043], tgm: true, kind: "station" },
  { id: "goulette-neuve", fr: "La Goulette Neuve", ar: "حلق الوادي الجديدة", en: "La Goulette Neuve", pos: [36.8238, 10.3070], tgm: true, kind: "station" },
  { id: "kheireddine", fr: "Kheireddine", ar: "خير الدين", en: "Kheireddine", pos: [36.8312, 10.3112], tgm: true, kind: "station" },
  { id: "le-kram", fr: "Le Kram", ar: "الكرم", en: "Le Kram", pos: [36.8352, 10.3160], tgm: true, kind: "station" },
  { id: "salammbo", fr: "Carthage Salammbô", ar: "قرطاج صلامبو", en: "Carthage Salammbô", pos: [36.8446, 10.3225], tgm: true, kind: "station" },
  { id: "byrsa", fr: "Carthage Byrsa", ar: "قرطاج بيرصا", en: "Carthage Byrsa", pos: [36.8511, 10.3262], tgm: true, kind: "station" },
  { id: "hannibal", fr: "Carthage Hannibal", ar: "قرطاج حنبعل", en: "Carthage Hannibal", pos: [36.8580, 10.3308], tgm: true, kind: "station" },
  { id: "sidi-bou-said", fr: "Sidi Bou Saïd", ar: "سيدي بوسعيد", en: "Sidi Bou Said", pos: [36.8676, 10.3410], tgm: true, kind: "station" },
  { id: "marsa-plage", fr: "La Marsa Plage", ar: "المرسى الشاطئ", en: "La Marsa Beach", pos: [36.8787, 10.3254], tgm: true, kind: "station" },
];

export const PLACES: Place[] = [
  ...TGM,
  { id: "la-marsa", fr: "La Marsa", ar: "المرسى", en: "La Marsa", pos: [36.8822, 10.3240], kind: "place" },
  { id: "barcelone", fr: "Place Barcelone", ar: "ساحة برشلونة", en: "Barcelona Square", pos: [36.7963, 10.1806], kind: "place" },
  { id: "medina", fr: "Médina de Tunis", ar: "المدينة العتيقة", en: "Tunis Medina", pos: [36.7988, 10.1700], kind: "place" },
  { id: "bab-saadoun", fr: "Bab Saadoun", ar: "باب سعدون", en: "Bab Saadoun", pos: [36.8090, 10.1600], kind: "place" },
  { id: "lac2", fr: "Les Berges du Lac 2", ar: "البحيرة 2", en: "Lac 2", pos: [36.8455, 10.2700], kind: "place" },
  { id: "aeroport", fr: "Aéroport Tunis-Carthage", ar: "مطار تونس قرطاج", en: "Tunis-Carthage Airport", pos: [36.8510, 10.2272], kind: "place" },
  { id: "ariana", fr: "Ariana Centre", ar: "أريانة المركز", en: "Ariana Centre", pos: [36.8625, 10.1956], kind: "place" },
  { id: "bardo", fr: "Le Bardo", ar: "باردو", en: "Le Bardo", pos: [36.8092, 10.1340], kind: "place" },
  { id: "ben-arous", fr: "Ben Arous", ar: "بن عروس", en: "Ben Arous", pos: [36.7530, 10.2280], kind: "place" },
  { id: "gammarth", fr: "Gammarth", ar: "قمرت", en: "Gammarth", pos: [36.9180, 10.2870], kind: "place" },
];

export function byId(id: string): Place {
  return PLACES.find((p) => p.id === id) ?? { id, fr: id, ar: id, en: id, pos: [0, 0], kind: "place" };
}
