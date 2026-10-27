import { describe, expect, it, vi } from 'vitest';
import { addRealPreviewMapLayers, applyRealPreviewVisualSettings, hasRealPreviewMapLayers, nativeClusterMaxZoom, referenceRadiusExpression, setClusterTileRounding, setRealPreviewPinMode, useRoundedClusterTiles, REAL_PREVIEW_LAYER_IDS, DEFAULT_CLUSTER_MAX_ZOOM } from '../../src/design-lab/components/realPreviewMapLayers';

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
    expect(Object.keys(sources)).toEqual(['locations', 'approximate-reference-area']);
    expect(sources['approximate-reference-area']).toMatchObject({ type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    expect(sources.locations).toMatchObject({ cluster: true, clusterRadius: 50, clusterMaxZoom: 8, roundZoom: false, clusterProperties: { representedCount: ['+', ['get', 'weight']], approximateCount: ['+', ['case', ['any', ['==', ['get', 'precision'], 'approximate'], ['==', ['get', 'precision'], 'city'], ['==', ['get', 'precision'], 'locality_reference_coarse']], ['get', 'weight'], 0]] } });
    expect(layers.find(layer => layer.id === 'clusters')?.filter).toEqual(['has', 'cluster']);
    expect(layers.find(layer => layer.id === 'clusters')?.layout['icon-image'])
      .toEqual(['step', ['get', 'representedCount'], 'cluster-low', 10, 'cluster-mid', 100, 'cluster-high', 1001, 'cluster-very-high']);
    expect(layers.find(layer => layer.id === 'approx-reference-points')?.maxzoom).toBeUndefined();
    expect(JSON.stringify(layers.find(layer => layer.id === 'approx-reference-points')?.layout['icon-image'])).toContain('v1-pin-graphite');
    expect(JSON.stringify(layers.find(layer => layer.id === 'source-coordinate-points')?.paint['circle-color'])).toContain('#515B60');
    expect(layers.find(layer => layer.id === 'approx-reference-points')).toMatchObject({
      type: 'symbol',
      layout: {
        'icon-image': expect.any(Array), 'icon-anchor': 'bottom', 'icon-size': 0.4,
        'text-field': ['case', ['>', ['get', 'weight'], 1], ['to-string', ['get', 'weight']], ''],
      },
      paint: { 'text-color': '#172019' },
    });
    expect(layers.find(layer => layer.id === 'aggregate-count')?.filter).toEqual([
      'all', ['!', ['has', 'cluster']], ['in', ['get', 'kind'], ['literal', ['reference', 'provider_locality_approximate']]],
      ['!', ['any', ['==', ['get', 'precision'], 'city'], ['==', ['get', 'precision'], 'city_reference_approximate'], ['==', ['get', 'precision'], 'provider_locality_approximate'], ['==', ['get', 'precision'], 'locality_reference_coarse']]],
    ]);
    const approximatePins = layers.find(layer => layer.id === 'approx-reference-pins');
    expect(approximatePins).toMatchObject({
      type: 'symbol',
      filter: ['all', ['!', ['has', 'cluster']], ['in', ['get', 'kind'], ['literal', ['reference', 'provider_locality_approximate']]], ['==', ['get', 'precision'], 'approximate']],
      layout: { visibility: 'none', 'icon-anchor': 'bottom', 'icon-size': 0.4, 'text-field': ['case', ['>', ['get', 'weight'], 1], ['to-string', ['get', 'weight']], ''] },
    });
    expect(JSON.stringify(approximatePins.layout['icon-image'])).toContain('category_keys');
    expect(JSON.stringify(approximatePins.layout['icon-image'])).toContain('v1-pin-red');
    expect(layers.find(layer => layer.id === 'approx-reference-circles')).toMatchObject({
      type: 'circle', layout: { visibility: 'none' }, paint: { 'circle-radius': 6.5, 'circle-opacity': 0.94 },
    });
    expect(layers.find(layer => layer.id === 'source-coordinate-points')?.layout?.visibility).toBe('none');
    expect(layers.find(layer => layer.id === 'approx-reference-cue')).toMatchObject({
      type: 'symbol', layout: {
        visibility: 'none', 'icon-image': 'approximation-mark', 'icon-size': 0.4,
        'icon-offset': [17, -21], 'icon-allow-overlap': true,
      },
    });
    expect(layers.find(layer => layer.id === 'approx-reference-cue')?.layout).not.toHaveProperty('text-field');
    expect(JSON.stringify(layers.find(layer => layer.id === 'approx-reference-circles').paint['circle-color']))
      .toEqual(JSON.stringify(layers.find(layer => layer.id === 'source-coordinate-points').paint['circle-color']));
    expect(layers.find(layer => layer.id === 'approximate-reference-area-fill')).toMatchObject({
      type: 'fill', source: 'approximate-reference-area', paint: { 'fill-color': '#d8473f', 'fill-opacity': 0.16 },
    });
    expect(layers.find(layer => layer.id === 'approximate-reference-area-outline')).toMatchObject({
      type: 'line', source: 'approximate-reference-area', paint: { 'line-color': '#ff695c', 'line-opacity': 0.92 },
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
      .toContain('v1-pin-yellow');
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

  it('scales visible facility symbols and matching shadows without rebuilding the source', () => {
    const changes: Array<[string, string, unknown]> = [];
    const map = { getLayer: () => ({}), setPaintProperty() {}, setLayoutProperty: (id: string, property: string, value: unknown) => changes.push([id, property, value]) };
    applyRealPreviewVisualSettings(map as any, { referenceRadiusKm: 0.25, referenceOpacity: 0.22, coordinateRadius: 7, pinScale: 1.4, showReferenceLabels: false });
    expect(changes).toContainEqual(['v1-source-pins', 'icon-size', 0.7]);
    expect(changes).toContainEqual(['v1-source-shadows', 'icon-size', 1.4]);
    expect(changes).toContainEqual(['approx-reference-pins', 'icon-size', 0.7]);
    expect(changes).toContainEqual(['approx-reference-shadows', 'icon-size', 1.4]);
  });

  it('keeps approximate singleton markers visible in either exact-pin presentation mode', async () => {
    expect(REAL_PREVIEW_LAYER_IDS).toContain('approx-reference-pins');
    const changes: Array<[string, string, unknown]> = [];
    const map = {
      hasImage: () => true,
      getLayer: (id: string) => ['v1-source-pins', 'source-coordinate-points', 'approx-reference-circles', 'approx-reference-shadows', 'approx-reference-pins', 'approx-reference-cue'].includes(id) ? {} : undefined,
      setLayoutProperty: (id: string, property: string, value: unknown) => changes.push([id, property, value]),
    };
    await setRealPreviewPinMode(map as any, false, '');
    await setRealPreviewPinMode(map as any, true, '');
    expect(changes).toEqual([
      ['source-coordinate-points', 'visibility', 'visible'],
      ['v1-source-shadows', 'visibility', 'none'],
      ['v1-source-pins', 'visibility', 'none'],
      ['approx-reference-circles', 'visibility', 'visible'],
      ['approx-reference-shadows', 'visibility', 'none'],
      ['approx-reference-pins', 'visibility', 'none'],
      ['approx-reference-cue', 'visibility', 'none'],
      ['source-coordinate-points', 'visibility', 'none'],
      ['approx-reference-circles', 'visibility', 'none'],
      ['source-coordinate-points', 'visibility', 'none'],
      ['v1-source-shadows', 'visibility', 'visible'],
      ['v1-source-pins', 'visibility', 'visible'],
      ['approx-reference-circles', 'visibility', 'none'],
      ['approx-reference-shadows', 'visibility', 'visible'],
      ['approx-reference-pins', 'visibility', 'visible'],
      ['approx-reference-cue', 'visibility', 'visible'],
    ]);
  });

  it('keeps fallback dots hidden until V1 artwork is ready and ignores stale mode requests', async () => {
    const changes: Array<[string, string, unknown]> = [];
    const images = new Set<string>();
    const imageData = { data: new Uint8ClampedArray(24 * 24 * 4), width: 24, height: 24 };
    const context = {
      beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(), stroke: vi.fn(), moveTo: vi.fn(), bezierCurveTo: vi.fn(),
      getImageData: vi.fn(() => imageData),
      set fillStyle(_value: string) {}, set strokeStyle(_value: string) {}, set lineWidth(_value: number) {}, set lineCap(_value: string) {},
    };
    const canvasContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as any);
    let releaseFirstImage!: (value: { data: unknown }) => void;
    let firstLoad = true;
    const map = {
      hasImage: (id: string) => images.has(id),
      loadImage: () => firstLoad
        ? (firstLoad = false, new Promise<{ data: unknown }>(resolve => { releaseFirstImage = resolve; }))
        : Promise.resolve({ data: {} }),
      addImage: (id: string) => images.add(id),
      getLayer: (id: string) => ['v1-source-pins', 'source-coordinate-points', 'approx-reference-circles', 'approx-reference-shadows', 'approx-reference-pins', 'approx-reference-cue'].includes(id) ? {} : undefined,
      setLayoutProperty: (id: string, property: string, value: unknown) => changes.push([id, property, value]),
    };
    const loading = setRealPreviewPinMode(map as any, true, '/pins/');
    expect(changes).toContainEqual(['source-coordinate-points', 'visibility', 'none']);
    expect(changes).toContainEqual(['approx-reference-circles', 'visibility', 'none']);
    await setRealPreviewPinMode(map as any, false, '/pins/');
    releaseFirstImage({ data: {} });
    await loading;
    expect(images.has('approximation-mark')).toBe(true);
    expect(changes.slice(-7)).toEqual([
      ['source-coordinate-points', 'visibility', 'visible'],
      ['v1-source-shadows', 'visibility', 'none'],
      ['v1-source-pins', 'visibility', 'none'],
      ['approx-reference-circles', 'visibility', 'visible'],
      ['approx-reference-shadows', 'visibility', 'none'],
      ['approx-reference-pins', 'visibility', 'none'],
      ['approx-reference-cue', 'visibility', 'none'],
    ]);
    expect(changes).not.toContainEqual(['approx-reference-cue', 'visibility', 'visible']);
    await setRealPreviewPinMode(map as any, true, '/pins/');
    expect(changes.at(-1)).toEqual(['approx-reference-cue', 'visibility', 'visible']);
    canvasContext.mockRestore();
  });

  it('detects an incomplete native projection so callers can restore every overlay', () => {
    expect(hasRealPreviewMapLayers({ getSource: () => ({}), getLayer: (id: string) => id === 'clusters' ? {} : undefined } as any)).toBe(false);
  });

  it('uses the tile zoom transition matching whole and half camera zoom cutoffs', () => {
    expect(DEFAULT_CLUSTER_MAX_ZOOM).toBe(9);
    expect(nativeClusterMaxZoom(DEFAULT_CLUSTER_MAX_ZOOM)).toBe(8);
    expect(useRoundedClusterTiles(DEFAULT_CLUSTER_MAX_ZOOM)).toBe(false);
    expect(nativeClusterMaxZoom(7.5)).toBe(7);
    expect(useRoundedClusterTiles(7.5)).toBe(true);
    expect(nativeClusterMaxZoom(8)).toBe(7);
    expect(useRoundedClusterTiles(8)).toBe(false);
    expect(nativeClusterMaxZoom(6.5)).toBe(6);
    const unsupportedMap = { getSource: () => Object.freeze({}) } as any;
    expect(setClusterTileRounding(unsupportedMap, 7.5)).toBe(false);
  });
});
