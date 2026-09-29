import { describe, expect, it, vi } from 'vitest';
import fixture from '../fixtures/release-map/manifest.json';
import {
  parseReleaseMapManifest,
  ReleaseMapManifestError,
  ReleaseMapManifestRepository,
} from '../../src/api/ReleaseMapManifestRepository';

const clone = () => structuredClone(fixture) as Record<string, any>;
const artifact = (payload: Record<string, any>) => payload.data.manifest.map_artifact;
const response = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), { status });

describe('release map manifest contract', () => {
  it('parses a release-scoped artifact without exposing arbitrary manifest fields', () => {
    const parsed = parseReleaseMapManifest(fixture, 'synthetic-release-2026-09', 'official');
    expect(parsed).toMatchObject({
      releaseId: 'synthetic-release-2026-09', profile: 'official', suppressionGeneration: 7,
      sourceLayer: 'uec_map', minZoom: 0, maxZoom: 8,
    });
    expect(JSON.stringify(parsed)).not.toMatch(/private|address|facility name/i);
  });

  it('treats absent or explicitly ineligible artifacts as no map', () => {
    const absent = clone();
    delete absent.data.manifest.map_artifact;
    expect(parseReleaseMapManifest(absent)).toBeNull();
    const ineligible = clone();
    artifact(ineligible).eligible = false;
    expect(parseReleaseMapManifest(ineligible)).toBeNull();
    const revoked = clone();
    revoked.data.suppression_generation = 8;
    expect(parseReleaseMapManifest(revoked)).toBeNull();
  });

  it('rejects release, profile, schema, and unsafe tile URL mismatches', () => {
    expect(() => parseReleaseMapManifest(fixture, 'other-release', 'official')).toThrow(ReleaseMapManifestError);
    expect(() => parseReleaseMapManifest(fixture, undefined, 'secondary')).toThrow(ReleaseMapManifestError);
    const wrongArtifact = clone();
    artifact(wrongArtifact).feature_schema_version = '';
    expect(() => parseReleaseMapManifest(wrongArtifact)).toThrow(ReleaseMapManifestError);
    for (const url of ['https://tiles.example/{z}/{x}/{y}.mvt', '//evil.example/{z}/{x}/{y}.mvt', '/api/map/{z}/{x}/{y}?next={q}']) {
      const unsafe = clone();
      artifact(unsafe).tile_url_template = url;
      expect(() => parseReleaseMapManifest(unsafe)).toThrow(ReleaseMapManifestError);
    }
  });

  it('revalidates with no-store and fails closed for 304 and network errors', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(fixture));
    const repo = new ReleaseMapManifestRepository(fetcher as typeof fetch);
    await expect(repo.load('official', undefined, 'synthetic-release-2026-09')).resolves.toMatchObject({ releaseId: 'synthetic-release-2026-09' });
    expect(fetcher).toHaveBeenCalledWith('/api/v2/releases/manifest?profile=official', expect.objectContaining({ cache: 'no-store', method: 'GET' }));
    await expect(new ReleaseMapManifestRepository(vi.fn().mockResolvedValue(new Response(null, { status: 304 })) as typeof fetch).load()).rejects.toMatchObject({ kind: 'invalid-contract' });
    await expect(new ReleaseMapManifestRepository(vi.fn().mockRejectedValue(new TypeError('offline')) as typeof fetch).load()).rejects.toMatchObject({ kind: 'network' });
  });
});
