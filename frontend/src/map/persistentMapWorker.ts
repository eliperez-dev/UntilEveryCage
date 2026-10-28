import NativeWorker from 'maplibre-gl/dist/maplibre-gl-worker.mjs';
import { decodePublicMapTransport } from './publicMapSourceTransport';
import { exportClusterIndex, restoreClusterIndex } from './clusterIndexCodec';
import { matchNativeClusterLineage, type NativeLineageRequest } from './nativeClusterLineage';
import { clusterIndexKey, INDEX_CACHE_CHANNEL, INDEX_CACHE_FIELD, publicIndexIdentity, readClusterIndex, writeClusterIndex, indexCacheFailureReason, type IndexCacheDiagnostic, type IndexCacheFailureReason, type IndexCacheTimings } from './clusterIndexCache';

type Index = unknown;
type Parameters = {
  source?: string; data?: { type: string; features?: unknown[]; [INDEX_CACHE_FIELD]?: unknown };
  geojsonVtOptions?: { cluster?: boolean }; clusterProperties?: unknown; updateCluster?: boolean; filter?: unknown;
};
type Source = {
  _geoJSONIndex: Index;
  getClusterChildren(parameters: { clusterId: number; uecMotionLineage?: NativeLineageRequest }): unknown;
  _createGeoJSONIndex(data: unknown, parameters: Parameters): Index;
  loadAndProcessGeoJSON(parameters: Parameters, controller: AbortController): Promise<unknown>;
};
type WorkerPrototype = { _getWorkerSource(mapId: string, type: string, sourceId: string): Source };
const prototype = (NativeWorker as unknown as { prototype: WorkerPrototype }).prototype;
const originalGetSource = prototype._getWorkerSource;
const installed = new WeakSet<object>();
const empty = { type: 'FeatureCollection', features: [] };
const counts = new Map<string, { builds: number; restores: number }>();
const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(INDEX_CACHE_CHANNEL);
const tuning = new Map<string, { enabled: boolean; maxMiB: number }>();
if (channel) channel.onmessage = event => {
  const value = event.data;
  if (value?.command === 'settings' && typeof value.session === 'string' && /^[a-zA-Z0-9-]{1,80}$/.test(value.session)
    && typeof value.enabled === 'boolean' && Number.isFinite(value.maxMiB)) {
    tuning.set(value.session, { enabled: value.enabled, maxMiB: Math.max(8, Math.min(64, value.maxMiB)) });
  }
};

/**
 * Version-locked worker-only adapter. MapLibre does not expose an index import
 * API. Its native source/factory and reducer compilation remain unchanged;
 * the codec rehydrates a validated empty native shell on a cache hit.
 */
if (typeof originalGetSource === 'function') {
  prototype._getWorkerSource = function(mapId, type, sourceId) {
    const source = originalGetSource.call(this, mapId, type, sourceId);
    if (type !== 'geojson' || sourceId !== 'locations' || installed.has(source)
      || typeof source.loadAndProcessGeoJSON !== 'function' || typeof source._createGeoJSONIndex !== 'function') return source;
    installed.add(source);
    const originalChildren = source.getClusterChildren;
    source.getClusterChildren = function(parameters) {
      if (parameters.uecMotionLineage) return matchNativeClusterLineage(this._geoJSONIndex, parameters.uecMotionLineage);
      return originalChildren.call(this, parameters);
    };
    const originalLoad = source.loadAndProcessGeoJSON;
    const originalFactory = source._createGeoJSONIndex;
    const restorations = new WeakMap<Parameters, Index>();
    source._createGeoJSONIndex = function(data, parameters) {
      if (restorations.has(parameters)) {
        const restored = restorations.get(parameters)!;
        restorations.delete(parameters);
        return restored;
      }
      return originalFactory.call(this, data, parameters);
    };
    let publicData: Parameters['data'];
    source.loadAndProcessGeoJSON = async function(parameters, controller) {
      const started = performance.now();
      const transport = decodePublicMapTransport(parameters.data);
      if (parameters.data) parameters.data = transport.data as NonNullable<Parameters['data']>;
      if (parameters.data) publicData = publicIndexIdentity(parameters.data[INDEX_CACHE_FIELD]) ? parameters.data : undefined;
      const input = parameters.updateCluster && !parameters.data && publicData ? { ...parameters, data: publicData } : parameters;
      parameters = input;
      const identity = publicIndexIdentity(parameters.data?.[INDEX_CACHE_FIELD]);
      const settings = identity ? tuning.get(identity.session) : undefined;
      if (!identity || settings?.enabled === false || (parameters.data?.[INDEX_CACHE_FIELD] as { enabled?: boolean })?.enabled === false
        || !parameters.geojsonVtOptions?.cluster || !parameters.data?.features?.length) return originalLoad.call(this, parameters, controller);
      if (settings) identity.maxMiB = settings.maxMiB;
      const counter = counts.get(identity.session) ?? { builds: 0, restores: 0 };
      counts.set(identity.session, counter);
      const timings: IndexCacheTimings = { transportEncodeMs: transport.encodeMs, transportParseMs: transport.parseMs,
        hashMs: 0, databaseMs: 0, inflateMs: 0, parseMs: 0, validationMs: 0, reconstructionMs: 0, nativeLoadMs: 0, totalMs: 0 };
      const report = (state: IndexCacheDiagnostic['state'], reason?: IndexCacheFailureReason, storedBytes?: number) => {
        timings.totalMs = performance.now() - started;
        try { channel?.postMessage({ session: identity.session, state, ...counter, ...(reason ? { reason } : {}), ...(storedBytes !== undefined ? { storedBytes } : {}), timings,
          startedAtEpochMs: performance.timeOrigin + started, reportedAtEpochMs: performance.timeOrigin + performance.now() } satisfies IndexCacheDiagnostic); } catch { /* Metrics never prevent rendering. */ }
      };
      report('lookup');
      let key: string | undefined;
      let epoch = 0;
      let restored: Index | null = null;
      let writable = false;
      let storedBytes: number | undefined;
      try {
        key = await clusterIndexKey(identity, parameters.data.features, [parameters.geojsonVtOptions, parameters.filter ?? null], parameters.clusterProperties);
        timings.hashMs = performance.now() - started - transport.parseMs;
        const cached = await readClusterIndex(key, identity.maxMiB, parameters.data.features);
        if (cached.timings) Object.assign(timings, cached.timings);
        epoch = cached.epoch; writable = true;
        storedBytes = cached.storedBytes;
        if (controller.signal.aborted) return;
        if (cached.snapshot) restored = restoreClusterIndex(cached.snapshot, () => originalFactory.call(this, empty, parameters), value => Object.assign(timings, value));
      } catch (error) { report('unavailable', indexCacheFailureReason(error)); }
      if (controller.signal.aborted) return;
      if (restored) {
        // Keep the factory stable across overlapping requests. Only this exact
        // parameter object may consume its restored native index.
        restorations.set(parameters, restored);
        try {
          const loading = performance.now();
          const result = await originalLoad.call(this, parameters, controller);
          timings.nativeLoadMs = performance.now() - loading;
          if (!controller.signal.aborted) { counter.restores++; report('restored', undefined, storedBytes); }
          return result;
        } finally { restorations.delete(parameters); }
      }
      counter.builds++; report('building');
      const loading = performance.now();
      const result = await originalLoad.call(this, parameters, controller);
      timings.nativeLoadMs = performance.now() - loading;
      if (controller.signal.aborted) return result;
      if (!key || !writable) { report('unavailable', 'storage-unavailable'); return result; }
      try {
        // The freshly built, pinned native engine is trusted. Fully validate
        // persisted bytes when restoring, rather than walking the tree twice.
        const snapshot = exportClusterIndex(this._geoJSONIndex, false, false);
        if (snapshot) {
          const stored = await writeClusterIndex(key, snapshot, epoch, identity.maxMiB, controller.signal, bytes => { storedBytes = bytes; }, parameters.data?.features);
          if (!controller.signal.aborted) report(stored ? 'stored' : 'unavailable', stored ? undefined : 'cleared-during-build', stored ? storedBytes : undefined);
        } else report('unavailable', 'invalid-snapshot');
      } catch (error) { report('unavailable', indexCacheFailureReason(error)); }
      return result;
    };
    return source;
  };
}
