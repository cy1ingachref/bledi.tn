// The transport catalog is a static JSON bundle shipped with the site, so the map shows the
// whole network even when the backend is unreachable.

const CATALOG_URL = '/transport_catalog.json';

const MODE_COLORS = {
  bus: '#F4B400',
  louage: '#D7261E',
  metro: '#1F6F8B',
  rail: '#9B59B6',
  train: '#7B2D8E',
  taxi: '#D7261E',
  tram: '#1F6F8B',
  louaj: '#D7261E',
  unknown: '#586972',
};

export function modeColor(mode) {
  return MODE_COLORS[mode] ?? MODE_COLORS.unknown;
}

let pending = null;

/** The catalog, fetched once per page load. A failed fetch is not cached, so a retry works. */
export function loadCatalog() {
  pending ??= fetch(CATALOG_URL)
    .then((response) => {
      if (!response.ok) throw new Error(`catalog request failed: ${response.status}`);
      return response.json();
    })
    .catch((error) => {
      pending = null;
      throw error;
    });
  return pending;
}
