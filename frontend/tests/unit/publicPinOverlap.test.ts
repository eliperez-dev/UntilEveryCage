import { describe, expect, it } from 'vitest';
import { collectPublicOverlap, coordinateKey, createPublicOverlapIndex, overlapPanelFrame, publicOverlapMember } from '../../src/design-lab/components/publicPinOverlap';
import type { JsonMapCollection, JsonMapFeature } from '../../src/design-lab/components/jsonMapFallback';

const point = (n: number, coordinates: [number, number] = [12, 34], precision = 'source_reported'): JsonMapFeature => ({
  type: 'Feature', id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
  geometry: { type: 'Point', coordinates },
  properties: { key: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`, weight: 1, precision, kind: precision === 'approximate' ? 'reference' : 'source-coordinate' },
});
const collection = (...features: JsonMapFeature[]): JsonMapCollection => ({ type: 'FeatureCollection', features });

describe('public pin overlaps', () => {
  it('finds the complete shared-point group from a single rendered member and preserves individual precision', () => {
    const features = Array.from({ length: 81 }, (_, i) => point(i, [12, 34], i % 2 ? 'approximate' : 'source_reported'));
    const index = createPublicOverlapIndex(collection(...features));
    const result = collectPublicOverlap(index, [features[75]], { x: 100, y: 100 }, () => ({ x: 100, y: 100 }));
    expect(result).toHaveLength(81);
    expect(new Set(result.map(member => member.feature.properties.precision)).size).toBe(2);
    expect(result[0]!.feature).toBe(features[0]);
  });
  it('does not carry old release/filter membership into a replacement collection', () => {
    const first = point(1), second = point(2);
    const previous = createPublicOverlapIndex(collection(first, second));
    const filtered = createPublicOverlapIndex(collection(second));
    expect(previous.group(String(second.id))).toHaveLength(2);
    expect(filtered.group(String(second.id))).toHaveLength(1);
    expect(collectPublicOverlap(filtered, [first], { x: 0, y: 0 }, () => ({ x: 0, y: 0 }))).toEqual([]);
  });
  it('has stable deduplicated IDs and excludes clusters, private reference keys, weighted aggregates and invalid coordinates', () => {
    const first = point(1), second = point(2);
    const invalid = [
      { ...point(3), properties: { key: 'a'.repeat(32), weight: 1 } },
      { ...point(4), properties: { ...point(4).properties, cluster_id: 12 } },
      { ...point(5), properties: { ...point(5).properties, kind: 'aggregate' } },
      { ...point(6), properties: { ...point(6).properties, weight: 81 } },
      point(7, [0, 91]), point(8, [181, 0]), point(9, [NaN, 0]),
    ];
    const index = createPublicOverlapIndex(collection(second, ...invalid, first, second));
    expect([...index.byId.keys()]).toHaveLength(2);
    expect(index.group(String(first.id)).map(member => member.id)).toEqual([String(first.id), String(second.id)]);
    for (const feature of invalid) expect(publicOverlapMember(feature)).toBeNull();
  });
  it('supports wrapped world copies without changing real member geometry', () => {
    const feature = point(1, [180, 0]);
    const other = point(2, [-180, 0]);
    const index = createPublicOverlapIndex(collection(feature, other));
    expect(coordinateKey([180, 0])).toBe(coordinateKey([-180, 0]));
    expect(index.group(String(feature.id))).toHaveLength(2);
    const wrapped = { ...feature, geometry: { type: 'Point', coordinates: [540, 0] } };
    const matches = collectPublicOverlap(index, [wrapped], { x: 50, y: 50 }, () => ({ x: 50, y: 50 }));
    expect(matches).toHaveLength(2);
    expect(matches.find(member => member.id === feature.id)?.coordinates).toEqual([180, 0]);
  });
  it('expands visible nearby overlaps but excludes unrelated marks and unfiltered rendered leftovers', () => {
    const first = point(1, [1, 1]), second = point(2, [2, 2]), far = point(3, [100, 100]);
    const stale = point(4, [1, 1]);
    const index = createPublicOverlapIndex(collection(first, second, far));
    const result = collectPublicOverlap(index, [first, second, far, stale], { x: 0, y: 0 }, coordinates => ({ x: coordinates[0] * 10, y: coordinates[1] * 10 }), 30);
    expect(result.map(member => member.id)).toEqual([String(first.id), String(second.id)]);
    expect(result.map(member => member.coordinates)).toEqual([[1, 1], [2, 2]]);
  });
});

describe('overlap panel positioning', () => {
  const bounds = { left: 12, right: 1100, top: 80, bottom: 800 };

  it('places the list beside the pin when there is room', () => {
    expect(overlapPanelFrame(bounds, { x: 550, y: 400 }, 5)).toEqual({
      left: 575, top: 353, width: 304, maxHeight: 382,
    });
    expect(overlapPanelFrame(bounds, { x: 1050, y: 100 }, 5)).toMatchObject({ left: 721, top: 80 });
  });

  it('keeps a long list above the bottom and within a narrow viewport', () => {
    expect(overlapPanelFrame(bounds, { x: 500, y: 790 }, 614)).toMatchObject({ top: 418 });
    expect(overlapPanelFrame({ left: 12, right: 302, top: 80, bottom: 350 }, { x: 200, y: 250 }, 214))
      .toEqual({ left: 12, top: 80, width: 290, maxHeight: 270 });
  });
});
