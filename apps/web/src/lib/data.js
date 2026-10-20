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
  'walk': { id: 'walk', badge: 'Marche', color: '#888E92' }
};

// Default modes to search 
// 'train' for TGM/light rail, 'bus' for buses
export const defaultModes = ['train', 'bus'];

// Helper to normalize mode from API response
function normalizeMode(mode) {
  if (!mode) return 'bus';
  if (mode === 'transit' || mode === 'bus') return 'bus';
  if (mode === 'train') return 'train';
  return mode;
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
  const type = normalizeMode(apiRoute.mode);
  const routeType = routeTypes[type] || routeTypes.bus;
  
  // Build path from legs geometry (API returns legs, not steps for geometry)
  const legs = apiRoute.legs || apiRoute.steps || [];
  const path = buildPathFromLegs(legs);
  
  return {
    id: type,
    badge: routeType.badge,
    color: routeType.color,
    minutes: Math.round((apiRoute.duration_min || apiRoute.duration || 0)),
    depart: apiRoute.depart_time || '--:--',
    arrive: apiRoute.arrive_time || '--:--',
    path: path,
    steps: (apiRoute.steps || apiRoute.legs || []).map((leg, i) => ({
      kind: leg.type === 'walk' ? 'walk' : 'ride',
      min: Math.round((leg.duration_min || 0)),
      label: {
        fr: leg.label?.fr || leg.name?.fr || leg.from_name || `Étape ${i + 1}`,
        ar: leg.label?.ar || leg.name?.ar || leg.from_name || `الخطوة ${i + 1}`,
        en: leg.label?.en || leg.name?.en || leg.from_name || `Step ${i + 1}`
      }
    }))
  };
}

// Normalize API response to routes array
export function normalizeRoutes(apiResponse) {
  if (!apiResponse || !apiResponse.itineraries) return [];
  return apiResponse.itineraries.map(formatRoute);
}