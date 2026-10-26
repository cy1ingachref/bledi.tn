import { describe, it, expect } from 'vitest';

const originalFetch = globalThis.fetch;
let lastRequest = null;

function createOkResponse(body) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    clone: async () => createOkResponse(body)
  };
}

describe('fetchRoutePlan defaults', () => {
  it('sends backend-supported modes and excludes invalid tgm', async () => {
    globalThis.fetch = async (input, init) => {
      lastRequest = typeof input === 'string' ? input : input.url;
      return createOkResponse({ itineraries: [] });
    };

    const { fetchRoutePlan } = await import('./api.js');
    await fetchRoutePlan({
      startLat: 36.7989,
      startLon: 10.1827,
      endLat: 34.7394,
      endLon: 10.7604,
    });

    expect(lastRequest).toBeTruthy();
    const url = new URL(lastRequest, 'http://localhost:8000');
    const modes = url.searchParams.getAll('modes_include').flatMap((v) => v.split(','));
    expect(modes).toContain('bus');
    expect(modes).toContain('train');
    expect(modes).not.toContain('tgm');

    globalThis.fetch = originalFetch;
  });
});
