import { describe, expect, it } from 'vitest';
import { addRealPreviewMapLayers, nativeClusterMaxZoom, setClusterTileRounding, useRoundedClusterTiles } from '../../src/design-lab/components/realPreviewMapLayers';

describe('real-preview native clustering layers', () => {
  it('puts facility coordinates and weighted references in one source and filters clusters first', () => {
    const sources: Record<string, any> = {};
    const layers: any[] = [];
    const map = {
      getSource: (id: string) => sources[id],
      addSource: (id: string, source: unknown) => { sources[id] = source; },
      addLayer: (layer: unknown) => layers.push(layer),
    };
    const data = { type: 'FeatureCollection' as const, features: [
      { type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [4, 51] as [number, number] }, properties: { kind: 'source-coordinate', weight: 1 } },
      { type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [4.1, 51.1] as [number, number] }, properties: { kind: 'reference', weight: 12 } },
    ] };
    addRealPreviewMapLayers(map as any, data);
    expect(Object.keys(sources)).toEqual(['locations']);
    expect(sources.locations).toMatchObject({ cluster: true, clusterRadius: 25, clusterMaxZoom: 7, roundZoom: true, clusterProperties: { representedCount: ['+', ['get', 'weight']] } });
    expect(layers.find(layer => layer.id === 'clusters')?.filter).toEqual(['has', 'cluster']);
    expect(layers.find(layer => layer.id === 'clusters')?.layout['icon-image'])
      .toEqual(['step', ['get', 'representedCount'], 'cluster-low', 10, 'cluster-mid', 100, 'cluster-high', 1001, 'cluster-very-high']);
    expect(layers.find(layer => layer.id === 'approx-reference-points')?.maxzoom).toBeUndefined();
    expect(layers.find(layer => layer.id === 'approx-reference-points')).toMatchObject({
      type: 'symbol',
      layout: {
        'icon-image': 'cluster-approx', 'icon-size': 0.8,
        'text-field': ['to-string', ['get', 'weight']],
      },
      paint: { 'text-color': '#172019' },
    });
    expect(layers.find(layer => layer.id === 'aggregate-count')?.filter).toEqual([
      'all', ['!', ['has', 'cluster']], ['==', ['get', 'kind'], 'reference'],
      ['!', ['any', ['==', ['get', 'precision'], 'city'], ['==', ['get', 'precision'], 'city_reference_approximate']]],
    ]);
    expect(layers.find(layer => layer.id === 'aggregate-outer')?.paint['circle-color']).toEqual([
      'case', ['any', ['==', ['get', 'precision'], 'city'], ['==', ['get', 'precision'], 'city_reference_approximate']],
      '#79b9da', '#15252c',
    ]);
    expect(layers.find(layer => layer.id === 'aggregate-outer')?.filter).toEqual(['all', ['!', ['has', 'cluster']], ['==', ['get', 'kind'], 'reference']]);
    expect(layers.find(layer => layer.id === 'source-coordinate-points')?.filter).toEqual(['all', ['!', ['has', 'cluster']], ['==', ['get', 'kind'], 'source-coordinate']]);
    expect(layers.find(layer => layer.id === 'source-coordinate-points')?.paint?.['circle-color']).toEqual(
      ['match', ['get', 'precision'], 'source_provided_unverified', '#e0a45d', '#d8c99b'],
    );
  });

  it('uses the tile zoom transition matching whole and half camera zoom cutoffs', () => {
    expect(nativeClusterMaxZoom(7.5)).toBe(7);
    expect(useRoundedClusterTiles(7.5)).toBe(true);
    expect(nativeClusterMaxZoom(8)).toBe(7);
    expect(useRoundedClusterTiles(8)).toBe(false);
    expect(nativeClusterMaxZoom(6.5)).toBe(6);
    const unsupportedMap = { getSource: () => Object.freeze({}) } as any;
    expect(setClusterTileRounding(unsupportedMap, 7.5)).toBe(false);
  });
});
