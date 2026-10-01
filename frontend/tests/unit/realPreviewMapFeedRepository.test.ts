import { describe, expect, it, vi } from 'vitest';
import { createRealPreviewMapFeedRepository, parseRealPreviewMapFeed, RealPreviewMapFeedError } from '../../src/api/RealPreviewMapFeedRepository';

const envelope = {
  api_version: 'real-preview-v1',
  data: [
    { key: '550e8400-e29b-41d4-a716-446655440000', kind: 'source_coordinate', precision: 'approximate_source_precision_unknown_pending_review', source_id: 'source-a', latitude: 51.2, longitude: 4.1, weight: 1 },
    { key: '0123456789abcdef0123456789abcdef', kind: 'city_reference', precision: 'city_reference_approximate', source_id: 'source-a', latitude: 50.8, longitude: 4.3, weight: 9 },
  ],
  meta: { bounded: true, private_preview: true, scope: 'default_map_scope', zoom_max: 14, feature_limit: 200000, total_weight: 10, snapshot_id: 'a'.repeat(64) },
};

describe('real-preview native map feed', () => {
  it('preserves the private FSIS unverified precision instead of relabeling it exact or coarse', () => {
    const payload = { ...envelope, data: [{ ...envelope.data[0], precision: 'source_provided_unverified' }] };
    const feature = parseRealPreviewMapFeed(payload).collection.features[0];
    expect(feature?.properties).toMatchObject({ kind: 'source-coordinate', precision: 'source_provided_unverified' });
  });
  it('projects only minimal coordinates, kind, opaque key, precision, and weight', () => {
    const result = parseRealPreviewMapFeed(envelope);
    expect(result.collection.features).toHaveLength(2);
    expect(result.collection.features[0]).toMatchObject({
      geometry: { coordinates: [4.1, 51.2] },
      properties: { key: envelope.data[0].key, kind: 'source-coordinate', weight: 1, precision: envelope.data[0].precision },
    });
    expect(result.collection.features[1]).toMatchObject({
      id: `${envelope.data[1].key}:source-a`,
      properties: { kind: 'reference', source_id: 'source-a', key: envelope.data[1].key, weight: 9 },
    });
    expect(JSON.stringify(result)).not.toMatch(/address|name|provenance/i);
  });

  it('rejects feeds that do not confirm bounded private preview scope', () => {
    expect(() => parseRealPreviewMapFeed({ ...envelope, meta: { ...envelope.meta, private_preview: false } })).toThrow(RealPreviewMapFeedError);
  });

  it('fetches the compact source-filtered endpoint once with same-origin no-store semantics', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope), { status: 200 }));
    await createRealPreviewMapFeedRepository(fetcher as typeof fetch).load('be.source / 1');
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0]?.[0]).toBe('/dev/real-preview/map/feed?source_id=be.source+%2F+1');
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({ credentials: 'same-origin', cache: 'no-store' });
  });
});
