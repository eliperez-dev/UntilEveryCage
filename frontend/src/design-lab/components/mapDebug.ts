export type LayoutTuning = Readonly<{ panelWidthPercent: number; rowPadding: number; typeScale: number }>;
export type CacheTuning = Readonly<{
  indexEnabled: boolean;
  indexMaxMiB: number;
  tileEnabled: boolean;
  tileMaxMiB: number;
  tileMaxEntries: number;
  tileTtlHours: number;
  ramTiles: number;
  baselineOpacity: number;
  tileFadeMs: number;
}>;
export type WorldCacheTuning = Readonly<{ enabled: boolean; maxZoom: number; maxMiB: number }>;
export type SearchDiagnostics = Readonly<{ total: number | null; shown: number; listStatus: string; matchesStatus: string; matchingMappedCount: number | null; scope: string | null }>;
export type DebugMetric = Readonly<{ label: string; value: string }>;

type FeedCacheMetadata = Readonly<{ cacheStatus?: 'hit' | 'miss' | 'unavailable'; decodedBytes?: number }>;
/** Public feeds carry these measurements inside meta; private feeds keep them at the top level. */
export function mapFeedCacheDiagnostics(feed: { meta: FeedCacheMetadata } | (FeedCacheMetadata & { cacheStatus: 'hit' | 'miss' | 'unavailable' })) {
  const metadata = 'meta' in feed ? feed.meta : feed;
  return { cacheStatus: metadata.cacheStatus ?? 'unavailable', decodedBytes: metadata.decodedBytes ?? null };
}

export function publicMapLoadingLabel(cacheStatus: string, indexState: string | null): string {
  if (indexState === 'building') return 'First time loading. This may take a while…';
  if (cacheStatus === 'hit' || indexState === 'lookup' || indexState === 'restored') return 'Restoring cached map…';
  return 'Loading map…';
}

const indexFailureReasons = ['cache-limit', 'compression-unavailable', 'storage-unavailable', 'invalid-snapshot', 'cleared-during-build'];
export function indexCacheReasonLabel(reason: string | undefined): string | null {
  const labels: Record<string, string> = {
    'cache-limit': 'Index exceeds cache budget', 'compression-unavailable': 'Compression unavailable',
    'storage-unavailable': 'Storage unavailable', 'invalid-snapshot': 'Stored index failed validation',
    'cleared-during-build': 'Cache cleared during build',
  };
  return reason && indexFailureReasons.includes(reason) ? labels[reason]! : null;
}

export type DiagnosticInput = Readonly<{
  mode: string; release: string | null; manifest: string | null; restrictionGeneration: number | null;
  search?: SearchDiagnostics | undefined;
  loadedMapped: number; filteredMapped: number; renderedMarks: number | null;
  feedRequests: number; decodedBytes: number | null; cacheEntries: number | null;
  indexUpdates?: number;
  feedMs: number | null; indexMs: number | null; rebuildMs: number | null;
  cameraMoveendMs: number | null; cameraIdleMs: number | null;
  width: number; height: number; canvasWidth: number; canvasHeight: number;
  zoom: number; bearing: number; pitch: number;
  clusterMode: 'auto' | 'on' | 'off'; clusterRadius: number; clusterMaxZoom: number;
  clusterMotionDuration?: number; clusterMotionLimit?: number;
  pinScale: number; layout: LayoutTuning;
  cache?: CacheTuning;
  worldCache?: WorldCacheTuning;
  worldCacheMetrics?: Readonly<{ status: string; bytes: number; hits: number; requests: number; readyChunks: number; totalChunks: number }>;
  cacheMetrics?: Readonly<{ indexState: string | null; builds: number; restores: number; indexReason?: string | null; indexStoredBytes?: number | null;
    tileEntries: number; tileBytes: number; tileHits: number; tileMisses: number; tileEvictions: number; httpDelegations: number }>;
}>;

const finite = (value: number | null) => value !== null && Number.isFinite(value) ? value : null;
const state = (value: string | undefined) => ['idle', 'loading', 'ready', 'empty', 'error', 'unauthorized'].includes(value ?? '') ? value : null;

/** Deliberately reconstruct the export: never serialize application state, requests or camera coordinates. */
export function safeDiagnosticSnapshot(input: DiagnosticInput) {
  return {
    schema: 'uec-map-diagnostics-v1',
    mode: ['synthetic', 'real-preview', 'candidate-preview', 'public-release'].includes(input.mode) ? input.mode : null,
    release: input.release && /^[a-zA-Z0-9_.-]{1,160}$/.test(input.release) ? input.release : null,
    manifest: input.manifest && /^[a-f0-9]{64}$/.test(input.manifest) ? input.manifest : null,
    restrictionGeneration: finite(input.restrictionGeneration),
    search: {
      total: finite(input.search?.total ?? null), shown: finite(input.search?.shown ?? null),
      listStatus: state(input.search?.listStatus), matchesStatus: state(input.search?.matchesStatus),
      matchingMappedCount: finite(input.search?.matchingMappedCount ?? null),
      scope: input.search?.scope === 'area' || input.search?.scope === 'radius' ? input.search.scope : null,
    },
    population: { loaded: finite(input.loadedMapped), filtered: finite(input.filteredMapped), renderedMarks: finite(input.renderedMarks), clusteringThreshold: 2800 },
    projection: { requests: finite(input.feedRequests), decodedBytes: finite(input.decodedBytes), cacheEntries: finite(input.cacheEntries), indexUpdates: finite(input.indexUpdates ?? null) },
    timingMs: { feed: finite(input.feedMs), index: finite(input.indexMs), rebuild: finite(input.rebuildMs), cameraMoveend: finite(input.cameraMoveendMs), cameraIdle: finite(input.cameraIdleMs) },
    viewport: { width: finite(input.width), height: finite(input.height), canvasWidth: finite(input.canvasWidth), canvasHeight: finite(input.canvasHeight), zoom: finite(input.zoom), bearing: finite(input.bearing), pitch: finite(input.pitch) },
    tuning: { clusterMode: ['auto','on','off'].includes(input.clusterMode) ? input.clusterMode : null, clusterRadius: finite(input.clusterRadius), clusterMaxZoom: finite(input.clusterMaxZoom), clusterMotionDuration: finite(input.clusterMotionDuration ?? null), clusterMotionLimit: finite(input.clusterMotionLimit ?? null), pinScale: finite(input.pinScale), panelWidthPercent: finite(input.layout.panelWidthPercent), rowPadding: finite(input.layout.rowPadding), typeScale: finite(input.layout.typeScale) },
    cache: {
      indexEnabled: typeof input.cache?.indexEnabled === 'boolean' ? input.cache.indexEnabled : null,
      indexMaxMiB: finite(input.cache?.indexMaxMiB ?? null),
      tileEnabled: typeof input.cache?.tileEnabled === 'boolean' ? input.cache.tileEnabled : null,
      tileMaxMiB: finite(input.cache?.tileMaxMiB ?? null), tileMaxEntries: finite(input.cache?.tileMaxEntries ?? null),
      tileTtlHours: finite(input.cache?.tileTtlHours ?? null), ramTiles: finite(input.cache?.ramTiles ?? null),
      baselineOpacity: finite(input.cache?.baselineOpacity ?? null),
      tileFadeMs: finite(input.cache?.tileFadeMs ?? null),
      indexState: ['lookup', 'building', 'stored', 'restored', 'unavailable'].includes(input.cacheMetrics?.indexState ?? '') ? input.cacheMetrics!.indexState : null,
      builds: finite(input.cacheMetrics?.builds ?? null), restores: finite(input.cacheMetrics?.restores ?? null),
      indexReason: indexFailureReasons.includes(input.cacheMetrics?.indexReason ?? '') ? input.cacheMetrics!.indexReason : null,
      indexStoredBytes: finite(input.cacheMetrics?.indexStoredBytes ?? null),
      tileEntries: finite(input.cacheMetrics?.tileEntries ?? null), tileBytes: finite(input.cacheMetrics?.tileBytes ?? null),
      tileHits: finite(input.cacheMetrics?.tileHits ?? null), tileMisses: finite(input.cacheMetrics?.tileMisses ?? null),
      tileEvictions: finite(input.cacheMetrics?.tileEvictions ?? null), httpDelegations: finite(input.cacheMetrics?.httpDelegations ?? null),
    },
    worldCache: {
      enabled: typeof input.worldCache?.enabled === 'boolean' ? input.worldCache.enabled : null,
      maxZoom: finite(input.worldCache?.maxZoom ?? null), maxMiB: finite(input.worldCache?.maxMiB ?? null),
      status: ['idle', 'warming', 'ready', 'partial', 'paused', 'unavailable'].includes(input.worldCacheMetrics?.status ?? '') ? input.worldCacheMetrics!.status : null,
      bytes: finite(input.worldCacheMetrics?.bytes ?? null), hits: finite(input.worldCacheMetrics?.hits ?? null),
      requests: finite(input.worldCacheMetrics?.requests ?? null), readyChunks: finite(input.worldCacheMetrics?.readyChunks ?? null),
      totalChunks: finite(input.worldCacheMetrics?.totalChunks ?? null),
    },
  };
}
