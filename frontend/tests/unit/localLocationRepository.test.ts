import{describe,expect,it,vi}from'vitest';import{LocalLocationRepository}from'../../src/api/LocalLocationRepository';
const row={facility_id:'550e8400-e29b-41d4-a716-446655440000',canonical_name:'Local V2 Fixture',city:'North Coast',country_code:'DK',category:'dairy',source_type:'official',publication_profile:'official',factual_review_status:'reviewed',privacy_screening_status:'passed',project_approval:'approved',reviewer_role:null,publication_warning:null,display_precision:'city',latitude:55,longitude:10,first_observed_at:null,last_observed_at:'2026-01-01T00:00:00Z',observation_count:1,lifecycle_status:'active_observed',provenance_source_id:'source-1',provenance_source_name:'Synthetic local source',provenance_source_url:'https://example.test/source',provenance_retrieved_at:'2026-01-01T00:00:00Z',release_id:'rel-1',release_ruleset_version:'rules-1'};
const response=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json'}});const envelope=(data=[row],meta={release_id:'rel-1',ruleset_version:'rules-1',profile:'official',next_cursor:null,coverage_note:'Local promoted release.'})=>({data,api_version:'v2',meta});
describe('LocalLocationRepository',()=>{it('maps a valid Rust-shaped envelope',async()=>{const result=await new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope()))).list();expect(result.locations[0]).toMatchObject({id:row.facility_id,name:'Local V2 Fixture',lat:55});});it('fails closed when no release is promoted',async()=>{await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope([],{release_id:null,profile:'official',coverage_note:'No promoted release.'})))).list()).rejects.toMatchObject({kind:'no-release'});});it('classifies HTTP failures',async()=>{await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response({},503))).list()).rejects.toMatchObject({kind:'http',status:503});});it('rejects malformed or restricted payloads',async()=>{await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response({...envelope(),api_version:'v1'}))).list()).rejects.toMatchObject({kind:'invalid-contract'});await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(response(envelope([{...row,privacy_screening_status:'failed'}])))).list()).rejects.toMatchObject({kind:'invalid-contract'});});});
describe('LocalLocationRepository query contract', () => {
  it('passes supported filters and the opaque cursor without inventing search semantics', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(envelope([], { ...envelope().meta, next_cursor: 'cursor-2' })));
    const result = await new LocalLocationRepository(fetcher).list('official', { country_code: 'DK', category: 'dairy', source_type: 'official', display_precision: 'city', lifecycle_status: 'active_observed', cursor: 'cursor-1' });
    const request = String(fetcher.mock.calls[0]?.[0]);
    expect(request).toContain('profile=official');
    expect(request).toContain('country_code=DK');
    expect(request).toContain('category=dairy');
    expect(request).toContain('source_type=official');
    expect(request).toContain('display_precision=city');
    expect(request).toContain('lifecycle_status=active_observed');
    expect(request).toContain('cursor=cursor-1');
    expect(result.nextCursor).toBe('cursor-2');
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
});
