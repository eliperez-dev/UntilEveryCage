import { describe, expect, it, vi } from 'vitest';
import { CLUSTERING_POPULATION_THRESHOLD, clusterFilteredPopulation, maskPublicMapMatches, representedMappedCount, resizeWorkspaceMap } from '../../src/design-lab/components/mapWorkspace';
import { createSearchRadiusArea } from '../../src/design-lab/components/mapSurfaceLayers';
import type { JsonMapCollection } from '../../src/design-lab/components/jsonMapFallback';

const feature = (id: string, weight = 1) => ({
  type: 'Feature' as const,
  id,
  geometry: { type: 'Point' as const, coordinates: [0, 0] as [number, number] },
  properties: { facility_id: id, weight },
});
const collection = (...features: ReturnType<typeof feature>[]): JsonMapCollection => ({ type: 'FeatureCollection', features });

describe('map workspace population', () => {
  it('uses the complete filtered represented population, including weighted references', () => {
    expect(CLUSTERING_POPULATION_THRESHOLD).toBe(2800);
    const below = collection(feature('reference', 2798), feature('coordinate'));
    expect(representedMappedCount(below)).toBe(2799);
    expect(clusterFilteredPopulation(below)).toBe(false);
    const threshold = collection(feature('reference', 2799), feature('coordinate'));
    expect(clusterFilteredPopulation(threshold)).toBe(true);
    expect(clusterFilteredPopulation(collection())).toBe(false);
  });

  it('retains explicit debug choices on either side of the automatic threshold', () => {
    expect(clusterFilteredPopulation(collection(feature('small')), true)).toBe(true);
    expect(clusterFilteredPopulation(collection(feature('large', 4000)), false)).toBe(false);
  });

  it('uses every matching mapped ID rather than the loaded result page', () => {
    const full = collection(...Array.from({ length: 350 }, (_, index) => feature(`unit-${index}`)));
    const matches = new Set(['unit-1', 'unit-150', 'unit-349']);
    const filtered = maskPublicMapMatches(full, matches, 'ready');
    expect(filtered.features.map(item => item.id)).toEqual(['unit-1', 'unit-150', 'unit-349']);
    expect(full.features).toHaveLength(350);
    expect(maskPublicMapMatches(full, null, 'idle')).toBe(full);
    expect(maskPublicMapMatches(full, new Set(), 'ready').features).toHaveLength(0);
  });

  it('never falls back to all pins while a matching request loads or fails', () => {
    const full = collection(feature('previous-match'));
    for (const status of ['loading', 'error'] as const) {
      expect(maskPublicMapMatches(full, null, status).features).toHaveLength(0);
      expect(maskPublicMapMatches(full, new Set(['previous-match']), status).features).toHaveLength(0);
    }
  });
});

describe('map workspace resize', () => {
  it('centers the selected location in the resized renderer without touching sources', () => {
    const map = { resize: vi.fn(), jumpTo: vi.fn(), getSource: vi.fn(), addSource: vi.fn() };
    resizeWorkspaceMap(map, [0, 51], false);
    expect(map.resize).toHaveBeenCalledOnce();
    expect(map.jumpTo).toHaveBeenCalledWith({ center: [0, 51] });
    expect(map.getSource).not.toHaveBeenCalled();
    expect(map.addSource).not.toHaveBeenCalled();
  });

  it('preserves an active selection flight or a camera without selection', () => {
    const map = { resize: vi.fn(), jumpTo: vi.fn() };
    resizeWorkspaceMap(map, [0, 51], true);
    resizeWorkspaceMap(map, null, false);
    expect(map.resize).toHaveBeenCalledTimes(2);
    expect(map.jumpTo).not.toHaveBeenCalled();
  });
});

describe('explicit city search radius', () => {
  it('makes a closed geographic radius and clears it without a scope', () => {
    const area = createSearchRadiusArea({ latitude: 0, longitude: 0, radiusKm: 25 });
    expect(area.features).toHaveLength(1);
    const ring = area.features[0]!.geometry.coordinates[0]!;
    expect(ring[0]![1]).toBeCloseTo(25 / 6371.0088 * 180 / Math.PI, 6);
    expect(ring.at(-1)![0]).toBeCloseTo(ring[0]![0], 8);
    expect(ring.at(-1)![1]).toBeCloseTo(ring[0]![1], 8);
    expect(area.features[0]!.properties).toEqual({ scope: 'search-radius' });
    expect(createSearchRadiusArea(null).features).toHaveLength(0);
    expect(createSearchRadiusArea({ latitude: 100, longitude: 0, radiusKm: 25 }).features).toHaveLength(0);
  });
});
