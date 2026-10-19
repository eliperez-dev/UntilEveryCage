import { describe, expect, it } from 'vitest';
import {
  JSON_LOCATION_LAYER_IDS,
  MVT_LOCATION_LAYER_IDS,
  addMvtLocationLayers,
  createMvtReferenceAreas,
  createBaseStyle,
  isMvtReferenceKind,
  mvtTileUrl,
  removeLocationLayers,
  setMvtClusterCutoff,
  MVT_SOURCE_ID,
  MVT_SOURCE_LAYER,
} from '../../src/design-lab/components/mapSurfaceLayers';

describe('MapSurface layer contract', () => {
  it('keeps the private tile request relative to the same-origin proxy', () => {
    expect(mvtTileUrl()).toEqual([
      '/dev/real-preview/map/tiles/{z}/{x}/{y}?cluster_cutoff=7.5',
    ]);
  });

  it('encodes source filters without changing the private endpoint', () => {
    expect(mvtTileUrl('fr.dgal / section-i')).toEqual([
      '/dev/real-preview/map/tiles/{z}/{x}/{y}?cluster_cutoff=7.5&source_id=fr.dgal%20%2F%20section-i',
    ]);
  });

  it('updates the cached MVT source for a valid whole or fractional cutoff', () => {
    let tiles: string[] = [];
    const source: any = { setTiles: (value: string[]) => { tiles = value; } };
    setMvtClusterCutoff({ getSource: (id: string) => id === MVT_SOURCE_ID ? source : undefined } as any, 'be.locations', 8.5);
    expect(source.roundZoom).toBe(true);
    expect(tiles[0]).toContain('cluster_cutoff=8.5');
    setMvtClusterCutoff({ getSource: () => source } as any, undefined, 9);
    expect(source.roundZoom).toBe(false);
    expect(tiles[0]).toContain('cluster_cutoff=9');
  });

  it('keeps transport below location overlays and delegates zoom visibility to tiles', () => {
    const style = createBaseStyle('satellite') as { layers: { id: string }[] };
    expect(style.layers.map((layer) => layer.id)).toEqual(['base', 'transport']);
    const layers: any[] = [];
    const sources: Record<string, any> = {};
    addMvtLocationLayers({
      addSource: (id, source) => { sources[id] = source; }, addLayer: (layer) => layers.push(layer),
      getLayer: () => undefined, getSource: () => undefined,
      removeLayer() {}, removeSource() {},
    });
    expect(sources[MVT_SOURCE_ID]).toMatchObject({
      roundZoom: true,
      promoteId: { [MVT_SOURCE_LAYER]: 'feature_key' },
    });
    expect(layers.filter((layer) => layer.id.startsWith('mvt-'))).toHaveLength(MVT_LOCATION_LAYER_IDS.length);
    expect(layers.every((layer) => layer.minzoom === undefined && layer.maxzoom === undefined)).toBe(true);
    expect(layers.find((layer) => layer.id === 'mvt-v1-source-pins')?.layout).toMatchObject({
      visibility: 'none', 'icon-image': 'v1-pin-red', 'icon-anchor': 'bottom',
    });
    expect(layers.find((layer) => layer.id === 'mvt-reference-outer')).toBeUndefined();
    expect(layers.find((layer) => layer.id === 'mvt-reference-center')).toMatchObject({
      type: 'symbol',
      filter: ['any', ['==', ['get', 'kind'], 'city_reference'], ['==', ['get', 'kind'], 'coarse_reference']],
      layout: { 'icon-image': 'v1-pin-grey' },
    });
    expect(layers.find((layer) => layer.id === 'mvt-reference-count')?.layout['text-field'])
      .toEqual(['case', ['>', ['coalesce', ['get', 'count'], 1], 1], ['to-string', ['coalesce', ['get', 'count'], 1]], '']);
  });

  it('creates selected-only 250m geographic areas for city and coarse references, never source points', () => {
    const areas = createMvtReferenceAreas([
      { properties: { kind: 'city_reference', feature_key: 'city' }, geometry: { type: 'Point', coordinates: [4.35, 50.85] } },
      { properties: { kind: 'coarse_reference', feature_key: 'coarse' }, geometry: { type: 'Point', coordinates: [151.2, -33.8] } },
      { properties: { kind: 'source_coordinate', feature_key: 'source' }, geometry: { type: 'Point', coordinates: [0, 0] } },
    ], 0.25);
    expect(areas.features).toHaveLength(2);
    expect(areas.features.map((feature: any) => feature.properties.feature_key)).toEqual(['city', 'coarse']);
    expect(areas.features.every((feature: any) => feature.geometry.coordinates[0].length === 25)).toBe(true);
    const ring = (areas.features[1] as any).geometry.coordinates[0];
    const toRadians = (value: number) => value * Math.PI / 180;
    const distanceKm = 6371.0088 * Math.acos(Math.sin(toRadians(-33.8)) * Math.sin(toRadians(ring[0][1])) + Math.cos(toRadians(-33.8)) * Math.cos(toRadians(ring[0][1])) * Math.cos(toRadians(ring[0][0] - 151.2)));
    expect(distanceKm).toBeCloseTo(0.25, 3);
    expect(isMvtReferenceKind('city_reference')).toBe(true);
    expect(isMvtReferenceKind('coarse_reference')).toBe(true);
    expect(isMvtReferenceKind('source_coordinate')).toBe(false);
    // A cold or deselected source is represented by an empty area collection.
    expect(createMvtReferenceAreas([], 0.25).features).toEqual([]);
  });

  it('tears down both projections before the selected path attaches', () => {
    const removedLayers: string[] = [];
    const removedSources: string[] = [];
    const map = {
      addLayer() {},
      addSource() {},
      getLayer: () => ({}),
      getSource: () => ({}),
      removeLayer: (id: string) => removedLayers.push(id),
      removeSource: (id: string) => removedSources.push(id),
    };

    removeLocationLayers(map);

    expect(removedLayers).toEqual([
      ...JSON_LOCATION_LAYER_IDS,
      ...MVT_LOCATION_LAYER_IDS,
    ]);
    expect(removedSources).toEqual(['locations', 'mvt-reference-areas', 'preview-mvt']);
  });
});
