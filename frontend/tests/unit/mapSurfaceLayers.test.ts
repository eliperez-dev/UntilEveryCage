import { describe, expect, it } from 'vitest';
import {
  JSON_LOCATION_LAYER_IDS,
  MVT_LOCATION_LAYER_IDS,
  addMvtLocationLayers,
  createBaseStyle,
  mvtTileUrl,
  removeLocationLayers,
} from '../../src/design-lab/components/mapSurfaceLayers';

describe('MapSurface layer contract', () => {
  it('keeps the private tile request relative to the same-origin proxy', () => {
    expect(mvtTileUrl()).toEqual([
      '/dev/real-preview/map/tiles/{z}/{x}/{y}',
    ]);
  });

  it('encodes source filters without changing the private endpoint', () => {
    expect(mvtTileUrl('fr.dgal / section-i')).toEqual([
      '/dev/real-preview/map/tiles/{z}/{x}/{y}?source_id=fr.dgal%20%2F%20section-i',
    ]);
  });

  it('keeps transport below location overlays and delegates zoom visibility to tiles', () => {
    const style = createBaseStyle('satellite') as { layers: { id: string }[] };
    expect(style.layers.map((layer) => layer.id)).toEqual(['base', 'transport']);
    const layers: any[] = [];
    addMvtLocationLayers({
      addSource() {}, addLayer: (layer) => layers.push(layer),
      getLayer: () => undefined, getSource: () => undefined,
      removeLayer() {}, removeSource() {},
    });
    expect(layers.filter((layer) => layer.id.startsWith('mvt-'))).toHaveLength(MVT_LOCATION_LAYER_IDS.length);
    expect(layers.every((layer) => layer.minzoom === undefined && layer.maxzoom === undefined)).toBe(true);
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
    expect(removedSources).toEqual(['locations', 'preview-mvt']);
  });
});
