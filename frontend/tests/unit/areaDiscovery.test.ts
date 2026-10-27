import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_LAB_STATE } from '../../src/design-lab/contract';
import { encodeLabHash, reduceLabState } from '../../src/design-lab/state';
import { emptyAreaSummary, summarizeMappedArea } from '../../src/features/search/areaSummary';
import { DEFAULT_NEARBY_RADIUS_KM, requestDeviceLocation } from '../../src/features/search/nearbySearch';
import { publicSearchFilters } from '../../src/features/search/powerSearch';
import type { JsonMapFeature } from '../../src/design-lab/components/jsonMapFallback';

const point = (id: string, category: string, source: string, precision: string, longitude = 10, latitude = 50): JsonMapFeature => ({
  type: 'Feature', id, geometry: { type: 'Point', coordinates: [longitude, latitude] },
  properties: { facility_id: id, category_key: category, source_id: source, precision, weight: 1 },
});
afterEach(() => vi.restoreAllMocks());

describe('complete mapped area summary', () => {
  it('counts all distinct facilities across pages and makes display categories add up once', () => {
    const features = Array.from({ length: 350 }, (_, index) => point(`synthetic-${index}`,
      index < 200 ? 'processing_and_preparation' : 'slaughter', index < 300 ? 'source-a' : 'source-b',
      index % 2 ? 'source_reported' : 'approximate', 10 + index / 1000));
    const summary = summarizeMappedArea({ type: 'FeatureCollection', features: [...features, features[0]!] });
    expect(summary.total).toBe(350);
    expect(summary.categories.reduce((sum, item) => sum + item.count, 0)).toBe(350);
    expect(summary.categories.find(item => item.key === 'processing_and_preparation')?.count).toBe(200);
    expect(summary.sourceCount).toBe(2);
    expect(summary.sourceReportedCount).toBe(175);
    expect(summary.approximateCount).toBe(175);
    expect(summary.bounds).toEqual({ west: 10, east: 10.349, south: 50, north: 50 });
  });
  it('does not invent animal totals or retain stale counts in unavailable states', () => {
    const summary = summarizeMappedArea({ type: 'FeatureCollection', features: [
      point('valid', 'unknown', 'source-a', 'exact'), point('invalid', 'slaughter', 'source-b', 'exact', NaN),
    ] });
    expect(summary.total).toBe(1);
    expect(summary.categories.find(item => item.key === 'unclassified')?.count).toBe(1);
    expect(summary).not.toHaveProperty('animals');
    for (const status of ['loading', 'error'] as const) expect(emptyAreaSummary(status)).toMatchObject({ status, total: 0, bounds: null, sourceCount: 0 });
    expect(summarizeMappedArea({ type: 'FeatureCollection', features: [] })).toMatchObject({ status: 'ready', total: 0, bounds: null });
  });
});

describe('explicit nearby search', () => {
  it('atomically searches100miles while retaining query, filters and the public navigation camera', () => {
    const before = { ...DEFAULT_LAB_STATE, query: 'synthetic evidence', selectedId: 'synthetic-id',
      filters: { ...DEFAULT_LAB_STATE.filters, categories: ['slaughter'], countries: ['US'] } };
    const next = reduceLabState(before, { type: 'near-device', value: { latitude: 39.12512, longitude: -95.74883 } });
    expect(next.query).toBe(before.query); expect(next.filters).toBe(before.filters);
    expect(next.searchScope).toMatchObject({ kind: 'radius', radiusKm: DEFAULT_NEARBY_RADIUS_KM, deviceDerived: true });
    expect(next).toMatchObject({ selectedId: null, listOpen: true, navigationViewport: before.viewport });
    expect(publicSearchFilters(next)).toMatchObject({ q: before.query, latitude: 39.12512, longitude: -95.74883, radius_km: 160.9344 });
    const panned = reduceLabState(next, { type: 'viewport', value: { ...next.viewport, centerLat: 39.2, centerLon: -95.8 } });
    const encoded = encodeLabHash(panned, false, true);
    for (const value of ['39.12512', '-95.74883', '39.2', '-95.8', 'radius', 'synthetic%20evidence']) expect(encoded).not.toContain(value);
    expect(encoded).toContain('country=US');
    expect(reduceLabState(before, { type: 'near-device', value: { latitude: NaN, longitude: 0 } })).toBe(before);
  });
  it('only requests permission on invocation and ignores callbacks after cancellation', async () => {
    let success: PositionCallback | undefined;
    const getCurrentPosition = vi.fn((callback: PositionCallback) => { success = callback; });
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition } });
    expect(getCurrentPosition).not.toHaveBeenCalled();
    const controller = new AbortController();
    const result = requestDeviceLocation(controller.signal);
    expect(getCurrentPosition).toHaveBeenCalledOnce();
    controller.abort();
    await expect(result).rejects.toMatchObject({ name: 'AbortError' });
    success?.({ coords: { latitude: 1, longitude: 2 } } as GeolocationPosition);
    expect(getCurrentPosition.mock.calls[0]?.[0]).toBeTypeOf('function');
  });
  it('validates coordinates and reports permission failure without a network request', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch');
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition: (_success: PositionCallback, fail: PositionErrorCallback) => fail({ code: 1 } as GeolocationPositionError) } });
    await expect(requestDeviceLocation()).rejects.toThrow('Location permission was denied.');
    expect(fetcher).not.toHaveBeenCalled();
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition: (success: PositionCallback) => success({ coords: { latitude: 91, longitude: 0 } } as GeolocationPosition) } });
    await expect(requestDeviceLocation()).rejects.toThrow('Your location is unavailable.');
  });
});
