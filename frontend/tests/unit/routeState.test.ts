import { describe, expect, it } from 'vitest';
import { mapHrefFromHash, mapHrefFromParams, parseRoute, safeMapHref, serializeRoute } from '../../src/app/routeState';

describe('routeState', () => {
  it('exposes local secure routes only under the explicit development gate without retaining credentials', () => {
    const fragment = '#/secure-inbox?case_id=18c6ef3a-28cd-4c8e-a9bb-3951f45f210d&access_secret=' + '2'.repeat(64);
    expect(parseRoute(fragment).kind).toBe('not-found');
    expect(parseRoute(fragment, true)).toEqual({ kind: 'secure-inbox' });
    expect(parseRoute('#/secure-review', true)).toEqual({ kind: 'secure-review' });
    expect(serializeRoute({ kind: 'secure-inbox' })).toBe('#/secure-inbox');
    expect(mapHrefFromHash(fragment)).toBe('#/map');
  });
  it('defaults the root and empty hash to the map', () => {
    expect(parseRoute('')).toEqual({ kind: 'map' });
    expect(parseRoute('#/')).toEqual({ kind: 'map' });
    expect(parseRoute('#/map')).toEqual({ kind: 'map' });
    expect(parseRoute('#/map?release_id=release-2026-10')).toEqual({ kind: 'map', releaseId: 'release-2026-10' });
    expect(serializeRoute({ kind: 'map', releaseId: 'release-2026-10' })).toBe('#/map?release_id=release-2026-10');
  });

  it('parses the database route independently', () => {
    expect(parseRoute('#/database')).toEqual({ kind: 'database', returnMapHref: '#/map' });
    expect(parseRoute('#/database?lat=44.5&lon=8.1&z=5&basemap=satellite&release_id=r-2026-10&selected=stale')).toEqual({ kind: 'database', releaseId: 'r-2026-10', returnMapHref: '#/map?lat=44.5&lon=8.1&z=5&basemap=satellite&release_id=r-2026-10' });
    const databaseRoute = { kind: 'database' as const, releaseId: 'r-2026-10', returnMapHref: '#/map?lat=44.5&lon=8.1&z=5&basemap=satellite&release_id=r-2026-10' };
    expect(parseRoute(serializeRoute(databaseRoute))).toEqual(databaseRoute);
  });

  it('keeps the manifesto route and opens legacy FAQ and methodology URLs in the matching FAQ section', () => {
    expect(parseRoute('#/about')).toEqual({ kind: 'about', section: 'overview' });
    expect(parseRoute('#/about/manifesto')).toEqual({ kind: 'about', section: 'overview' });
    expect(serializeRoute(parseRoute('#/about/manifesto') as { kind: 'about'; section: 'overview' })).toBe('#/about');
    expect(parseRoute('#/about?section=sources')).toEqual({ kind: 'about', section: 'sources' });
    expect(parseRoute('#/about/sources')).toEqual({ kind: 'faq', section: 'technology' });
    expect(parseRoute('#/methodology')).toEqual({ kind: 'faq', section: 'technology' });
    expect(parseRoute('#/about/faq')).toEqual({ kind: 'faq', section: 'records' });
    expect(parseRoute('#/about/help')).toEqual({ kind: 'faq', section: 'help' });
    expect(parseRoute('#/faq?section=contributions')).toEqual({ kind: 'faq', section: 'contributions' });
  });

  it('preserves only validated map context when returning from Database or other routes', () => {
    const context = new URLSearchParams('lat=44.5&lon=8.1&z=5&pitch=32&bearing=-12&basemap=satellite&list=open&release_id=release-2026-10&q=private%20search&scenario=default&f1a=field&extra=unsafe');
    context.set('selected', 'stale-record');
    expect(mapHrefFromParams(context)).toBe('#/map?lat=44.5&lon=8.1&z=5&pitch=32&bearing=-12&basemap=satellite&list=open&release_id=release-2026-10');
    expect(mapHrefFromParams(context, 'release-2026-10', 'target-record')).toBe('#/map?lat=44.5&lon=8.1&z=5&pitch=32&bearing=-12&basemap=satellite&list=open&selected=target-record&release_id=release-2026-10');
    expect(mapHrefFromHash('#/database?lat=44.5&lon=8.1&z=5&pitch=32&bearing=-12&basemap=satellite&list=open&release_id=release-2026-10&q=private&extra=unsafe')).toBe('#/map?lat=44.5&lon=8.1&z=5&pitch=32&bearing=-12&basemap=satellite&list=open&release_id=release-2026-10');
    expect(mapHrefFromHash('#/database?lat=100&lon=181&z=99&pitch=90&bearing=181&list=closed&release_id=bad/value')).toBe('#/map');
    expect(safeMapHref('#/map?lat=44.5&lon=8.1&q=private&f1a=field')).toBe('#/map?lat=44.5&lon=8.1');
    expect(safeMapHref('#/database?lat=44.5')).toBeUndefined();
  });

  it('keeps API and downloads aliases with map context', () => {
    for (const kind of ['api', 'downloads'] as const) {
      const route = { kind, returnMapHref: '#/map?lat=44.5&lon=8.1' };
      expect(parseRoute(serializeRoute(route))).toEqual(route);
    }
  });

  it('retains the old API URL and uses the Database destination for new links', () => {
    expect(parseRoute('#/about/api')).toEqual({ kind: 'api' });
    expect(parseRoute('#/database/api')).toEqual({ kind: 'api' });
    expect(serializeRoute({ kind: 'api' })).toBe('#/database/api');
    expect(parseRoute('#/database/downloads')).toEqual({ kind: 'downloads' });
    expect(parseRoute('#/about/faq')).toEqual({ kind: 'faq', section: 'records' });
    expect(parseRoute('#/about/help')).toEqual({ kind: 'faq', section: 'help' });
  });

  it('parses the contribution hub, form subroutes, and bug route', () => {
    expect(parseRoute('#/contribute?target=synthetic-record')).toEqual({ kind: 'contribute', targetRecordId: 'synthetic-record' });
    expect(parseRoute('#/contribute/facility')).toEqual({ kind: 'community', page: 'form', formKind: 'facility' });
    expect(parseRoute('#/contribute/evidence?target=synthetic-record&map=%23%2Fmap%3Flat%3D44.5%26lon%3D8.1%26q%3Dprivate')).toEqual({ kind: 'community', page: 'form', formKind: 'evidence', targetRecordId: 'synthetic-record', returnMapHref: '#/map?lat=44.5&lon=8.1' });
    expect(parseRoute('#/contribute/evidence?target=4c4708fa-cdde-51dd-b7b9-30c907f7acce')).toMatchObject({ kind: 'community', page: 'form', formKind: 'evidence', targetRecordId: '4c4708fa-cdde-51dd-b7b9-30c907f7acce' });
    expect(parseRoute('#/contribute/privacy-removal')).toEqual({ kind: 'community', page: 'form', formKind: 'privacy_removal' });
    expect(parseRoute('#/contribute/bug')).toEqual({ kind: 'bug-report' });
    expect(serializeRoute({ kind: 'community', page: 'form', formKind: 'evidence', targetRecordId: 'synthetic-record' })).toBe('#/contribute/evidence?target=synthetic-record');
  });

  it('keeps all five contribution task routes addressable', () => {
    const paths = [
      ['facility', 'facility'], ['evidence', 'evidence'], ['correction', 'correction'],
      ['duplicate', 'duplicate'], ['privacy_removal', 'privacy-removal'],
    ] as const;
    for (const [formKind, path] of paths) {
      const route = { kind: 'community', page: 'form', formKind } as const;
      expect(parseRoute(`#/contribute/${path}`)).toEqual(route);
      expect(serializeRoute(route)).toBe(`#/contribute/${path}`);
    }
  });

  it('round-trips all selector types with record and map context, retaining old aliases', () => {
    for (const formKind of ['facility', 'evidence', 'correction', 'duplicate', 'privacy_removal', 'bug'] as const) {
      const route = { kind: 'contribute' as const, formKind, targetRecordId: 'synthetic-record', returnMapHref: '#/map?lat=44.5&lon=8.1' };
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
    const route = { kind: 'community' as const, page: 'claim-detail' as const, claimId: 'claim-42', releaseId: 'release-2026-10', returnMapHref: '#/map?lat=44.5&lon=8.1' };
    const serialized = serializeRoute(route);
    expect(serialized).toContain('release_id=release-2026-10');
    expect(parseRoute(serialized)).toEqual(route);
  });

  it('preserves record links and rejects unsupported paths', () => {
    expect(parseRoute('#/records/syn-north-star?source=shared')).toEqual({ kind: 'record', facilityId: 'syn-north-star', returnMapHref: '#/map' });
    expect(parseRoute('#/locations/syn-river-meadow')).toEqual({ kind: 'record', facilityId: 'syn-river-meadow', returnMapHref: '#/map' });
    expect(parseRoute('#/search?q=eggs')).toEqual({ kind: 'not-found', fragment: '/search?q=eggs' });
  });

  it('round-trips a public record snapshot with profile and release membership', () => {
    const route = { kind: 'record' as const, facilityId: '18c6ef3a-28cd-4c8e-a9bb-3951f45f210d', profile: 'community' as const, releaseId: 'synthetic-release', returnMapHref: '#/map?release_id=synthetic-release' };
    expect(parseRoute(serializeRoute(route))).toEqual(route);
    expect(parseRoute('#/records/synthetic?profile=private&release_id=bad/value')).toEqual({kind:'record',facilityId:'synthetic',returnMapHref:'#/map'});
  });

  it('keeps legacy location routes and hash fallback below a preview base path', () => {
    expect(parseRoute('#/locations/syn-river-meadow')).toEqual({ kind: 'record', facilityId: 'syn-river-meadow', returnMapHref: '#/map' });
    const previewUrl = new URL('https://example.test/v2-preview/#/records/syn-north-star');
    expect(parseRoute(previewUrl.hash)).toEqual({ kind: 'record', facilityId: 'syn-north-star', returnMapHref: '#/map' });
  });

  it('rejects malformed public claim links and does not guess unsupported paths', () => {
    expect(parseRoute('#/community/claim?id=')).toEqual({ kind: 'not-found', fragment: '/community/claim?id=' });
    expect(parseRoute('#/community/claim?id=synthetic-claim')).toEqual({ kind: 'not-found', fragment: '/community/claim?id=synthetic-claim' });
    expect(parseRoute('#/community/claim?id=synthetic-claim&release_id=unsafe%2Fvalue')).toEqual({ kind: 'not-found', fragment: '/community/claim?id=synthetic-claim&release_id=unsafe%2Fvalue' });
    expect(parseRoute('#/search?q=eggs')).toEqual({ kind: 'not-found', fragment: '/search?q=eggs' });
  });
});
