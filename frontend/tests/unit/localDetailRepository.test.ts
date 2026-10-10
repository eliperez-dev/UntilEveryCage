import{describe,expect,it,vi}from'vitest';import{LocalLocationRepository}from'../../src/api/LocalLocationRepository';
const row={facility_id:'550e8400-e29b-41d4-a716-446655440000',canonical_name:'Detail Local Fixture',city:'North Coast',country_code:'DK',category:'dairy',source_type:'official',publication_profile:'official',factual_review_status:'reviewed',privacy_screening_status:'passed',project_approval:'approved',reviewer_role:null,publication_warning:null,display_precision:'city',latitude:55,longitude:10,first_observed_at:null,last_observed_at:'2026-01-01T00:00:00Z',observation_count:1,lifecycle_status:'active_observed',provenance_source_id:'source-1',provenance_source:null,provenance_source_name:'Synthetic local source',provenance_source_url:'https://example.test/source',provenance_retrieved_at:'2026-01-01T00:00:00Z',source_rights_status:'cleared',release_id:'rel-1',release_ruleset_version:'rules-1'};
const body=(data=row,meta={release_id:'rel-1',ruleset_version:'rules-1',release_created_at:'2026-01-01T00:00:00Z',profile:'official'})=>({data,api_version:'v2',meta});
describe('LocalLocationRepository detail',()=>{it('maps a valid detail envelope',async()=>{const fetcher=vi.fn().mockResolvedValue(new Response(JSON.stringify(body()),{status:200}));const result=await new LocalLocationRepository(fetcher).detail(row.facility_id);expect(result).toMatchObject({releaseId:'rel-1',profile:'official',location:{id:row.facility_id,name:'Detail Local Fixture'}});expect(fetcher).toHaveBeenCalledWith(`/api/v2/locations/${row.facility_id}?profile=official`,expect.any(Object));});it('rejects wrong profile and aborts',async()=>{const wrong=vi.fn().mockResolvedValue(new Response(JSON.stringify(body(row,{...body().meta,profile:'community'}))));await expect(new LocalLocationRepository(wrong).detail(row.facility_id)).rejects.toMatchObject({kind:'invalid-contract'});const controller=new AbortController();const fetcher=vi.fn().mockRejectedValue(new DOMException('aborted','AbortError'));await expect(new LocalLocationRepository(fetcher).detail(row.facility_id,'official',controller.signal)).rejects.toMatchObject({kind:'aborted'});});it('pins detail to release and rejects a different release',async()=>{const fetcher=vi.fn().mockResolvedValue(new Response(JSON.stringify(body()),{status:200}));await expect(new LocalLocationRepository(fetcher).detail(row.facility_id,'official',undefined,'rel-1')).resolves.toMatchObject({releaseId:'rel-1'});expect(fetcher).toHaveBeenCalledWith(`/api/v2/locations/${row.facility_id}?profile=official&release_id=rel-1`,expect.any(Object));const other=vi.fn().mockResolvedValue(new Response(JSON.stringify(body(row,{...body().meta,release_id:'rel-2'}))));await expect(new LocalLocationRepository(other).detail(row.facility_id,'official',undefined,'rel-1')).rejects.toMatchObject({kind:'restricted'});});it.each([404,410])('fails closed with a safe restricted state for status %s',async status=>{const fetcher=vi.fn().mockResolvedValue(new Response(JSON.stringify({error:{code:'suppressed',message:'sensitive server detail'}}),{status}));await expect(new LocalLocationRepository(fetcher).detail(row.facility_id,'official',undefined,'rel-1')).rejects.toMatchObject({kind:'restricted',status,message:'This location snapshot is unavailable.'});expect(String(fetcher.mock.calls[0]?.[0])).toContain(`/api/v2/locations/${row.facility_id}?`);});});

it('returns all additive taxonomy leaf assignments and provenance in authorized details', async () => {
  const classified = {
    ...row,
    taxonomy_display_category: 'slaughter',
    taxonomy_primary_categories: ['slaughter', 'processing_and_preparation'],
    taxonomy_leaf_activities: [{ key: 'slaughter', label: 'Animal slaughter' }, { key: 'cutting', label: 'Meat cutting' }],
    taxonomy_assignments: [{
      primary_key: 'slaughter', leaf_key: 'slaughter', leaf_label: 'Animal slaughter', source_code_reference: 'table-1',
      source_label_reference: 'activity heading', source_code: 'SH', source_label: 'Slaughterhouse', method: 'direct',
      status: 'mapped', taxonomy_version: 'uec-taxonomy-v1', crosswalk_version: 'dk-v1', ruleset_version: 'rules-v1',
      observation_id: 'observation-1', source_record_id: 'source-row-1', artifact_id: 'artifact-1',
    }],
  };
  const result = await new LocalLocationRepository(vi.fn().mockResolvedValue(new Response(JSON.stringify(body(classified)), { status: 200 }))).detail(row.facility_id);
  expect(result.location.taxonomy).toMatchObject({
    displayCategory: 'slaughter', primaryCategories: ['slaughter', 'processing_and_preparation'],
    leafActivities: [{ label: 'Meat cutting' }, { label: 'Animal slaughter' }],
    assignments: [{ sourceCode: 'SH', sourceLabel: 'Slaughterhouse', method: 'direct', taxonomyVersion: 'uec-taxonomy-v1' }],
  });
});

describe('community detail safety', () => {
  const community = { ...row, source_type: 'user_submitted', publication_profile: 'community', factual_review_status: 'unreviewed', project_approval: 'pending', publication_warning: 'Unreviewed community claim — not verified by Until Every Cage' };
  it('accepts an eligible unreviewed community direct link with evidence context', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(body(community, { ...body().meta, profile: 'community' }))));
    await expect(new LocalLocationRepository(fetcher).detail(row.facility_id, 'community')).resolves.toMatchObject({ location: { evidence: { factualReviewStatus: 'unreviewed', projectApproval: 'pending', publicationWarning: community.publication_warning } } });
  });
  it('rejects row/envelope profile mismatch and release mismatch', async () => {
    await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(new Response(JSON.stringify(body(community))))).detail(row.facility_id)).rejects.toMatchObject({ kind: 'invalid-contract' });
    await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(new Response(JSON.stringify(body({ ...row, release_id: 'other' }))))).detail(row.facility_id)).rejects.toMatchObject({ kind: 'invalid-contract' });
  });
});

describe('allowlisted source-native detail facts', () => {
  const facts = {
    alternate_names: ['Detail DBA'],
    species_slaughtered: { beef_cow_slaughter: 'No', poultry: true },
    processing_activities: { raw_intact_beef_processing: 'Yes' },
    source_volume_categories: [{ code: '2.0', provenance: { source_field: 'activity_volume_codes', method: 'source_native' } }],
    derived_source_volume_ranges: [{ ordinal_code: '2', lower: 10000, upper: 100000, bounds: 'inclusive_lower_exclusive_upper', unit: 'pounds', period: 'month', method_version: 'fsis-mpi-volume-codebook-2026-03-24-v1', source_codebook_url: 'https://example.test/codebook', verification_state: 'source_codebook_verified' }],
    aphis_annual_reports: [{ fiscal_year: '2025', species_counts: [{ species: 'cattle', count: 12 }], source_url: 'https://example.test/annual', safe_provenance: { source_id: 'us.aphis.annual-reports', evidence_type: 'annual_reports', match_method: 'exact_source_identifier', matched_identifier_types: ['certificate_number'] } }],
    establishment_id: 'EST-42', establishment_number: 'P-42', grant_date: '2026-01-01',
    native_activity_code: 'SH', native_activity_label: 'Slaughterhouse',
  };
  it('maps populated allowlisted facts while preserving negative source flags', async () => {
    const result = await new LocalLocationRepository(vi.fn().mockResolvedValue(new Response(JSON.stringify(body({ ...row, ...facts })), { status: 200 }))).detail(row.facility_id);
    expect(result.location.sourceFacts).toMatchObject({
      alternateNames: ['Detail DBA'], speciesSlaughtered: { beef_cow_slaughter: 'No', poultry: true },
      processingActivities: { raw_intact_beef_processing: 'Yes' }, establishmentId: 'EST-42',
      sourceVolumeCategories: [{ code: '2.0', provenance: { sourceField: 'activity_volume_codes', method: 'source_native' } }],
      derivedSourceVolumeRanges: [{ ordinalCode: '2', lower: 10000, upper: 100000, unit: 'pounds', period: 'month' }],
      aphisAnnualReports: [{ fiscalYear: '2025', speciesCounts: [{ species: 'cattle', count: 12 }], safeProvenance: { sourceId: 'us.aphis.annual-reports', matchMethod: 'exact_source_identifier' } }],
    });
  });
  it('keeps list payloads minimal and rejects non-allowlisted detail fields', async () => {
    await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...body(), data: [{ ...row, ...facts }] }), { status: 200 }))).list()).rejects.toMatchObject({ kind: 'invalid-contract' });
    await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(new Response(JSON.stringify(body({ ...row, raw_source_values: { address: 'private' } })), { status: 200 }))).detail(row.facility_id)).rejects.toMatchObject({ kind: 'invalid-contract' });
    await expect(new LocalLocationRepository(vi.fn().mockResolvedValue(new Response(JSON.stringify(body({ ...row, contact_email: 'private@example.test' })), { status: 200 }))).detail(row.facility_id)).rejects.toMatchObject({ kind: 'invalid-contract' });
  });
});
