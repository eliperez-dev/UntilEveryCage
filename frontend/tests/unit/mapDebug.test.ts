import { describe, expect, it } from 'vitest';
import { safeDiagnosticSnapshot, mapFeedCacheDiagnostics, publicMapLoadingLabel, type DiagnosticInput } from '../../src/design-lab/components/mapDebug';

const input: DiagnosticInput = {
  mode: 'public-release', release: 'release-test', manifest: 'a'.repeat(64), restrictionGeneration: 3,
  search: { total: 900, shown: 100, listStatus: 'ready', matchesStatus: 'ready', matchingMappedCount: 850, scope: 'area' },
  loadedMapped: 5000, filteredMapped: 850, renderedMarks: 120, feedRequests: 1, decodedBytes: 256000,
  cacheEntries: 1, feedMs: 30, indexMs: 50, rebuildMs: 20, cameraMoveendMs: 40, cameraIdleMs: 120,
  width: 800, height: 600, canvasWidth: 1600, canvasHeight: 1200, zoom: 7, bearing: 0, pitch: 0,
  clusterMode: 'auto', clusterRadius: 50, clusterMaxZoom: 9, pinScale: 1,
  layout: { panelWidthPercent: 100 / 3, rowPadding: 16, typeScale: 1 },
};

describe('explicit map diagnostic export', () => {
  it('reads cached public projection metadata and preserves the private feed shape', () => {
    expect(mapFeedCacheDiagnostics({ meta: { cacheStatus: 'hit', decodedBytes: 48000 } }))
      .toEqual({ cacheStatus: 'hit', decodedBytes: 48000 });
    expect(mapFeedCacheDiagnostics({ cacheStatus: 'miss', decodedBytes: 1234 }))
      .toEqual({ cacheStatus: 'miss', decodedBytes: 1234 });
    expect(mapFeedCacheDiagnostics({ meta: {} })).toEqual({ cacheStatus: 'unavailable', decodedBytes: null });
    expect(mapFeedCacheDiagnostics({ meta: { decodedBytes: 0 } }).decodedBytes).toBe(0);
  });

  it('shows one public loading message and distinguishes a cached restore from a cold index build', () => {
    expect(publicMapLoadingLabel('unavailable', null)).toBe('Loading map…');
    expect(publicMapLoadingLabel('hit', null)).toBe('Restoring cached map…');
    expect(publicMapLoadingLabel('miss', 'lookup')).toBe('Restoring cached map…');
    expect(publicMapLoadingLabel('hit', 'building')).toBe('First time loading. This may take a while…');
    expect(publicMapLoadingLabel('hit', 'restored')).toBe('Restoring cached map…');
  });
  it('includes useful complete matching counts, actual timings and settings', () => {
    const snapshot = safeDiagnosticSnapshot(input);
    expect(snapshot.search).toEqual(input.search);
    expect(snapshot.population).toEqual({ loaded: 5000, filtered: 850, renderedMarks: 120, clusteringThreshold: 3000 });
    expect(snapshot.timingMs).toEqual({ feed: 30, index: 50, rebuild: 20, cameraMoveend: 40, cameraIdle: 120 });
    expect(snapshot.tuning.clusterMode).toBe('auto');
  });
  it('exports camera idle delay and provider counters as finite aggregates only', () => {
    const snapshot = safeDiagnosticSnapshot({ ...input, clusterMotionIdleDelay: 250,
      cacheMetrics: { indexState: 'restored', builds: 0, restores: 1, tileEntries: 1, tileBytes: 12, tileHits: 2, tileMisses: 3, tileEvictions: 0, httpDelegations: 4,
        streetHits: 1, streetMisses: 2, streetDelegations: 3, satelliteHits: 4, satelliteMisses: 5, satelliteDelegations: Infinity } });
    expect(snapshot.tuning.clusterMotionIdleDelay).toBe(250);
    expect(snapshot.cache).toMatchObject({ streetHits: 1, streetMisses: 2, streetDelegations: 3, satelliteHits: 4, satelliteMisses: 5, satelliteDelegations: null });
  });

  it('never exports arbitrary state, precise coordinates, identities or private request data', () => {
    const snapshot = safeDiagnosticSnapshot({
      ...input, query: 'private-query-sentinel', selectedId: 'private-selected-sentinel',
      centerLat: 12.345678, centerLon: 98.765432, address: 'private-address-sentinel',
      requestUrl: 'https://private.example/?token=secret-sentinel',
      search: { ...input.search!, query: 'nested-query-sentinel' },
      layout: { ...input.layout, sourceUrl: 'nested-source-sentinel' },
    } as DiagnosticInput);
    const json = JSON.stringify(snapshot);
    expect(json).not.toMatch(/sentinel|12\.345678|98\.765432|centerLat|centerLon|selectedId|requestUrl|address/);
    expect(Object.keys(snapshot.viewport)).toEqual(['width', 'height', 'canvasWidth', 'canvasHeight', 'zoom', 'bearing', 'pitch']);
  });

  it('represents unmeasured metrics as null and rejects unexpected identifier/state strings', () => {
    const snapshot = safeDiagnosticSnapshot({ ...input, manifest: 'bad-manifest', release: 'https://private.example/',
      feedMs: NaN, cameraIdleMs: null, search: { ...input.search!, listStatus: 'raw-server-payload', scope: 'source-url' } });
    expect(snapshot.manifest).toBeNull(); expect(snapshot.release).toBeNull();
    expect(snapshot.timingMs.feed).toBeNull(); expect(snapshot.timingMs.cameraIdle).toBeNull();
    expect(snapshot.search.listStatus).toBeNull(); expect(snapshot.search.scope).toBeNull();
  });

  it('keeps an unknown search total unavailable rather than converting it to zero', () => {
    expect(safeDiagnosticSnapshot({ ...input, search: { ...input.search!, total: null } }).search.total).toBeNull();
    expect(safeDiagnosticSnapshot({ ...input, search: undefined }).search.total).toBeNull();
  });

  it('copies cache settings and aggregate counters without leaking nested state', () => {
    const snapshot = safeDiagnosticSnapshot({ ...input,
      cache: { indexEnabled: true, indexMaxMiB: 64, tileEnabled: true, tileMaxMiB: 32,
        tileMaxEntries: 512, tileTtlHours: 168, ramTiles: 128, baselineOpacity: 1, tileFadeMs: 180, query: 'private-sentinel' },
      cacheMetrics: { indexState: 'restored', builds: 0, restores: 1, indexStoredBytes: 123456, indexReason: 'cache-limit', tileEntries: 20, tileBytes: 9000,
        tileHits: 40, tileMisses: 20, tileEvictions: 0, httpDelegations: 0, providerUrl: 'private-sentinel' },
    } as DiagnosticInput);
    expect(snapshot.cache).toMatchObject({ indexState: 'restored', builds: 0, restores: 1, indexStoredBytes: 123456, indexReason: 'cache-limit', ramTiles: 128, tileEntries: 20, tileFadeMs: 180 });
    expect(JSON.stringify(snapshot)).not.toContain('sentinel');
  });

  it('rejects arbitrary cache failure messages and non-finite stored byte counts', () => {
    const snapshot = safeDiagnosticSnapshot({ ...input, cacheMetrics: { indexState: 'unavailable', builds: 0, restores: 0,
      indexReason: 'private-error-sentinel', indexStoredBytes: Infinity, tileEntries: 0, tileBytes: 0,
      tileHits: 0, tileMisses: 0, tileEvictions: 0, httpDelegations: 0 } });
    expect(snapshot.cache.indexReason).toBeNull(); expect(snapshot.cache.indexStoredBytes).toBeNull();
    expect(JSON.stringify(snapshot)).not.toContain('sentinel');
  });

  it('copies only measured world-cache aggregates and known states', () => {
    const snapshot = safeDiagnosticSnapshot({ ...input,
      worldCache: { enabled: true, maxZoom: 5, maxMiB: 24 },
      worldCacheMetrics: { status: 'ready', bytes: 12000, hits: 3, requests: 12, readyChunks: 12, totalChunks: 12,
        tileUrls: ['https://private-sentinel.test/'] } } as DiagnosticInput);
    expect(snapshot.worldCache).toEqual({ enabled: true, maxZoom: 5, maxMiB: 24,
      status: 'ready', bytes: 12000, hits: 3, requests: 12, readyChunks: 12, totalChunks: 12 });
    expect(JSON.stringify(snapshot)).not.toContain('sentinel');
    expect(safeDiagnosticSnapshot({ ...input, worldCacheMetrics: { status: 'raw-error-sentinel', bytes: NaN,
      hits: 0, requests: 0, readyChunks: 0, totalChunks: 0 } }).worldCache)
      .toMatchObject({ status: null, bytes: null });
  });
});
