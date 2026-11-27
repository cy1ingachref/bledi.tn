// The memories API. Every call goes through the accounts service, so every call needs the
// caller's token.

import { accounts } from './api.js';

/** The memories the caller owns, with their media URL. */
export async function listMemories(token) {
  return accounts('/memories', { token });
}

/** One memory. The owner gets the photo, anyone else gets the summary without it. */
export async function getMemory(token, id) {
  return accounts(`/memories/${id}`, { token });
}

/**
 * Creates a memory. The photo is sent as a multipart form, which the server checks and
 * stores under its own media root; the client never names the file.
 */
export async function createMemory(token, memory, photo) {
  const form = new FormData();
  form.append('lat', String(memory.lat));
  form.append('lon', String(memory.lon));
  form.append('unlock_radius_m', String(memory.unlock_radius_m));
  form.append('visibility', memory.visibility);
  if (memory.title) form.append('title', memory.title);
  if (memory.description) form.append('description', memory.description);
  form.append('photo', photo, photo.name || 'photo.jpg');

  return accounts('/memories', { token, method: 'POST', form });
}

export async function deleteMemory(token, id) {
  return accounts(`/memories/${id}`, { token, method: 'DELETE' });
}

/** Discovery only: these summaries carry no media URL, the photo needs unlocking. */
export async function fetchNearbyMemories(token, { lat, lon, radius_m }) {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    radius_m: String(radius_m)
  });
  return accounts(`/memories/nearby?${params}`, { token });
}

/** Claims a position and gets the memory back when the claim is inside the radius. */
export async function unlockMemory(token, id, { lat, lon }) {
  return accounts(`/memories/${id}/unlock`, { token, method: 'POST', body: { lat, lon } });
}
