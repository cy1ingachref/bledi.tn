// Data module: connects to bledi.tn backend API
// API base URL is configured in vite.config.js proxy

export { fetchRoutePlan, fetchRouteGeometry, geocode, fetchStations, fetchLines, healthCheck } from './api.js';

// Dictionary translations
export const dict = {
  fr: {
    from: 'D\'où partez-vous ?',
    to: 'Où allez-vous ?',
    swap: 'Inverser',
    min: 'min',
    routes: 'Itinéraires',
    search: 'Rechercher',
    train: 'TGM',
    bus: 'Bus'
  },
  ar: {
    from: 'من أين تنطلق؟',
    to: 'إلى أين؟',
    swap: 'عكس الاتجاه',
    min: 'د',
    routes: 'المسارات',
    search: 'بحث',
    train: 'TGM',
    bus: 'حافلة'
  },
  en: {
    from: 'Where from?',
    to: 'Where to?',
    swap: 'Swap',
    min: 'min',
    routes: 'Routes',
    search: 'Search',
    train: 'TGM',
    bus: 'Bus'
  }
};

// Default places - Tunis Marine to La Marsa
// These are approximate; the backend will find exact routes
export const places = {
  a: {
    fr: 'Tunis Marine',
    ar: 'تونس البحرية',
    lat: 36.8005,
    lon: 10.182
  },
  b: {
    fr: 'La Marsa',
    ar: 'المرسى',
    lat: 36.879,
    lon: 10.326
  }
};

// Sample itineraries, shown before the backend answers. The coordinates are approximate.
export const routes = [
  {
    id: 'tgm', badge: 'TGM', color: '#1F6F8B', minutes: 38, depart: '14:08', arrive: '14:46',
    path: [[36.8005, 10.182], [36.8183, 10.305], [36.853, 10.323], [36.869, 10.341], [36.879, 10.326]],
    steps: [
      { kind: 'walk', min: 4, label: { fr: 'Marchez jusqu’à la gare Tunis Marine', ar: 'امشِ إلى محطة تونس البحرية', en: 'Walk to Tunis Marine station' } },
      { kind: 'ride', min: 32, label: { fr: 'Prenez le TGM direction La Marsa', ar: 'اركب TGM باتجاه المرسى', en: 'Take the TGM toward La Marsa' } },
      { kind: 'walk', min: 2, label: { fr: 'Sortez à La Marsa Plage', ar: 'انزل في محطة المرسى الشاطئ', en: 'Get off at La Marsa Plage' } }
    ]
  },
  {
    id: 'bus', badge: 'Bus', color: '#2E7D4F', minutes: 51, depart: '14:12', arrive: '15:03',
    path: [[36.8005, 10.182], [36.83, 10.23], [36.85, 10.27], [36.879, 10.326]],
    steps: [
      { kind: 'walk', min: 6, label: { fr: 'Marchez jusqu’à l’arrêt Place de la République', ar: 'امشِ إلى محطة ساحة الجمهورية', en: 'Walk to Place de la République stop' } },
      { kind: 'ride', min: 41, label: { fr: 'Prenez le bus vers La Marsa', ar: 'اركب الحافلة باتجاه المرسى', en: 'Take the bus toward La Marsa' } },
      { kind: 'walk', min: 4, label: { fr: 'Descendez à La Marsa centre', ar: 'انزل في وسط المرسى', en: 'Get off at La Marsa centre' } }
    ]
  }
];

// Route types available (maps backend mode names to UI display)
// Backend modes: bus, tram, metro, train, louaj, taxi, walk
// transit mode is used for bus/train combinations
export const routeTypes = {
  'train': { id: 'train', badge: 'TGM', color: '#1F6F8B' },
  'bus': { id: 'bus', badge: 'Bus', color: '#2E7D4F' },
  'transit': { id: 'transit', badge: 'Bus', color: '#2E7D4F' },
  'walk': { id: 'walk', badge: 'Marche', color: '#888E92' },
  'louaj': { id: 'louaj', badge: 'Louage', color: '#D7261E' },
  'taxi': { id: 'taxi', badge: 'Taxi', color: '#F4B400' },
};

export const modeColors = {
  train: '#1F6F8B',
  bus: '#2E7D4F',
  tram: '#2E7D4F',
  metro: '#2E7D4F',
  louaj: '#D7261E',
  taxi: '#F4B400',
  walk: '#888E92',
  transfer: '#888E92',
};

// Default modes to search
// Include louage so shared-louage routing is attempted by default
export const defaultModes = ['train', 'bus', 'louaj'];

// Helper to normalize mode from API response
function normalizeMode(mode) {
  if (!mode) return 'bus';
  const m = String(mode).toLowerCase();
  if (m === 'transit' || m === 'bus' || m === 'rfr' || m === 'tram' || m === 'metro') return 'bus';
  if (m === 'train' || m === 'tgm') return 'train';
  if (m === 'louaj' || m === 'louage' || m === 'louage_red' || m === 'louage_blue' || m === 'louage_green') return 'louaj';
  if (m === 'taxi') return 'taxi';
  return 'bus';
}

function modeLabelFr(mode) {
  return {train:'TGM/Train',bus:'Bus',louaj:'Louage',taxi:'Taxi',walk:'Marche'}[mode] || mode;
}
function modeBadge(mode) {
  return {train:'TGM/Train',bus:'Bus',louaj:'Louage',taxi:'Taxi',walk:'Marche'}[mode] || mode;
}

function legIdentifier(leg) {
  const id = leg.mode_id || leg.line_id || leg.line || leg.route_short_name || leg.id || null;
  const op = leg.operator || leg.agency || '';
  if (id && op) return `${op} · ${id}`;
  if (id) return String(id);
  if (op) return String(op);
  return '—';
}

// kept for potential future route-detail rendering
// placeholder removed in CI cleanup

function legStationNames(leg) {
  const out = [];
  const add = (v) => { const s = (v || '').trim(); if (s) out.push(s); };
  add(leg.from_name);
  add(leg.to_name);
  if (Array.isArray(leg.intermediate_stops)) {
    for (const s of leg.intermediate_stops) add(typeof s === 'string' ? s : (s?.name || ''));
  }
  return out;
}

function modeFareDinars(leg) {
  const f = leg.fare_dinars;
  if (typeof f === 'number' && Number.isFinite(f) && f > 0) return f;
  const a = leg.fare;
  if (typeof a === 'object') {
    if (typeof a.dinars === 'number') return a.dinars;
    if (typeof a.value === 'number') return a.value;
  }
  if (typeof a === 'number' && Number.isFinite(a) && a > 0) return a;
  return null;
}

// Helper to build path array from legs geometry
// API returns geometry as [lat, lon] pairs within each leg
function buildPathFromLegs(legs) {
  const path = [];
  if (!legs || !Array.isArray(legs)) return path;
  
  for (const leg of legs) {
    if (leg.geometry && Array.isArray(leg.geometry)) {
      for (const point of leg.geometry) {
        if (Array.isArray(point) && point.length >= 2) {
          // Geometry is [lat, lon] format
          path.push([point[0], point[1]]);
        }
      }
    }
  }
  return path;
}

// Helper to format a route from API response
// API returns itineraries with legs that have geometry points
export function formatRoute(apiRoute) {
  const rawMode = apiRoute.mode || apiRoute.type || 'transit';
  const type = normalizeMode(rawMode);
  const routeType = routeTypes[type] || routeTypes.bus;
  
  // Build path from legs geometry (API returns legs, not steps for geometry)
  const legs = apiRoute.legs || apiRoute.steps || [];
  const path = buildPathFromLegs(legs);
  const isTaxi = rawMode === 'taxi';
  const totalFareRaw = modeFareDinars({fare_dinars: apiRoute.fare_dinars, fare: apiRoute.fare});
  const legsFare = legs.reduce((sum, leg) => sum + (modeFareDinars(leg) || 0), 0);
  const fareDinars = totalFareRaw || legsFare || null;
  
  return {
    id: type + '_' + Math.random().toString(36).slice(2, 7),
    rawMode,
    mode: type,
    badge: isTaxi ? 'Taxi' : (routeType.badge || modeBadge(type)),
    color: routeType.color || '#1F6F8B',
    minutes: Math.round((apiRoute.duration_min || apiRoute.duration || 0)),
    depart: apiRoute.depart_time || '--:--',
    arrive: apiRoute.arrive_time || '--:--',
    fare_dinars: fareDinars,
    path,
    label: apiRoute.label || '',
    identifier: isTaxi ? 'Taxi' : null,
    steps: legs.map((leg, i) => {
      const isWalk = leg.type === 'walk';
      const mode = isWalk ? 'walk' : normalizeMode(leg.mode || leg.type || 'bus');
      const identifier = null;
      const stations = legStationNames(leg);
      const label = {
        fr: leg.label?.fr || leg.name?.fr || leg.from_name || `Étape ${i + 1}`,
        ar: leg.label?.ar || leg.name?.ar || leg.from_name || `الخطوة ${i + 1}`,
        en: leg.label?.en || leg.name?.en || leg.from_name || `Step ${i + 1}`
      };
      return { kind: isWalk ? 'walk' : 'ride', mode, min: Math.round((leg.duration_min || 0)), identifier, stations, fare_dinars: modeFareDinars(leg), label };
    })
  };
}

// Normalize API response to routes array
export function normalizeRoutes(apiResponse) {
  if (!apiResponse || !apiResponse.itineraries) return [];
  const items = apiResponse.itineraries.map(formatRoute);
  items.sort((a, b) => {
    if (a.minutes !== b.minutes) return a.minutes - b.minutes;
    return (a.fare_dinars || 1e9) - (b.fare_dinars || 1e9);
  });
  items.forEach((it, idx) => { it.id = it.mode + '_' + (idx + 1); });
  return items;
}

export { modeLabelFr, modeBadge };