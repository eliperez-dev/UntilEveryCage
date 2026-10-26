// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { clusterIndexKey, publicIndexIdentity } from '../../src/map/clusterIndexCache';

const identity = { profile: 'official' as const, releaseId: 'synthetic-release', manifestSha256: 'a'.repeat(64), suppressionGeneration: 4, session: 'synthetic-session', maxMiB: 64 };
const features = [{ type: 'Feature', id: 'synthetic-point', geometry: { type: 'Point', coordinates: [1, 2] }, properties: { weight: 1, category_key: 'slaughter' } }];
const options = { cluster: true, clusterOptions: { radius: 50, maxZoom: 8 } };
const properties = { representedCount: ['+', ['get', 'weight']] };

describe('persistent index identity', () => {
  it('reuses identical content across sessions without storing the raw cache inputs in its key', async () => {
    const first = await clusterIndexKey(identity, features, options, properties);
    expect(first).toMatch(/^[a-f0-9]{64}$/);
    expect(await clusterIndexKey({ ...identity, session: 'next-session', maxMiB: 32 }, structuredClone(features), options, properties)).toBe(first);
  });
  it('invalidates release, manifest, restrictions, membership, displayed properties and hierarchy settings independently', async () => {
    const initial = await clusterIndexKey(identity, features, options, properties);
    for (const changed of [{ ...identity, releaseId: 'next-release' }, { ...identity, manifestSha256: 'b'.repeat(64) }, { ...identity, suppressionGeneration: 5 }]) {
      expect(await clusterIndexKey(changed, features, options, properties)).not.toBe(initial);
    }
    expect(await clusterIndexKey(identity, [], options, properties)).not.toBe(initial);
    expect(await clusterIndexKey(identity, [{ ...features[0], properties: { weight: 2 } }], options, properties)).not.toBe(initial);
    expect(await clusterIndexKey(identity, features, { ...options, clusterOptions: { radius: 60, maxZoom: 8 } }, properties)).not.toBe(initial);
    expect(await clusterIndexKey(identity, features, options, { representedCount: ['+', 2] })).not.toBe(initial);
  });
  it('allows only an explicit public identity and drops unrelated fields', () => {
    expect(publicIndexIdentity({ ...identity, query: 'never-copy-this' })).toEqual(identity);
    for (const change of [{ profile: 'community' }, { profile: 'candidate-preview' }, { suppressionGeneration: -1 }, { manifestSha256: 'wrong' }, { releaseId: '../private' }, { session: '' }]) {
      expect(publicIndexIdentity({ ...identity, ...change })).toBeNull();
    }
  });
});
