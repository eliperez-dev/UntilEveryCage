import { describe, expect, it } from 'vitest';
import { canOpenDevPreview, DEV_PREVIEW_LABEL, DEV_PREVIEW_PATH, DEV_PREVIEW_QUERY, DEV_PREVIEW_TOKEN_HEADER, devPreviewExportLabel, canMountPublicExport } from '../../src/features/devPreview/devPreviewContract';
import { DevCandidatePreviewRepository } from '../../src/api/DevCandidatePreviewRepository';
import { nextLocalReviewState } from '../../src/features/devPreview/devReviewState';

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
});
