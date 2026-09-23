import{describe,expect,it,vi}from'vitest';import{LocalLocationRepository}from'../../src/api/LocalLocationRepository';
const row={facility_id:'550e8400-e29b-41d4-a716-446655440000',canonical_name:'Local V2 Fixture',city:'North Coast',country_code:'DK',category:'dairy',source_type:'official',publication_profile:'official',factual_review_status:'reviewed',privacy_screening_status:'passed',project_approval:'approved',reviewer_role:null,publication_warning:null,display_precision:'city',latitude:55,longitude:10,first_observed_at:null,last_observed_at:'2026-01-01T00:00:00Z',observation_count:1,lifecycle_status:'active_observed',provenance_source_id:'source-1',provenance_source:null,provenance_source_name:'Synthetic local source',provenance_source_url:'https://example.test/source',provenance_retrieved_at:'2026-01-01T00:00:00Z',source_rights_status:'cleared',release_id:'rel-1',release_ruleset_version:'rules-1'};
const response=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json'}});const envelope=(data=[row],meta={release_id:'rel-1',ruleset_version:'rules-1',profile:'official',next_cursor:null,coverage_note:'Local promoted release.'})=>({data,api_version:'v2',meta});
describe('LocalLocationRepository',()=>{it('maps a valid Rust-shaped envelope',async()=>{const result=await new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope()))).list();expect(result.locations[0]).toMatchObject({id:row.facility_id,name:'Local V2 Fixture',lat:55});});it('fails closed when no release is promoted',async()=>{await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope([],{release_id:null,profile:'official',coverage_note:'No promoted release.'})))).list()).rejects.toMatchObject({kind:'no-release'});});it('classifies server failures as unavailable',async()=>{await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response({},503))).list()).rejects.toMatchObject({kind:'unavailable',status:503});});it('rejects malformed or restricted payloads',async()=>{await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response({...envelope(),api_version:'v1'}))).list()).rejects.toMatchObject({kind:'invalid-contract'});await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope([{...row,privacy_screening_status:'failed'}])))).list()).rejects.toMatchObject({kind:'invalid-contract'});});});
describe('LocalLocationRepository query contract', () => {
  it('passes server-side search, region, supported filters, and opaque cursor', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(envelope([], { ...envelope().meta, next_cursor: 'cursor-2' })));
    const result = await new LocalLocationRepository(fetcher).list('official', { q: 'North Coast', country_code: 'DK', region: 'North Coast', category: 'dairy', source_type: 'official', display_precision: 'city', lifecycle_status: 'active_observed', min_lon: 8, min_lat: 54, max_lon: 13, max_lat: 58, cursor: 'cursor-1' });
    const request = String(fetcher.mock.calls[0]?.[0]);
    expect(request).toContain('profile=official');
    expect(request).toContain('q=North+Coast');
    expect(request).toContain('country_code=DK');
    expect(request).toContain('region=North+Coast');
    expect(request).toContain('category=dairy');
    expect(request).toContain('source_type=official');
    expect(request).toContain('display_precision=city');
    expect(request).toContain('lifecycle_status=active_observed');
    expect(request).toContain('min_lon=8');
    expect(request).toContain('max_lat=58');
    expect(request).toContain('cursor=cursor-1');
    expect(result.nextCursor).toBe('cursor-2');
  });
  it('retains compatibility offset while allowing the preferred cursor to remain explicit', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(envelope([], { ...envelope().meta, next_cursor: null })));
    await new LocalLocationRepository(fetcher).list('official', { offset: 20, limit: 10 });
    const request = String(fetcher.mock.calls[0]?.[0]);
    expect(request).toContain('offset=20');
    expect(request).toContain('limit=10');
    expect(request).not.toContain('cursor=');
  });

  it('keeps global search and bounded viewport queries separate', async () => {
    const globalFetcher = vi.fn().mockResolvedValue(response(envelope()));
    const viewportFetcher = vi.fn().mockResolvedValue(response(envelope()));
    await new LocalLocationRepository(globalFetcher).list('official', { q: 'North Coast' });
    await new LocalLocationRepository(viewportFetcher).list('official', { min_lon: 8, min_lat: 54, max_lon: 13, max_lat: 58 });
    const globalRequest = new URL(String(globalFetcher.mock.calls[0]?.[0]), 'https://example.test');
    const viewportRequest = new URL(String(viewportFetcher.mock.calls[0]?.[0]), 'https://example.test');
    expect(globalRequest.searchParams.get('q')).toBe('North Coast');
    expect(['min_lon', 'min_lat', 'max_lon', 'max_lat'].some(key => globalRequest.searchParams.has(key))).toBe(false);
    expect(viewportRequest.searchParams.has('q')).toBe(false);
    expect(['min_lon', 'min_lat', 'max_lon', 'max_lat'].every(key => viewportRequest.searchParams.has(key))).toBe(true);
  });
});

describe('current V2 wire edge cases', () => {
  it('accepts a null canonical name and exposes an explicit safe display label', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(envelope([{ ...row, canonical_name: null }])));
    await expect(new LocalLocationRepository(fetcher).list()).resolves.toMatchObject({ locations: [{ name: 'Unnamed candidate record' }] });
  });
  it('classifies structured server failures for first-class UI states', async () => {
    const unavailable = vi.fn().mockResolvedValue(new Response(JSON.stringify({ api_version: 'v2', error: { code: 'database_pool_unavailable', message: 'database unavailable' } }), { status: 503 }));
    await expect(new LocalLocationRepository(unavailable).list()).rejects.toMatchObject({ kind: 'unavailable', code: 'database_pool_unavailable', status: 503 });
    const restricted = vi.fn().mockResolvedValue(new Response(JSON.stringify({ api_version: 'v2', error: { code: 'location_not_found', message: 'location not found' } }), { status: 404 }));
    await expect(new LocalLocationRepository(restricted).detail(row.facility_id)).rejects.toMatchObject({ kind: 'restricted', code: 'location_not_found', status: 404 });
  });
});

describe('community list safety', () => {
  const community = { ...row, source_type: 'user_submitted', publication_profile: 'community', factual_review_status: 'unreviewed', project_approval: 'pending', publication_warning: 'Unreviewed community claim — not verified by Until Every Cage' };
  const communityMeta = { ...envelope().meta, profile: 'community' };
  it('accepts screened unreviewed claims only in the explicit community profile and retains review context', async () => {
    const result = await new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope([community], communityMeta)))).list('community');
    expect(result.locations[0]).toMatchObject({ evidence: { sourceType: 'user_submitted', factualReviewStatus: 'unreviewed', projectApproval: 'pending', publicationWarning: community.publication_warning, sourceUrl: row.provenance_source_url } });
    await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope([community])))).list()).rejects.toMatchObject({ kind: 'invalid-contract' });
  });
  it.each([{ privacy_screening_status: 'failed' }, { factual_review_status: 'rejected' }])('rejects unsafe community rows: %o', async (change) => {
    await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope([{ ...community, ...change }], communityMeta)))).list('community')).rejects.toMatchObject({ kind: 'invalid-contract' });
  });
  it('rejects a row profile that disagrees with the requested envelope', async () => {
    await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope([{ ...row, publication_profile: 'community' }])))).list()).rejects.toMatchObject({ kind: 'invalid-contract' });
  });
  it('rejects a non-web source URL before it can become a detail link', async () => {
    await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope([{ ...row, provenance_source_url: 'javascript:alert(1)' }])))).list()).rejects.toMatchObject({ kind: 'invalid-contract' });
  });
  it('retains source rights context and rejects unknown rights states', async () => {
    await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope()))).list()).resolves.toMatchObject({ locations: [{ evidence: { sourceRightsStatus: 'cleared', provenanceSource: null } }] });
    await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope([{ ...row, source_rights_status: 'restricted' }])))).list()).rejects.toMatchObject({ kind: 'invalid-contract' });
  });
});
