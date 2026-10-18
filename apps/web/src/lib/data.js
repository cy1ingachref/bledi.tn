// Live data from bledi.tn backend API
export const dict = {
  fr: { from: 'D\'où partez-vous ?', to: 'Où allez-vous ?', swap: 'Inverser', min: 'min', routes: 'Itinéraires' },
  ar: { from: 'من أين تنطلق؟', to: 'إلى أين؟', swap: 'عكس الاتجاه', min: 'د', routes: 'المسارات' },
  en: { from: 'Where from?', to: 'Where to?', swap: 'Swap', min: 'min', routes: 'Routes' }
};

export const places = {
  a: { fr: 'Tunis Marine', ar: 'تونس البحرية' },
  b: { fr: 'La Marsa', ar: 'المرسى' }
};

// Fetch stations from backend (direct connection to avoid proxy timeout)
const API_BASE = 'http://localhost:8000/api/v1';

export async function fetchStations() {
  const res = await fetch(`${API_BASE}/stations`);
  const data = await res.json();
  return data.features.map(f => ({
    id: f.properties.id,
    name: f.properties.name,
    lat: f.geometry.coordinates[1],
    lon: f.geometry.coordinates[0],
    mode: f.properties.mode,
  }));
}

// Fetch route plan from backend
export async function fetchRoute(fromLat, fromLon, toLat, toLon) {
  const params = new URLSearchParams({
    start_lat: fromLat,
    start_lon: fromLon,
    end_lat: toLat,
    end_lon: toLon,
  });
  const res = await fetch(`${API_BASE}/route/plan?${params}`);
  const data = await res.json();
  return data;
}

// Routes replaced with empty array — dynamic loading after both from/to selected
export const routes = [];
