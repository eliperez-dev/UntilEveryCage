import { describe, expect, it, vi } from 'vitest';
import { parseRealPreviewMapFeed, RealPreviewMapFeedError } from '../../src/api/RealPreviewMapFeedRepository';
import { createTestReleaseMapFeedRepository } from '../../src/api/TestReleaseMapFeedRepository';

const envelope = {
  api_version: 'dev-test-v1',
  data: { points: [{ key: '550e8400-e29b-41d4-a716-446655440000', source_id: 'us.fsis', kind: 'source_coordinate', precision: 'source_provided_unverified', latitude: 38.9, longitude: -77.1, weight: 1, category_key: 'slaughter', category_keys: ['slaughter'] }] },
  meta: { private_preview: true, candidate_only: true, test_only: false, release_id: 'candidate-2026', snapshot_id: 'b'.repeat(64), bounded: true, scope: 'candidate_map', zoom_max: 14, preview_label: 'Configured candidate correction' },
};

describe('configured candidate map feed', () => {
  it('accepts only its points envelope and preserves source-native precision', () => {
    const result = parseRealPreviewMapFeed(envelope, true);
    expect(result.collection.features[0]?.properties).toMatchObject({ key: envelope.data.points[0].key, precision: 'source_provided_unverified', kind: 'source-coordinate' });
    expect(JSON.stringify(result.collection)).not.toMatch(/name|address|detail/i);
  });

  it('rejects fixtures and non-candidate boundaries', () => {
    expect(() => parseRealPreviewMapFeed({ ...envelope, meta: { ...envelope.meta, test_only: true } }, true)).toThrow(RealPreviewMapFeedError);
    expect(() => parseRealPreviewMapFeed({ ...envelope, data: {} }, true)).toThrow(RealPreviewMapFeedError);
  });

  it('loads the authenticated candidate feed without using the location list as map input', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope), { status: 200 }));
    await createTestReleaseMapFeedRepository(fetcher as typeof fetch).load();
    expect(fetcher).toHaveBeenCalledWith('/api/dev/preview/test-release/map/feed', expect.objectContaining({ credentials: 'same-origin', cache: 'no-store' }));
  });
});
