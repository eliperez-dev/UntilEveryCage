import { describe, expect, it } from 'vitest';
import { parsePublicMapFeed } from '../../src/api/PublicMapFeedRepository';

const id = '11111111-1111-4111-8111-111111111111';
const meta = { profile: 'official', release_id: 'v0', manifest_sha256: 'a'.repeat(64), suppression_generation: 7, dataset_version: 'v0', release_label: 'v0', public_record_count: 1, feature_count: 1, unmapped_count: 0 };

describe('public map compact feed', () => {
  it('expands repeated-property dictionaries while retaining the direct UUID', () => {
    const feed = parsePublicMapFeed({ api_version: 'v2', data: { format: 'compact-v1', dictionaries: { source_ids: ['source'], category_keys: ['slaughter'], precisions: ['exact'] }, features: [[id, 1, 2, 0, 0, [0], 0]] }, meta }, 'official', 'v0');
    expect(feed.collection.features).toHaveLength(1);
    expect(feed.collection.features[0]?.properties).toMatchObject({ facility_id: id, source_id: 'source', category_key: 'slaughter', precision: 'exact' });
  });
  it('rejects compact indices outside their dictionaries', () => {
    expect(() => parsePublicMapFeed({ api_version: 'v2', data: { format: 'compact-v1', dictionaries: { source_ids: [], category_keys: [], precisions: [] }, features: [[id, 1, 2, 0, 0, [], 0]] }, meta }, 'official', 'v0')).toThrow();
  });
});
