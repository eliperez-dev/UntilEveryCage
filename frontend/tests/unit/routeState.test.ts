import { describe, expect, it } from 'vitest';
import { parseRoute, serializeRoute } from '../../src/app/routeState';

describe('routeState', () => {
  it('defaults the root and empty hash to the map', () => {
    expect(parseRoute('')).toEqual({ kind: 'map' });
    expect(parseRoute('#/')).toEqual({ kind: 'map' });
    expect(parseRoute('#/map')).toEqual({ kind: 'map' });
  });

  it('parses the database route independently', () => {
    expect(parseRoute('#/database')).toEqual({ kind: 'database' });
  });

  it('keeps the requested About hierarchy and the old methodology alias', () => {
    expect(parseRoute('#/about')).toEqual({ kind: 'about', section: 'overview' });
    expect(parseRoute('#/about/manifesto')).toEqual({ kind: 'about', section: 'overview' });
    expect(serializeRoute(parseRoute('#/about/manifesto') as { kind: 'about'; section: 'overview' })).toBe('#/about');
    expect(parseRoute('#/about/sources')).toEqual({ kind: 'methodology' });
    expect(parseRoute('#/methodology?map=%23%2Fmap%3Ff1a%3Dfield')).toEqual({ kind: 'methodology', returnMapHref: '#/map?f1a=field' });
    expect(serializeRoute({ kind: 'methodology' })).toBe('#/methodology');
    expect(serializeRoute({ kind: 'methodology', returnMapHref: '#/map?f1a=field' })).toBe('#/methodology?map=%23%2Fmap%3Ff1a%3Dfield');
  });

  it('parses the contribution hub, form subroutes, and bug route', () => {
    expect(parseRoute('#/contribute?target=synthetic-record')).toEqual({ kind: 'contribute', targetRecordId: 'synthetic-record' });
    expect(parseRoute('#/contribute/facility')).toEqual({ kind: 'community', page: 'form', formKind: 'facility' });
    expect(parseRoute('#/contribute/evidence?target=synthetic-record&map=%23%2Fmap%3Ff1a%3Dfield')).toEqual({ kind: 'community', page: 'form', formKind: 'evidence', targetRecordId: 'synthetic-record', returnMapHref: '#/map?f1a=field' });
    expect(parseRoute('#/contribute/privacy-removal')).toEqual({ kind: 'community', page: 'form', formKind: 'privacy_removal' });
    expect(parseRoute('#/contribute/bug')).toEqual({ kind: 'bug-report' });
    expect(serializeRoute({ kind: 'community', page: 'form', formKind: 'evidence', targetRecordId: 'synthetic-record' })).toBe('#/contribute/evidence?target=synthetic-record');
  });

  it('round-trips all selector types with record and map context, retaining old aliases', () => {
    for (const formKind of ['facility', 'evidence', 'correction', 'duplicate', 'privacy_removal', 'bug'] as const) {
      const route = { kind: 'contribute' as const, formKind, targetRecordId: 'synthetic-record', returnMapHref: '#/map?f1a=field' };
      expect(parseRoute(serializeRoute(route))).toEqual(route);
    }
    expect(parseRoute('#/contribute?type=unsupported')).toEqual({ kind: 'contribute' });
  });

  it('preserves receipt, review, and release-pinned community routes', () => {
    expect(parseRoute('#/contribution-status')).toEqual({ kind: 'community', page: 'status' });
    expect(parseRoute('#/community')).toEqual({ kind: 'community', page: 'claims' });
    const claimRoute = { kind: 'community' as const, page: 'claim-detail' as const, claimId: 'synthetic-claim', releaseId: 'synthetic-release' };
    const link = '#/community/claim?id=synthetic-claim&release_id=synthetic-release';
    expect(parseRoute(link)).toEqual(claimRoute);
    expect(serializeRoute(claimRoute)).toBe(link);
    expect(parseRoute('#/contribution-review')).toEqual({ kind: 'community', page: 'review' });
  });

  it('round-trips a public claim link with its explicit release context', () => {
    const route = { kind: 'community' as const, page: 'claim-detail' as const, claimId: 'claim-42', releaseId: 'release-2026-10', returnMapHref: '#/map?f1a=field' };
    const serialized = serializeRoute(route);
    expect(serialized).toContain('release_id=release-2026-10');
    expect(parseRoute(serialized)).toEqual(route);
  });

  it('preserves record links and rejects unsupported paths', () => {
    expect(parseRoute('#/records/syn-north-star?source=shared')).toEqual({ kind: 'record', facilityId: 'syn-north-star' });
    expect(parseRoute('#/locations/syn-river-meadow')).toEqual({ kind: 'record', facilityId: 'syn-river-meadow' });
    expect(parseRoute('#/search?q=eggs')).toEqual({ kind: 'not-found', fragment: '/search?q=eggs' });
  });

  it('keeps legacy location routes and hash fallback below a preview base path', () => {
    expect(parseRoute('#/locations/syn-river-meadow')).toEqual({ kind: 'record', facilityId: 'syn-river-meadow' });
    const previewUrl = new URL('https://example.test/v2-preview/#/records/syn-north-star');
    expect(parseRoute(previewUrl.hash)).toEqual({ kind: 'record', facilityId: 'syn-north-star' });
  });

  it('rejects malformed public claim links and does not guess unsupported paths', () => {
    expect(parseRoute('#/community/claim?id=')).toEqual({ kind: 'not-found', fragment: '/community/claim?id=' });
    expect(parseRoute('#/community/claim?id=synthetic-claim')).toEqual({ kind: 'not-found', fragment: '/community/claim?id=synthetic-claim' });
    expect(parseRoute('#/community/claim?id=synthetic-claim&release_id=unsafe%2Fvalue')).toEqual({ kind: 'not-found', fragment: '/community/claim?id=synthetic-claim&release_id=unsafe%2Fvalue' });
    expect(parseRoute('#/search?q=eggs')).toEqual({ kind: 'not-found', fragment: '/search?q=eggs' });
  });
});
