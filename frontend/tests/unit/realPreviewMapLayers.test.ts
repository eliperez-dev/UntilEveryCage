import { describe, expect, it } from 'vitest';
import { addRealPreviewMapLayers } from '../../src/design-lab/components/realPreviewMapLayers';

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
    expect(sources.locations).toMatchObject({ cluster: true, clusterRadius: 50, clusterMaxZoom: 14, clusterProperties: { representedCount: ['+', ['get', 'weight']] } });
    expect(layers.find(layer => layer.id === 'clusters')?.filter).toEqual(['has', 'cluster']);
    expect(layers.find(layer => layer.id === 'aggregate-outer')?.filter).toEqual(['all', ['!', ['has', 'cluster']], ['==', ['get', 'kind'], 'reference']]);
    expect(layers.find(layer => layer.id === 'source-coordinate-points')?.filter).toEqual(['all', ['!', ['has', 'cluster']], ['==', ['get', 'kind'], 'source-coordinate']]);
  });
});
