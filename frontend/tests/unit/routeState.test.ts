import { describe, expect, it } from 'vitest';
import { parseRoute, serializeRoute } from '../../src/app/routeState';

describe('routeState', () => {
  it('defaults the root and empty hash to the map', () => {
    expect(parseRoute('')).toEqual({ kind: 'map' });
    expect(parseRoute('#/')).toEqual({ kind: 'map' });
    expect(parseRoute('#/map')).toEqual({ kind: 'map' });
  });

  it('parses the database route', () => {
    expect(parseRoute('#/database')).toEqual({ kind: 'database' });
  });

  it('parses record routes and ignores unrelated query parameters', () => {
    expect(parseRoute('#/records/syn-north-star?source=shared')).toEqual({
      kind: 'record',
      facilityId: 'syn-north-star',
    });
  });

  it('keeps old location links compatible with record pages', () => {
    expect(parseRoute('#/locations/syn-river-meadow')).toEqual({
      kind: 'record',
      facilityId: 'syn-river-meadow',
    });
  });

  it('round-trips canonical routes', () => {
    expect(serializeRoute({ kind: 'map' })).toBe('#/map');
    expect(serializeRoute({ kind: 'database' })).toBe('#/database');
    expect(serializeRoute({ kind: 'record', facilityId: 'syn-river-meadow' })).toBe('#/records/syn-river-meadow');
  });

  it('supports hash fallback below a preview base path', () => {
    const previewUrl = new URL('https://example.test/v2-preview/#/records/syn-north-star');
    expect(parseRoute(previewUrl.hash)).toEqual({ kind: 'record', facilityId: 'syn-north-star' });
  });

  it('does not guess unsupported paths', () => {
    expect(parseRoute('#/search?q=eggs')).toEqual({ kind: 'not-found', fragment: '/search?q=eggs' });
  });
});
