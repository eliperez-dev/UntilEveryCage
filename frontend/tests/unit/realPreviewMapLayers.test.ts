import { describe, expect, it } from 'vitest';
import { addRealPreviewMapLayers, applyRealPreviewVisualSettings, hasRealPreviewMapLayers, nativeClusterMaxZoom, referenceRadiusExpression, setClusterTileRounding, setRealPreviewPinMode, useRoundedClusterTiles, REAL_PREVIEW_LAYER_IDS } from '../../src/design-lab/components/realPreviewMapLayers';

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
    expect(sources.locations).toMatchObject({ cluster: true, clusterRadius: 30, clusterMaxZoom: 7, roundZoom: true, clusterProperties: { representedCount: ['+', ['get', 'weight']], approximateCount: ['+', ['case', ['any', ['==', ['get', 'precision'], 'approximate'], ['==', ['get', 'precision'], 'city'], ['==', ['get', 'precision'], 'locality_reference_coarse']], ['get', 'weight'], 0]] } });
    expect(layers.find(layer => layer.id === 'clusters')?.filter).toEqual(['has', 'cluster']);
    expect(layers.find(layer => layer.id === 'clusters')?.layout['icon-image'])
      .toEqual(['step', ['get', 'representedCount'], 'cluster-low', 10, 'cluster-mid', 100, 'cluster-high', 1001, 'cluster-very-high']);
    expect(layers.find(layer => layer.id === 'approx-reference-points')?.maxzoom).toBeUndefined();
    expect(layers.find(layer => layer.id === 'approx-reference-points')).toMatchObject({
      type: 'symbol',
      layout: {
        'icon-image': 'v1-pin-grey', 'icon-anchor': 'bottom', 'icon-size': 0.5,
        'text-field': ['case', ['>', ['get', 'weight'], 1], ['to-string', ['get', 'weight']], ''],
      },
      paint: { 'text-color': '#172019' },
    });
    expect(layers.find(layer => layer.id === 'aggregate-count')?.filter).toEqual([
      'all', ['!', ['has', 'cluster']], ['in', ['get', 'kind'], ['literal', ['reference', 'provider_locality_approximate']]],
      ['!', ['any', ['==', ['get', 'precision'], 'city'], ['==', ['get', 'precision'], 'city_reference_approximate'], ['==', ['get', 'precision'], 'provider_locality_approximate'], ['==', ['get', 'precision'], 'locality_reference_coarse']]],
    ]);
    expect(layers.find(layer => layer.id === 'approx-reference-signal')).toMatchObject({
      type: 'circle',
      filter: ['all', ['!', ['has', 'cluster']], ['in', ['get', 'kind'], ['literal', ['reference', 'provider_locality_approximate']]], ['==', ['get', 'precision'], 'approximate']],
      paint: { 'circle-radius': 5, 'circle-opacity': 0.92, 'circle-stroke-width': 1.5 },
    });
    expect(layers.find(layer => layer.id === 'aggregate-outer')?.paint).toMatchObject({
      'circle-color': '#d8473f', 'circle-opacity': 0, 'circle-stroke-color': '#ff695c', 'circle-stroke-width': 2.5,
    });
    expect(JSON.stringify(layers.find(layer => layer.id === 'aggregate-outer')?.filter)).toContain('reference');
    expect(JSON.stringify(layers.find(layer => layer.id === 'aggregate-outer')?.filter)).not.toContain('source_provided_unverified');
    expect(layers.find(layer => layer.id === 'source-coordinate-points')?.filter).toEqual(['all', ['!', ['has', 'cluster']], ['in', ['get', 'kind'], ['literal', ['source-coordinate', 'provider_address_point_private']]]]);
    expect(layers.find(layer => layer.id === 'source-coordinate-points')?.filter).toContainEqual(['in', ['get', 'kind'], ['literal', ['source-coordinate', 'provider_address_point_private']]]);
    expect(JSON.stringify(layers.find(layer => layer.id === 'source-coordinate-points')?.paint?.['circle-color']))
      .toContain('category_keys');
    expect(JSON.stringify(layers.find(layer => layer.id === 'v1-source-pins')?.layout['icon-image']))
      .toContain('v1-pin-green');
    expect(JSON.stringify(layers.find(layer => layer.id === 'v1-source-pins')?.layout['icon-image']))
      .toContain('category_keys');
    expect(hasRealPreviewMapLayers({
      getSource: (id: string) => sources[id],
      getLayer: (id: string) => layers.find(layer => layer.id === id),
    } as any)).toBe(true);
  });

  it('uses a 250m geographic radius only while an approximate record is selected', () => {
    expect(JSON.stringify(referenceRadiusExpression(0.25))).toContain('250');
    const changes: Array<[string, string, unknown]> = [];
    const map = { getLayer: () => ({}), setPaintProperty: (id: string, property: string, value: unknown) => changes.push([id, property, value]), setLayoutProperty() {} };
    applyRealPreviewVisualSettings(map as any, { referenceRadiusKm: 0.25, referenceOpacity: 0.22, coordinateRadius: 7, showReferenceLabels: false, selectedKey: 'synthetic-key' });
    expect(changes.find(change => change[1] === 'circle-opacity')?.[2]).toEqual(['case', ['==', ['get', 'key'], 'synthetic-key'], expect.closeTo(0.34), 0]);
    expect(changes.find(change => change[1] === 'circle-stroke-opacity')?.[2]).toEqual(['case', ['==', ['get', 'key'], 'synthetic-key'], 0.96, 0]);
  });

  it('keeps approximate singleton markers visible in either exact-pin presentation mode', async () => {
    expect(REAL_PREVIEW_LAYER_IDS).toContain('approx-reference-signal');
    const changes: Array<[string, string, unknown]> = [];
    const map = {
      hasImage: () => true,
      getLayer: (id: string) => id === 'v1-source-pins' ? {} : undefined,
      setLayoutProperty: (id: string, property: string, value: unknown) => changes.push([id, property, value]),
    };
    await setRealPreviewPinMode(map as any, false, '');
    await setRealPreviewPinMode(map as any, true, '');
    expect(changes).toEqual([
      ['source-coordinate-points', 'visibility', 'visible'],
      ['v1-source-shadows', 'visibility', 'none'],
      ['v1-source-pins', 'visibility', 'none'],
      ['source-coordinate-points', 'visibility', 'none'],
      ['v1-source-shadows', 'visibility', 'visible'],
      ['v1-source-pins', 'visibility', 'visible'],
    ]);
    expect(changes.some(([id]) => id === 'approx-reference-signal')).toBe(false);
  });

  it('detects an incomplete native projection so callers can restore every overlay', () => {
    expect(hasRealPreviewMapLayers({ getSource: () => ({}), getLayer: (id: string) => id === 'clusters' ? {} : undefined } as any)).toBe(false);
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
