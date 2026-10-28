// API client for bledi.tn backend
// API base URL - change this if backend runs on different host/port

const API_BASE_URL = '/api/v1';

// Utility to build full URL
const apiUrl = (endpoint) => {
  const base = API_BASE_URL.replace(/\/+$/, '');
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${base}${path}`;
};

// The accounts service sits behind the same origin as the app: the nginx gateway routes
// /api/v1/* to it, and the dev server proxies the same paths. Relative URLs keep one
// origin in production and in development.
const ACCOUNTS_BASE = '/api/v1';

import { goto } from '$app/navigation';
import { resolve } from '$app/paths';

// Fetch itineraries for a route
export async function fetchRoutePlan({ startLat, startLon, endLat, endLon, modes = ['bus', 'train', 'louaj'] }) {
  const params = new URLSearchParams({
    start_lat: String(startLat),
    start_lon: String(startLon),
    end_lat: String(endLat),
    end_lon: String(endLon),
    modes_include: modes.join(','),
    max_itineraries: 6
  });

  const response = await fetch(apiUrl(`/route/plan?${params}`));
  if (!response.ok) throw new Error(`Failed to fetch route: ${response.status}`);
  return response.json();
}

// Fetch map geometry for routes
export async function fetchRouteGeometry({ startLat, startLon, endLat, endLon, objective = 'fastest' }) {
  const params = new URLSearchParams({
    start_lat: String(startLat),
    start_lon: String(startLon),
    end_lat: String(endLat),
    end_lon: String(endLon),
    objective
  });

  const response = await fetch(apiUrl(`/route/transit?${params}`));
  if (!response.ok) throw new Error(`Failed to fetch geometry: ${response.status}`);
  return response.json();
}

// Geocode a place name
export async function geocode(query, limit = 3) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const response = await fetch(apiUrl(`/geocode?${params}`));
  if (!response.ok) throw new Error(`Geocode failed: ${response.status}`);
  return response.json();
}

// Fetch stations
export async function fetchStations() {
  const response = await fetch(apiUrl('/stations'));
  if (!response.ok) throw new Error(`Failed to fetch stations: ${response.status}`);
  return response.json();
}

// Fetch lines
export async function fetchLines() {
  const response = await fetch(apiUrl('/lines'));
  if (!response.ok) throw new Error(`Failed to fetch lines: ${response.status}`);
  return response.json();
}

// Health check
export async function healthCheck() {
  const response = await fetch(apiUrl('/health'));
  if (!response.ok) throw new Error(`Health check failed: ${response.status}`);
  return response.json();
}

// ---- accounts ----

export async function accounts(path, { token, method = 'GET', body, form } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(`${ACCOUNTS_BASE}${path}`, {
      method,
      signal: controller.signal,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(body ? { 'Content-Type': 'application/json' } : {})
      },
      // A form carries its own multipart boundary, so no Content-Type is set for it.
      body: form ?? (body ? JSON.stringify(body) : undefined)
    });
    if (response.status === 401) {
      localStorage.removeItem('bledi_auth');
      await goto(resolve('/login'));
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `Request failed: ${response.status}`);
    }
    if (response.status === 204) return null;
    return response.json();
  } finally {
    clearTimeout(timeout);
  }
}

export async function loginUser({ email, password }) {
  return accounts('/auth/login', { method: 'POST', body: { email, password } });
}

export async function registerUser({ email, password, display_name }) {
  return accounts('/auth/register', { method: 'POST', body: { email, password, display_name } });
}

/**
 * Fetches a photo. The media endpoint needs the caller's token, so an <img> tag cannot
 * load it: the bytes are fetched here and shown through an object URL.
 */
export async function fetchMedia(token, url) {
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw new Error(`Photo unavailable: ${response.status}`);
  return response.blob();
}
