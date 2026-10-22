import { describe, expect, it } from 'vitest';
import {
  JSON_LOCATION_LAYER_IDS,
  MVT_LOCATION_LAYER_IDS,
  addMvtLocationLayers,
  createMvtReferenceAreas,
  createSelectedApproximateReferenceArea,
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

  it('creates selected-only 250m geographic areas for city and coarse MVT references, never source points', () => {
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

  it('keeps the selected public approximate area 250m across at multiple latitudes', () => {
    const earthRadiusKm = 6371.0088;
    const haversineKm = (from: [number, number], to: [number, number]) => {
      const radians = (value: number) => value * Math.PI / 180;
      const dLat = radians(to[1] - from[1]);
      const dLon = radians(to[0] - from[0]);
      const lat1 = radians(from[1]);
      const lat2 = radians(to[1]);
      const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
      return 2 * earthRadiusKm * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    };

    for (const [longitude, latitude] of [[4.35, 50.85], [151.2, -33.8], [-72.4, 0], [12.5, 78.2]] as [number, number][]) {
      const point = { type: 'Feature', properties: { key: `approx-${latitude}`, kind: 'reference', precision: 'approximate' }, geometry: { type: 'Point', coordinates: [longitude, latitude] } };
      const area = createSelectedApproximateReferenceArea([point], `approx-${latitude}`, 0.25);
      expect(area.features).toHaveLength(1);
      expect(area.features[0]?.properties).toEqual({ key: `approx-${latitude}` });
      const ring = area.features[0]!.geometry.coordinates[0]!;
      expect(ring).toHaveLength(25);
      expect(ring[0]).toEqual(ring.at(-1));
      for (const coordinate of ring.slice(0, -1)) {
        expect(haversineKm([longitude, latitude], coordinate)).toBeCloseTo(0.25, 5);
      }
    }
  });

  it('creates no public reference area for exact or source-coordinate features and clears when deselected', () => {
    const points = [
      { type: 'Feature', properties: { key: 'exact', kind: 'source-coordinate', precision: 'exact' }, geometry: { type: 'Point', coordinates: [4, 51] } },
      { type: 'Feature', properties: { key: 'not-reference', kind: 'source-coordinate', precision: 'approximate' }, geometry: { type: 'Point', coordinates: [4, 51] } },
      { type: 'Feature', properties: { key: 'city', kind: 'reference', precision: 'city' }, geometry: { type: 'Point', coordinates: [4, 51] } },
    ];
    expect(createSelectedApproximateReferenceArea(points, 'exact', 0.25).features).toHaveLength(0);
    expect(createSelectedApproximateReferenceArea(points, 'not-reference', 0.25).features).toHaveLength(0);
    expect(createSelectedApproximateReferenceArea(points, 'city', 0.25).features).toHaveLength(0);
    expect(createSelectedApproximateReferenceArea(points, null, 0.25).features).toHaveLength(0);
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
    expect(removedSources).toEqual(['locations', 'approximate-reference-area', 'mvt-reference-areas', 'preview-mvt']);
  });
});
