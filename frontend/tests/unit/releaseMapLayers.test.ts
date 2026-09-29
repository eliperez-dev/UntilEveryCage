import { describe, expect, it } from 'vitest';
import {
  RELEASE_MAP_PROPERTIES,
  RELEASE_MAP_SOURCE_LAYER,
  addReleaseMapLayers,
  removeReleaseMapLayers,
} from '../../src/design-lab/components/releaseMapLayers';

function fakeMap() {
  const sources = new Map<string, unknown>();
  const layers = new Map<string, any>();
  const removed: string[] = [];
  return {
    sources, layers, removed,
    addSource: (id: string, source: unknown) => sources.set(id, source),
    addLayer: (layer: any) => layers.set(layer.id, layer),
    getLayer: (id: string) => layers.get(id),
    getSource: (id: string) => sources.get(id),
    removeLayer: (id: string) => { removed.push(id); layers.delete(id); },
    removeSource: (id: string) => { removed.push(id); sources.delete(id); },
  };
}

describe('release map layers', () => {
  it('uses the immutable public MVT template and exact source layer with configurable zoom and opacity', () => {
    const map = fakeMap();
    const attached = addReleaseMapLayers(map, 'r2026_09', {
      tileTemplate: '/api/v2/releases/r1/map/tiles/{z}/{x}/{y}.mvt',
      minZoom: 2, maxZoom: 13, opacity: 0.35,
    });
    expect(map.sources.get(attached.sourceId)).toEqual({
      type: 'vector', tiles: ['/api/v2/releases/r1/map/tiles/{z}/{x}/{y}.mvt'], minzoom: 2, maxzoom: 13,
    });
    expect(attached.layerIds).toHaveLength(6);
    expect([...map.layers.values()].every(layer => layer['source-layer'] === RELEASE_MAP_SOURCE_LAYER)).toBe(true);
    expect(map.layers.get(attached.layerIds[0])?.paint['circle-opacity']).toBeCloseTo(0.322);
  });

  it('separates server cluster, coarse area, and exact pin kinds', () => {
    const map = fakeMap();
    const { layerIds } = addReleaseMapLayers(map, 'release_a', { tileTemplate: '/tiles/{z}/{x}/{y}' });
    const layers = layerIds.map(id => map.layers.get(id));
    expect(layers.map(layer => layer.filter)).toEqual([
      ['==', ['get', 'kind'], 'cluster'],
      ['==', ['get', 'kind'], 'cluster'],
      ['==', ['get', 'kind'], 'coarse'],
      ['==', ['get', 'kind'], 'coarse'],
      ['==', ['get', 'kind'], 'coarse'],
      ['==', ['get', 'kind'], 'exact'],
    ]);
    expect(JSON.stringify(layers[1])).toContain('exact_count');
    expect(JSON.stringify(layers[1])).toContain('coarse_count');
    expect(layers[4].layout['text-field']).toBe('APPROX.');
    expect(layers[2].paint['circle-radius']).toBe(17);
  });

  it('keeps the public property contract minimal and layer expressions free of identifying fields', () => {
    expect(RELEASE_MAP_PROPERTIES).toEqual([
      'feature_key', 'kind', 'count', 'exact_count', 'coarse_count', 'next_zoom', 'record_id', 'category_key',
    ]);
    const map = fakeMap();
    addReleaseMapLayers(map, 'public', { tileTemplate: '/tiles/{z}/{x}/{y}' });
    const encodedLayers = JSON.stringify([...map.layers.values()]);
    for (const forbidden of ['name', 'address', 'source_id', 'evidence', 'facility_id']) {
      expect(encodedLayers).not.toContain(forbidden);
    }
  });

  it('removes only the requested namespace and rejects collisions', () => {
    const map = fakeMap();
    const first = addReleaseMapLayers(map, 'release_1', { tileTemplate: '/one/{z}/{x}/{y}' });
    const second = addReleaseMapLayers(map, 'release_2', { tileTemplate: '/two/{z}/{x}/{y}' });
    expect(() => addReleaseMapLayers(map, 'release_1', { tileTemplate: '/again/{z}/{x}/{y}' })).toThrow(/already attached/);

    removeReleaseMapLayers(map, 'release_1');
    expect(map.sources.has(first.sourceId)).toBe(false);
    expect(first.layerIds.some(id => map.layers.has(id))).toBe(false);
    expect(map.sources.has(second.sourceId)).toBe(true);
    expect(second.layerIds.every(id => map.layers.has(id))).toBe(true);
  });
});
