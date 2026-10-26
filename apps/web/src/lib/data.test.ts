import { describe, it, expect } from 'vitest';
import { defaultModes, routeTypes } from '$lib/data.js';

describe('route mode defaults', () => {
  it('uses backend-supported modes and excludes invalid tgm', () => {
    expect(defaultModes).toContain('bus');
    expect(defaultModes).toContain('train');
    expect(defaultModes).not.toContain('tgm');
  });

  it('exposes route types used by the UI', () => {
    expect(routeTypes.bus).toBeDefined();
    expect(routeTypes.train).toBeDefined();
    expect(routeTypes.bus.badge).toBe('Bus');
    expect(routeTypes.train.badge).toBe('TGM');
  });
});
