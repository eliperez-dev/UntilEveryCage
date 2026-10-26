// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { decodePublicMapTransport, encodePublicMapTransport, installPublicMapTransport, PUBLIC_MAP_TRANSPORT_FIELD, type PublicTransportPrototype } from '../../src/map/publicMapSourceTransport';

function collection() {
  return { type: 'FeatureCollection', uec_public_index: { profile: 'official', releaseId: 'synthetic-release',
    manifestSha256: 'a'.repeat(64), suppressionGeneration: 2, session: 'synthetic-session', maxMiB: 64 },
  features: Array.from({ length: 1000 }, (_, index) => ({ type: 'Feature', id: `synthetic-${index}`,
    geometry: { type: 'Point', coordinates: [4 + index * .00001, 51] },
    properties: { facility_id: `synthetic-${index}`, category_keys: ['slaughter', 'processing_and_preparation'], weight: 1,
      unknown: null, public_flag: true, precision: 'source_reported' } })) };
}

describe('public native-source parameter transport', () => {
  it('preserves complete public point fields and category arrays through a string envelope', () => {
    const data = collection();
    const encoded = encodePublicMapTransport(data) as Record<string, unknown>;
    expect(encoded).not.toBe(data);
    expect(encoded.features).toEqual([]);
    expect(typeof encoded[PUBLIC_MAP_TRANSPORT_FIELD]).toBe('string');
    expect(decodePublicMapTransport(encoded).data).toEqual(data);
    expect(data.features).toHaveLength(1000);
  });

  it('leaves private, device-derived and unsupported values on the original native path', () => {
    const data = collection();
    for (const candidate of [{ ...data, uec_public_index: undefined },
      { ...data, uec_public_index: { ...data.uec_public_index, profile: 'candidate-preview' } },
      { ...data, uec_public_index: { ...data.uec_public_index, profile: 'community' } }]) {
      expect(encodePublicMapTransport(candidate)).toBe(candidate);
    }
    for (const value of [undefined, Infinity, -0, { nested: 'preserve the native object' }]) {
      const candidate = collection();
      (candidate.features[0]!.properties as Record<string, unknown>).unusual = value;
      expect(encodePublicMapTransport(candidate)).toBe(candidate);
    }
    const circular = collection() as unknown as Record<string, unknown>;
    circular.circular = circular;
    expect(encodePublicMapTransport(circular)).toBe(circular);
  });

  it('changes only worker parameters while preserving the original main-thread source data', async () => {
    const data = collection();
    const prototype = { async _getLoadGeoJSONParameters(this: { data: unknown; source: string }) {
      return { source: this.source, data: this.data };
    } };
    installPublicMapTransport(prototype);
    installPublicMapTransport(prototype);
    const source = Object.assign(Object.create(prototype), { source: 'locations', data });
    const parameters = await source._getLoadGeoJSONParameters();
    expect(source.data).toBe(data);
    expect(parameters.data).not.toBe(data);
    expect(decodePublicMapTransport(parameters.data).data).toEqual(data);
    const other = Object.assign(Object.create(prototype), { source: 'approximate-reference-area', data });
    expect((await other._getLoadGeoJSONParameters()).data).toBe(data);
  });

  it('rejects malformed or nonpublic envelopes before entering native indexing', () => {
    expect(() => decodePublicMapTransport({ type: 'FeatureCollection', features: [], [PUBLIC_MAP_TRANSPORT_FIELD]: '{' })).toThrow();
    expect(() => decodePublicMapTransport({ type: 'FeatureCollection', features: [], [PUBLIC_MAP_TRANSPORT_FIELD]: JSON.stringify({ ...collection(), uec_public_index: {} }) })).toThrow();
    const ordinary = { type: 'FeatureCollection', features: [] };
    expect(decodePublicMapTransport(ordinary).data).toBe(ordinary);
  });

  it('keeps an unsupported source prototype untouched', () => {
    const prototype = {};
    expect(installPublicMapTransport(prototype as PublicTransportPrototype)).toBe(false);
    expect(Object.keys(prototype)).toEqual([]);
  });
});
