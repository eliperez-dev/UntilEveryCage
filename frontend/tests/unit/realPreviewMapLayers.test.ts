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
      { type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [145, -37] as [number, number] }, properties: { kind: 'provider_address_point_private', precision: 'provider_address_point_high_confidence', weight: 1 } },
      { type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [144, -36] as [number, number] }, properties: { kind: 'provider_locality_approximate', precision: 'provider_locality_approximate', weight: 2 } },
      { type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [4.1, 51.1] as [number, number] }, properties: { kind: 'reference', weight: 12 } },
    ] };
    addRealPreviewMapLayers(map as any, data);
    expect(Object.keys(sources)).toEqual(['locations']);
    expect(sources.locations).toMatchObject({ cluster: true, clusterRadius: 30, clusterMaxZoom: 7, roundZoom: true, clusterProperties: { representedCount: ['+', ['get', 'weight']] } });
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
      'all', ['!', ['has', 'cluster']], ['in', ['get', 'kind'], ['literal', ['reference', 'provider_locality_approximate']]],
      ['!', ['any', ['==', ['get', 'precision'], 'city'], ['==', ['get', 'precision'], 'city_reference_approximate'], ['==', ['get', 'precision'], 'provider_locality_approximate']]],
    ]);
    expect(layers.find(layer => layer.id === 'aggregate-outer')?.paint['circle-color']).toEqual([
      'case', ['any', ['==', ['get', 'precision'], 'city'], ['==', ['get', 'precision'], 'city_reference_approximate'], ['==', ['get', 'precision'], 'provider_locality_approximate']],
      '#79b9da', '#15252c',
    ]);
    expect(layers.find(layer => layer.id === 'aggregate-outer')?.filter).toEqual(['all', ['!', ['has', 'cluster']], ['in', ['get', 'kind'], ['literal', ['reference', 'provider_locality_approximate']]]]);
    expect(layers.find(layer => layer.id === 'source-coordinate-points')?.filter).toEqual(['all', ['!', ['has', 'cluster']], ['in', ['get', 'kind'], ['literal', ['source-coordinate', 'provider_address_point_private']]]]);
    expect(layers.find(layer => layer.id === 'source-coordinate-points')?.filter).toContainEqual(['in', ['get', 'kind'], ['literal', ['source-coordinate', 'provider_address_point_private']]]);
    expect(layers.find(layer => layer.id === 'source-coordinate-points')?.paint?.['circle-color']).toEqual(
      ['match', ['get', 'category_key'], 'animal_keeping_and_production', '#009E73', 'slaughter', '#D55E00', 'processing_and_preparation', '#0072B2', 'research_and_animal_use', '#CC79A7', 'other_regulated_premises', '#E69F00', '#B8B8B8'],
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
