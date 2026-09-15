import { describe, expect, it, vi } from 'vitest';
import { canOpenDevPreview, DEV_PREVIEW_LABEL, DEV_PREVIEW_PATH, DEV_PREVIEW_QUERY, DEV_PREVIEW_TOKEN_HEADER, devPreviewExportLabel, canMountPublicExport, TEST_RELEASE_API_VERSION, TEST_RELEASE_LABEL, TEST_RELEASE_PATH, testReleasePath } from '../../src/features/devPreview/devPreviewContract';
import { DevCandidatePreviewRepository } from '../../src/api/DevCandidatePreviewRepository';
import { nextLocalReviewState } from '../../src/features/devPreview/devReviewState';
import { TestReleaseRepository } from '../../src/api/TestReleaseRepository';
import { TestReleaseCsvExportRepository } from '../../src/api/TestReleaseCsvExportRepository';
import { TestReleaseFilterMetadataRepository } from '../../src/api/TestReleaseFilterMetadataRepository';
import { locationSchema, testReleaseLocationSchema } from '../../src/api/wireSchema';

describe('dev preview boundary', () => {
  it('requires both a development build and the explicit mode', () => {
    expect(canOpenDevPreview(true, DEV_PREVIEW_QUERY)).toBe(true);
    expect(canOpenDevPreview(false, DEV_PREVIEW_QUERY)).toBe(false);
    expect(canOpenDevPreview(true, null)).toBe(false);
    expect(canOpenDevPreview(true, 'local-v2')).toBe(false);
  });

  it('keeps the route and label distinct from public V2', () => {
    expect(DEV_PREVIEW_PATH).toBe('/api/dev/preview/candidates');
    expect(DEV_PREVIEW_PATH).not.toContain('/api/v2/');
    expect(DEV_PREVIEW_TOKEN_HEADER).toBe('X-UEC-Dev-Preview-Token');
    expect(DEV_PREVIEW_LABEL).toContain('NOT REVIEWED OR PUBLISHED');
    expect(devPreviewExportLabel(true)).toContain('export unavailable');
    expect(devPreviewExportLabel(true)).not.toContain('curated');
    expect(devPreviewExportLabel(false)).toBeNull();
    expect(canMountPublicExport(true)).toBe(false); // includes ?preview=dev-candidates&mode=local-v2
    expect(canMountPublicExport(false)).toBe(true);
    expect(TEST_RELEASE_API_VERSION).toBe('dev-test-v1');
    expect(TEST_RELEASE_PATH).not.toContain('/api/v2/');
    expect(testReleasePath('locations', 'facility/one')).toBe('/api/dev/preview/test-release/locations/facility%2Fone');
    expect(testReleasePath('csv')).toBe('/api/dev/preview/test-release/csv');
    expect(TEST_RELEASE_LABEL).toContain('not project-approved or published');
  });

  it('preserves candidate unapproved and unpublished semantics', async () => {
    const fetcher = async () => new Response(JSON.stringify({ api_version: 'dev-preview-v1', data: [{ candidate_id: 'candidate-1', source_record_id: 'source-row-1', facility_id: 'facility-1', canonical_name: 'Candidate facility', country_code: 'DK', city: null, category: 'dairy', display_precision: 'unmapped', latitude: null, longitude: null, source_type: 'official', provenance_source_id: 'source-1', provenance_source_name: 'Private source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z', factual_review_status: 'unreviewed', privacy_screening_status: 'passed', project_approval: false, release_id: 'candidate-release', release_status: 'candidate', preview_label: DEV_PREVIEW_LABEL }], meta: { test_only: true, private_preview: true, profile: null, coverage_scope: 'candidate_release_only', next_cursor: null } }));
    const result = await new DevCandidatePreviewRepository(fetcher).list('operator-token');
    expect(result[0]?.evidence).toMatchObject({ projectApproval: false, publicationProfile: null, publicationWarning: DEV_PREVIEW_LABEL });
  });
  it('keeps local review notes non-approval and non-persistent in the model', () => {
    expect(nextLocalReviewState('unreviewed', 'inspect')).toBe('inspected');
    expect(nextLocalReviewState('inspected', 'follow_up')).toBe('follow_up');
    expect(nextLocalReviewState('follow_up', 'inspect')).toBe('follow_up');
  });
  it('maps test-release rows without requiring approval or coordinates and never falls back', async () => {
    const row = { facility_id: '550e8400-e29b-41d4-a716-446655440000', canonical_name: 'Pending test row', city: null, country_code: 'GB', category: 'dairy', source_type: 'official', publication_profile: 'official', factual_review_status: 'unreviewed', privacy_screening_status: 'passed', project_approval: 'pending', reviewer_role: null, publication_warning: null, display_precision: 'unmapped', latitude: null, longitude: null, first_observed_at: null, last_observed_at: null, observation_count: null, lifecycle_status: 'status_unknown', provenance_source_id: 's1', provenance_source_name: 'Test source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z', release_id: 'test-release', release_ruleset_version: 'rules-1' };
    const body = { data: [row], meta: { api_version: 'dev-test-v1', environment: 'test-only', test_only: true, private_preview: true, release_status: 'candidate', release_id: 'test-release', profile: 'official', coverage_scope: 'test_release_public_shaped_rows', count_semantics: 'Rows only', preview_label: TEST_RELEASE_LABEL, result_count: 1, next_cursor: null } };
    const candidateVariant = { ...row, canonical_name: null, privacy_screening_status: 'pending', project_approval: 'not-approved', release_ruleset_version: null };
    expect(testReleaseLocationSchema.safeParse(candidateVariant).success).toBe(true);
    expect(locationSchema.safeParse(candidateVariant).success).toBe(false);
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(body)));
    const result = await new TestReleaseRepository(fetcher).list('official', 'test-token');
    expect(result.locations[0]).toMatchObject({ name: 'Pending test row', lat: null, evidence: { projectApproval: 'pending' } });
    expect(result.coverageNote).toContain('not project-approved');
    await expect(new TestReleaseRepository(vi.fn().mockResolvedValue(new Response('unavailable', { status: 401 }))).list('official', 'wrong')).rejects.toThrow('unavailable');
  });
  it('requires explicit test-release CSV markers and validates facets metadata', async () => {
    const csvFetcher = vi.fn().mockResolvedValue(new Response('facility_id,project_approval\n1,pending\n', { headers: { 'x-uec-test-release': 'true', 'x-uec-release-id': 'test-release' } }));
    await expect(new TestReleaseCsvExportRepository(csvFetcher).download('official', 'test-token')).resolves.toMatchObject({ releaseId: 'test-release', label: TEST_RELEASE_LABEL });
    const facets = { data: null, meta: { api_version: 'dev-test-v1', environment: 'test-only', test_only: true, private_preview: true, release_status: 'candidate', release_id: 'test-release', profile: 'official', coverage_scope: 'test_release_public_shaped_rows', count_semantics: 'Rows only', preview_label: TEST_RELEASE_LABEL, result_count: 0 }, dimensions: { country_code: [], category: [], display_precision: [], source_type: [] } };
    await expect(new TestReleaseFilterMetadataRepository(vi.fn().mockResolvedValue(new Response(JSON.stringify(facets)))).get('official', 'test-token')).resolves.toMatchObject({ meta: { test_only: true, release_status: 'candidate' } });
  });
});
