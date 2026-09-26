<script lang="ts">
  import { onMount } from 'svelte';
  import type { LabAction, LabRecord, LabState, MapDiagnostics, ViewportBounds } from './contract';
  import { labRecords, LAB_SENTINEL } from './fixtures';
  import { decodeLabHash, encodeLabHash, reduceLabState } from './state';
  import { createLabViewModel } from './viewModel';
  import { createRealPreviewRepository, mapRealPreviewCandidate, RealPreviewError, type RealPreviewCounts, type RealPreviewFacet } from '../api/RealPreviewRepository';
  import { selectDesignLabDataMode } from './dataMode';
  import Field from './variants/field/Field.svelte';

  let state: LabState = decodeLabHash(typeof location === 'undefined' ? '' : location.hash);
  const serverMode = typeof document === 'undefined' ? null : document.querySelector<HTMLMetaElement>('meta[name="uec-local-data-mode"]')?.content ?? null;
  const mode = selectDesignLabDataMode(import.meta.env.DEV, serverMode);
  // Fixture projections never run during real-data gestures. A viewport event
  // changes state frequently, but it must not rescan synthetic rows or leak
  // them into the live record pool.
  let model = createLabViewModel(mode === 'synthetic' ? labRecords : [], state);
  $: if (mode === 'synthetic') model = createLabViewModel(labRecords, state);
  // MVT is an explicit local-preview rollout flag. Keeping the bounded JSON path
  // available makes an unavailable/incomplete tile service visible rather than
  // quietly changing the map to synthetic fixtures.
  const useMvtMap = mode === 'real-preview' && import.meta.env.VITE_REAL_PREVIEW_MAP_SOURCE === 'mvt';
  const repository = createRealPreviewRepository();
  let sourceId: string | null = state.sourceId;
  $: sourceId = state.sourceId;
  let apiRecords: LabRecord[] = [];
  let viewportRecords: LabRecord[] = [];
  let dataStatus: 'loading' | 'ready' | 'empty' | 'error' | 'unauthorized' = 'loading';
  let dataError = '';
  let nextCursor: string | null = null;
  let pageLoading = false;
  let counts: RealPreviewCounts | null = null;
  let facets: readonly RealPreviewFacet[] = [];
  let facetsStatus: 'loading' | 'ready' | 'error' | 'unauthorized' = 'loading';
  let viewportStatus: 'idle' | 'loading' | 'ready' | 'empty' | 'error' | 'unauthorized' = 'idle';
  let viewportError = '';
  let viewportTruncated = false;
  let detailRecord: LabRecord | null = null;
  let detailStatus: 'loading' | 'ready' | 'error' | 'unauthorized' = 'ready';
  let detailError = '';
  let listAbort: AbortController | undefined;
  const viewportCache = new Map<string, { records: readonly LabRecord[]; truncated: boolean; touched: number }>();
  const viewportRequests = new Map<string, AbortController>();
  let viewportGeneration = 0;
  let cacheHits = 0; let cacheMisses = 0; let inFlightTiles = 0; let lastFetchMs: number | null = null;
  let sourceMaterializeMs: number | null = null; let clusterReadyMs: number | null = null; let zoomSettleMs: number | null = null;
  let currentTileCount = 0; let currentReadyTileCount = 0;
  let detailAbort: AbortController | undefined;
  let referenceAbort: AbortController | undefined;
  let aggregateReferenceKey: string | null = null;
  let aggregateMemberRecords: LabRecord[] = [];
  let aggregateNextCursor: string | null = null;
  let aggregateLoading = false;
  let aggregateError = '';
  let currentBounds: ViewportBounds | null = null;
  // This is intentionally memory-only. Private preview rows and credentials never reach
  // browser persistence; the repository continues to issue no-store network requests.
  const TILE_CACHE_LIMIT = 72;
  const MAX_PAGES_PER_TILE = 8;
  const MAX_CONCURRENT_TILE_REQUESTS = 4;

  function dispatch(action: LabAction) {
    // The map can emit a final viewport event while a link is navigating away.
    // Never let that event replace the destination record/database route.
    if (!location.hash.startsWith('#/map')) return;
    state = reduceLabState(state, action);
    history.replaceState(null, '', encodeLabHash(state));
  }

  function errorState(error: unknown): 'error' | 'unauthorized' {
    return error instanceof RealPreviewError && error.kind === 'unauthorized' ? 'unauthorized' : 'error';
  }

  async function loadPage(query: string, reset: boolean) {
    listAbort?.abort();
    const controller = new AbortController();
    listAbort = controller;
    if (reset) {
      dataStatus = 'loading';
      dataError = '';
      apiRecords = [];
      nextCursor = null;
    } else pageLoading = true;
    try {
      const page = await repository.list({ query, sourceId, cursor: reset ? null : nextCursor, limit: 200, signal: controller.signal });
      if (controller.signal.aborted) return;
      const mapped = page.records.map(mapRealPreviewCandidate);
      const combined = reset ? mapped : [...apiRecords, ...mapped];
      apiRecords = [...new Map(combined.map(record => [record.id, record])).values()];
      nextCursor = page.nextCursor;
      dataStatus = apiRecords.length ? 'ready' : 'empty';
    } catch (error) {
      if (controller.signal.aborted) return;
      dataStatus = errorState(error);
      dataError = error instanceof Error ? error.message : 'The private real-data preview could not be loaded.';
    } finally {
      if (listAbort === controller) pageLoading = false;
    }
  }

  const clampLatitude = (latitude: number) => Math.max(-85.05112878, Math.min(85.05112878, latitude));
  const tileY = (latitude: number, zoom: number) => Math.floor((1 - Math.asinh(Math.tan(clampLatitude(latitude) * Math.PI / 180)) / Math.PI) / 2 * 2 ** zoom);
  const tileX = (longitude: number, zoom: number) => Math.floor(((longitude + 180) / 360) * 2 ** zoom);
  const tileBounds = (zoom: number, x: number, y: number): ViewportBounds => {
    const scale = 2 ** zoom;
    const longitude = (column: number) => column / scale * 360 - 180;
    const latitude = (row: number) => Math.atan(Math.sinh(Math.PI * (1 - 2 * row / scale))) * 180 / Math.PI;
    return { west: longitude(x), east: longitude(x + 1), north: latitude(y), south: latitude(y + 1) };
  };
  const tileKey = (zoom: number, x: number, y: number) => `${sourceId ?? 'all'}:${zoom}:${x}:${y}`;
  function neededTiles(bounds: ViewportBounds) {
    // A coarser logical grid increases cache reuse across ordinary pans while the one-tile
    // overscan makes the map feel ready before the next moveend event arrives.
    const zoom = Math.max(2, Math.min(8, Math.floor(mapZoomHint) - 1));
    const scale = 2 ** zoom;
    const ranges: readonly (readonly [number, number])[] = bounds.west <= bounds.east ? [[bounds.west, bounds.east]] : [[bounds.west, 180], [-180, bounds.east]];
    const result = new Map<string, { key: string; bounds: ViewportBounds }>();
    for (const [west, east] of ranges) {
      const left = Math.max(0, tileX(west, zoom) - 1);
      const right = Math.min(scale - 1, tileX(east, zoom) + 1);
      const top = Math.max(0, tileY(bounds.north, zoom) - 1);
      const bottom = Math.min(scale - 1, tileY(bounds.south, zoom) + 1);
      for (let x = left; x <= right; x += 1) for (let y = top; y <= bottom; y += 1) {
        const key = tileKey(zoom, x, y); result.set(key, { key, bounds: tileBounds(zoom, x, y) });
      }
    }
    return result;
  }

  async function loadReference(key: string, reset: boolean) {
    if (reset) {
      referenceAbort?.abort();
      aggregateReferenceKey = key;
      aggregateMemberRecords = [];
      aggregateNextCursor = null;
      aggregateError = '';
    }
    if (!aggregateReferenceKey) return;
    const controller = new AbortController();
    referenceAbort = controller;
    aggregateLoading = true;
    try {
      const page = await repository.reference(aggregateReferenceKey, { sourceId, cursor: reset ? null : aggregateNextCursor, limit: 100, signal: controller.signal });
      if (controller.signal.aborted || aggregateReferenceKey !== key) return;
      const mapped = page.records.map(mapRealPreviewCandidate);
      aggregateMemberRecords = reset ? mapped : [...new Map([...aggregateMemberRecords, ...mapped].map(record => [record.id, record])).values()];
      aggregateNextCursor = page.nextCursor;
      dispatch({ type: 'aggregate', value: aggregateMemberRecords.map(record => record.id) });
    } catch (error) {
      if (!controller.signal.aborted) aggregateError = error instanceof Error ? error.message : 'This map reference could not be loaded.';
    } finally {
      if (referenceAbort === controller) aggregateLoading = false;
    }
  }
  let mapZoomHint = state.viewport.zoom;
  let activeTileKeys = new Set<string>();
  let mapDiagnostics: MapDiagnostics = { zoom: mapZoomHint, currentTiles: 0, readyTiles: 0, cacheEntries: 0, cacheCapacity: TILE_CACHE_LIMIT, cacheHits: 0, cacheMisses: 0, inFlight: 0, lastFetchMs: null, renderedRecords: 0, sourceId: null, truncated: false, sourceMaterializeMs: null, clusterReadyMs: null, zoomSettleMs: null };
  $: mapDiagnostics = { zoom: mapZoomHint, currentTiles: currentTileCount, readyTiles: currentReadyTileCount, cacheEntries: viewportCache.size, cacheCapacity: TILE_CACHE_LIMIT, cacheHits, cacheMisses, inFlight: inFlightTiles, lastFetchMs, renderedRecords: viewportRecords.length, sourceId, truncated: viewportTruncated, sourceMaterializeMs, clusterReadyMs, zoomSettleMs };
  let renderedTileKeys = new Set<string>();
  function materializeCachedRecords(keys = renderedTileKeys) {
    // The LRU may remember a much larger route around the world. It is an instant
    // re-entry cache, not the live MapLibre source: render only current buffered
    // coverage (and, briefly, the immediately previous coverage during a pan).
    const values = [...keys].flatMap(key => viewportCache.get(key)?.records ?? []);
    viewportRecords = [...new Map(values.map(record => [record.id, record])).values()];
  }
  function materializeNow() {
    materializeCachedRecords();
  }
  function evictTiles() {
    if (viewportCache.size <= TILE_CACHE_LIMIT) return;
    const oldest = [...viewportCache.entries()].sort((a, b) => a[1].touched - b[1].touched).slice(0, viewportCache.size - TILE_CACHE_LIMIT);
    for (const [key] of oldest) viewportCache.delete(key);
  }
  async function fetchTile(key: string, bounds: ViewportBounds, generation: number) {
    if (viewportCache.has(key) || viewportRequests.has(key)) return;
    const startedAt = performance.now();
    const controller = new AbortController(); viewportRequests.set(key, controller); inFlightTiles = viewportRequests.size;
    try {
      const records: LabRecord[] = []; let cursor: string | null = null; let pages = 0; let truncated = false;
      do {
        const page = await repository.viewport(bounds, { sourceId, cursor, limit: 500, signal: controller.signal });
        records.push(...page.records.map(mapRealPreviewCandidate)); cursor = page.nextCursor; pages += 1;
        if (pages >= MAX_PAGES_PER_TILE && cursor) { truncated = true; cursor = null; }
      } while (cursor && !controller.signal.aborted);
      // Do not discard a tile merely because the camera moved again: if it was not
      // obsolete enough to abort, it is valuable warm coverage for a return pan.
      if (controller.signal.aborted) return;
      viewportCache.set(key, { records: [...new Map(records.map(record => [record.id, record])).values()], truncated, touched: Date.now() });
      evictTiles(); currentReadyTileCount = [...activeTileKeys].filter(activeKey => viewportCache.has(activeKey)).length;
    } finally { if (viewportRequests.get(key) === controller) { viewportRequests.delete(key); inFlightTiles = viewportRequests.size; } if (!controller.signal.aborted) lastFetchMs = Math.round(performance.now() - startedAt); }
  }
  async function loadViewport(bounds: ViewportBounds) {
    if (mode !== 'real-preview' || useMvtMap) return;
    currentBounds = bounds; mapZoomHint = state.viewport.zoom;
    const generation = ++viewportGeneration;
    const wanted = neededTiles(bounds);
    activeTileKeys = new Set(wanted.keys());
    currentTileCount = wanted.size;
    // A request is only obsolete when it no longer intersects the buffered viewport.
    for (const [key, request] of viewportRequests) if (!wanted.has(key)) request.abort();
    for (const key of wanted.keys()) { const cached = viewportCache.get(key); if (cached) cached.touched = Date.now(); }
    const cachedTiles = [...wanted.keys()].filter(key => viewportCache.has(key));
    cacheHits += cachedTiles.length;
    // Keep the previous bounded source stable while the next tile set is fetched.
    // That avoids a full Supercluster rebuild for every tile arrival or pan start.
    // Once this generation is complete, replace it once with the exact wanted set.
    const missing = [...wanted.values()].filter(tile => !viewportCache.has(tile.key));
    cacheMisses += missing.length;
    currentReadyTileCount = cachedTiles.length;
    viewportTruncated = [...wanted.keys()].some(key => viewportCache.get(key)?.truncated);
    if (!missing.length) { renderedTileKeys = new Set(wanted.keys()); materializeNow(); currentReadyTileCount = wanted.size; viewportStatus = viewportRecords.length ? 'ready' : 'empty'; return; }
    viewportStatus = 'loading'; viewportError = '';
    let index = 0;
    const worker = async () => { while (index < missing.length) { const tile = missing[index++]!; try { await fetchTile(tile.key, tile.bounds, generation); } catch (error) { if (!viewportRequests.has(tile.key) && generation !== viewportGeneration) continue; if (!viewportError) viewportError = error instanceof Error ? error.message : 'The map records could not be loaded.'; } } };
    await Promise.all(Array.from({ length: Math.min(MAX_CONCURRENT_TILE_REQUESTS, missing.length) }, worker));
    if (generation !== viewportGeneration) return;
    renderedTileKeys = new Set(wanted.keys()); materializeNow(); currentReadyTileCount = [...wanted.keys()].filter(key => viewportCache.has(key)).length;
    viewportTruncated = [...wanted.keys()].some(key => viewportCache.get(key)?.truncated);
    viewportStatus = viewportError ? errorState(new RealPreviewError('network', viewportError)) : viewportRecords.length ? 'ready' : 'empty';
  }

  let observedListKey: string | undefined;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  $: if (mode === 'real-preview' && observedListKey !== `${state.query}\u0000${sourceId ?? ''}`) {
    observedListKey = `${state.query}\u0000${sourceId ?? ''}`;
    if (searchTimer) clearTimeout(searchTimer);
    listAbort?.abort();
    const query = state.query;
    searchTimer = setTimeout(() => void loadPage(query, true), 180);
  }

  let observedMapSource: string | null | undefined;
  $: if (mode === 'real-preview' && observedMapSource !== sourceId) {
    observedMapSource = sourceId;
    viewportGeneration += 1;
    for (const request of viewportRequests.values()) request.abort();
    viewportRequests.clear(); viewportCache.clear(); renderedTileKeys = new Set(); viewportRecords = [];
    cacheHits = 0; cacheMisses = 0; inFlightTiles = 0; lastFetchMs = null; currentTileCount = 0; currentReadyTileCount = 0;
    if (currentBounds && !useMvtMap) void loadViewport(currentBounds);
  }

  let observedSelection: string | null | undefined;
  $: if (mode === 'real-preview' && observedSelection !== state.selectedId) {
    observedSelection = state.selectedId;
    detailAbort?.abort();
    if (!state.selectedId) { detailRecord = null; detailStatus = 'ready'; detailError = ''; }
    else {
      const id = state.selectedId;
      const controller = new AbortController();
      detailAbort = controller;
      detailStatus = 'loading'; detailRecord = null; detailError = '';
      void repository.detail(id, controller.signal).then(candidate => {
        if (!controller.signal.aborted) { detailRecord = mapRealPreviewCandidate(candidate); detailStatus = 'ready'; }
      }).catch(error => {
        if (!controller.signal.aborted) {
          detailStatus = errorState(error);
          detailError = error instanceof Error ? error.message : 'The selected record could not be loaded.';
        }
      });
    }
  }

  onMount(() => {
    const sync = () => {
      if (location.hash.startsWith('#/map')) state = decodeLabHash(location.hash);
    };
    addEventListener('hashchange', sync);
    let summaryAbort: AbortController | undefined;
    if (mode === 'real-preview') {
      summaryAbort = new AbortController();
      void repository.counts(summaryAbort.signal).then(value => { if (!summaryAbort?.signal.aborted) counts = value; }).catch(() => { /* The primary list surface reports request failures. */ });
      void repository.facets(summaryAbort.signal).then(value => { if (!summaryAbort?.signal.aborted) { facets = value; facetsStatus = 'ready'; } }).catch(error => { if (!summaryAbort?.signal.aborted) facetsStatus = errorState(error); });
    }
    return () => {
      removeEventListener('hashchange', sync);
      if (searchTimer) clearTimeout(searchTimer);
      summaryAbort?.abort(); listAbort?.abort(); referenceAbort?.abort(); for (const request of viewportRequests.values()) request.abort(); detailAbort?.abort();
    };
  });
</script>
<svelte:head><title>Until Every Cage — Map</title></svelte:head>
<div class="lab" data-review-sentinel={mode === 'synthetic' ? LAB_SENTINEL : undefined} data-direction="field" data-scenario={state.scenario} data-data-mode={mode}>
  <main aria-label="Map preview"><h1 class="sr-only">Investigative map</h1>
    <Field {state} records={mode === 'real-preview' ? apiRecords : model.listRecords} mapRecords={mode === 'real-preview' ? (useMvtMap ? [] : viewportRecords) : model.mapRecords} {mode} {useMvtMap}
      dataStatus={dataStatus} {dataError} mapStatus={viewportStatus} mapError={viewportError} mapTruncated={viewportTruncated}
      {detailRecord} {detailStatus} {detailError} {nextCursor} {pageLoading}
      {facets} {facetsStatus} {mapDiagnostics} {aggregateMemberRecords} {aggregateNextCursor} {aggregateLoading} {aggregateError} onMapTiming={timing=>{sourceMaterializeMs=timing.sourceMaterializeMs;clusterReadyMs=timing.clusterReadyMs;if(timing.zoomSettleMs!==undefined)zoomSettleMs=timing.zoomSettleMs;}} onLoadMore={() => void loadPage(state.query, false)} onMapReference={key => void loadReference(key, true)} onLoadMoreAggregate={() => { if (aggregateReferenceKey) void loadReference(aggregateReferenceKey, false); }} onViewportBounds={loadViewport} {dispatch}/>
    {#if mode === 'real-preview' && counts}
      <p class="private-counts" role="status">{counts.facilityCandidateCount.toLocaleString()} private candidates · {counts.mapVisibleCount.toLocaleString()} map locations · {counts.cityPostalCount.toLocaleString()} city or postal</p>
    {/if}
  </main>
</div>
<style>.lab,main{height:100dvh;overflow:hidden}.sr-only{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}.private-counts{position:fixed;z-index:6;bottom:.45rem;right:.55rem;max-width:40vw;margin:0;padding:.18rem .32rem;border:1px solid #48504b;background:#171a18e8;color:#c6cbc4;font:500 .58rem system-ui}@media(max-width:40rem){.private-counts{max-width:48vw;font-size:.5rem}}</style>
