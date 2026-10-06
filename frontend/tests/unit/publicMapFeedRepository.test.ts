import { describe, expect, it, vi } from 'vitest';
import { canReusePublicMapFeed, createPublicMapFeedRepository, parsePublicMapFeed } from '../../src/api/PublicMapFeedRepository';

const releaseId = 'synthetic-v0-release';
const featureId = '550e8400-e29b-41d4-a716-446655440000';
const payload = {
  api_version: 'v2',
  data: { type: 'FeatureCollection', features: [{
    type: 'Feature', id: featureId, geometry: { type: 'Point', coordinates: [4.4, 51.2] },
    properties: { facility_id: featureId, source_id: 'synthetic.source', category_key: 'slaughter', category_keys: ['slaughter'], precision: 'source_reported', weight: 1 },
  }] },
  meta: { profile: 'official', release_id: releaseId, manifest_sha256: 'a'.repeat(64), suppression_generation: 7, feature_count: 1, public_record_count: 2, unmapped_count: 1, release_label: 'Synthetic v0', dataset_version: 'synthetic-v0' },
};

describe('public release map feed', () => {
  it('reuses points only while the release and suppression identity are unchanged', () => {
    const identity = `${releaseId}:${'a'.repeat(64)}:7`;
    expect(canReusePublicMapFeed(releaseId, identity, releaseId, identity, true)).toBe(true);
    expect(canReusePublicMapFeed(releaseId, `${releaseId}:${'a'.repeat(64)}:8`, releaseId, identity, true)).toBe(false);
    expect(canReusePublicMapFeed(releaseId, identity, 'other-release', identity, true)).toBe(false);
    expect(canReusePublicMapFeed(null, null, releaseId, identity, true)).toBe(false);
    expect(canReusePublicMapFeed(releaseId, identity, releaseId, identity, false)).toBe(false);
  });

  it('projects only point identity and allowlisted display fields, preserving source-reported precision', () => {
    const result = parsePublicMapFeed(payload, 'official', releaseId);
    expect(result.collection.features[0]).toMatchObject({ id: featureId, geometry: { coordinates: [4.4, 51.2] }, properties: { id: featureId, kind: 'source-coordinate', precision: 'source_reported', weight: 1, category_key: 'slaughter' } });
    expect(JSON.stringify(result.collection)).not.toMatch(/canonical_name|address|city|provenance|facility name/i);
    expect(result.meta).toMatchObject({ releaseId, featureCount: 1, publicRecordCount: 2, unmappedCount: 1, suppressionGeneration: 7 });
  });

  it('rejects release mismatches, invalid precision and feature/meta count disagreement', () => {
    expect(() => parsePublicMapFeed(payload, 'official', 'other-release')).toThrow();
    expect(() => parsePublicMapFeed({ ...payload, data: { ...payload.data, features: [{ ...payload.data.features[0], properties: { ...payload.data.features[0]!.properties, precision: 'unmapped' } }] } }, 'official', releaseId)).toThrow();
    expect(() => parsePublicMapFeed({ ...payload, meta: { ...payload.meta, feature_count: 0 } }, 'official', releaseId)).toThrow();
  });

  it('requests one same-origin public feed pinned to profile and release', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
    await createPublicMapFeedRepository(fetcher as typeof fetch).load('official', releaseId);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0]?.[0]).toBe(`/api/v2/map/feed?profile=official&release_id=${releaseId}`);
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({ method: 'GET', cache: 'no-store', credentials: 'omit' });
  });
});
