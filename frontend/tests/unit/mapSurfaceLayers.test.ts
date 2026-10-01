import { describe, expect, it } from 'vitest';
import {
  JSON_LOCATION_LAYER_IDS,
  MVT_LOCATION_LAYER_IDS,
  addMvtLocationLayers,
  createBaseStyle,
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
