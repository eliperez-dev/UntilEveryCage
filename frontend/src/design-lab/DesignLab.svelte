<script lang="ts">
  import { onMount } from 'svelte';
  import type { LabAction, LabRecord, LabState, MapDiagnostics } from './contract';
  import { labRecords, LAB_SENTINEL } from './fixtures';
  import { decodeLabHash, encodeLabHash, reduceLabState } from './state';
  import { createLabViewModel } from './viewModel';
  import { createRealPreviewRepository, mapRealPreviewCandidate, RealPreviewError, type RealPreviewCounts, type RealPreviewFacet } from '../api/RealPreviewRepository';
  import { selectDesignLabDataMode } from './dataMode';
  import Field from './variants/field/Field.svelte';

  let state: LabState = decodeLabHash(typeof location === 'undefined' ? '' : location.hash);
  const serverMode = typeof document === 'undefined' ? null : document.querySelector<HTMLMetaElement>('meta[name="uec-local-data-mode"]')?.content ?? null;
  const mode = selectDesignLabDataMode(import.meta.env.DEV, serverMode);
  // Fixture projections run only in the synthetic mode.
  let model = createLabViewModel(mode === 'synthetic' ? labRecords : [], state);
  $: if (mode === 'synthetic') model = createLabViewModel(labRecords, state);
  const repository = createRealPreviewRepository();
  let sourceId: string | null = state.sourceId;
  $: sourceId = state.sourceId;
  let apiRecords: LabRecord[] = [];
  let dataStatus: 'loading' | 'ready' | 'empty' | 'error' | 'unauthorized' = 'loading';
  let dataError = '';
  let nextCursor: string | null = null;
  let pageLoading = false;
  let counts: RealPreviewCounts | null = null;
  let facets: readonly RealPreviewFacet[] = [];
  let facetsStatus: 'loading' | 'ready' | 'error' | 'unauthorized' = 'loading';
  let detailRecord: LabRecord | null = null;
  let detailStatus: 'loading' | 'ready' | 'error' | 'unauthorized' = 'ready';
  let detailError = '';
  let listAbort: AbortController | undefined;
  let sourceMaterializeMs: number | null = null; let clusterReadyMs: number | null = null; let zoomSettleMs: number | null = null;
  let detailAbort: AbortController | undefined;
  let referenceAbort: AbortController | undefined;
  let aggregateReferenceKey: string | null = null;
  let aggregateReferenceSourceId: string | null = null;
  let aggregateMemberRecords: LabRecord[] = [];
  let aggregateNextCursor: string | null = null;
  let aggregateLoading = false;
  let aggregateError = '';
  let mapDiagnostics: MapDiagnostics = { zoom: state.viewport.zoom, currentTiles: 0, readyTiles: 0, cacheEntries: 0, cacheCapacity: 0, cacheHits: 0, cacheMisses: 0, inFlight: 0, lastFetchMs: null, renderedRecords: 0, sourceId, truncated: false, sourceMaterializeMs: null, clusterReadyMs: null, zoomSettleMs: null };
  // This is intentionally memory-only. Private preview rows and credentials never reach
  // browser persistence; the repository continues to issue no-store network requests.

  function dispatch(action: LabAction) {
    // The map can emit a final viewport event while a link is navigating away.
    // Never let that event replace the destination record/database route.
    if (!location.hash.startsWith('#/map')) return;
    const wasSelected = state.selectedId !== null;
    state = reduceLabState(state, action);
    const nextHash = encodeLabHash(state);
    if (action.type === 'select' && action.value && !wasSelected) {
      // Selection is a navigable map state: Back dismisses the dossier. Other
      // frequent map updates (especially viewport movement) stay replace-only.
      history.pushState({ ...history.state, uecMapSelection: true }, '', nextHash);
    } else if (action.type === 'select' && !action.value && history.state?.uecMapSelection) {
      // Return to the immediately preceding unselected map entry. A direct
      // selected URL has no marker and is cleared in place below.
      history.back();
    } else {
      history.replaceState(history.state, '', nextHash);
    }
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

  async function loadReference(key: string, reset: boolean, featureSourceId?: string) {
    if (reset) {
      referenceAbort?.abort();
      aggregateReferenceKey = key;
      aggregateReferenceSourceId = featureSourceId ?? sourceId;
      aggregateMemberRecords = [];
      aggregateNextCursor = null;
      aggregateError = '';
    }
    if (!aggregateReferenceKey) return;
    const controller = new AbortController();
    referenceAbort = controller;
    aggregateLoading = true;
    try {
      const page = await repository.reference(aggregateReferenceKey, { sourceId: aggregateReferenceSourceId, cursor: reset ? null : aggregateNextCursor, limit: 100, signal: controller.signal });
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
  $: mapDiagnostics = { ...mapDiagnostics, zoom: state.viewport.zoom, sourceId, sourceMaterializeMs, clusterReadyMs, zoomSettleMs };

  let observedListKey: string | undefined;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  $: if (mode === 'real-preview' && observedListKey !== `${state.query}\u0000${sourceId ?? ''}`) {
    observedListKey = `${state.query}\u0000${sourceId ?? ''}`;
    if (searchTimer) clearTimeout(searchTimer);
    listAbort?.abort();
    const query = state.query;
    searchTimer = setTimeout(() => void loadPage(query, true), 180);
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
    addEventListener('popstate', sync);
    let summaryAbort: AbortController | undefined;
    if (mode === 'real-preview') {
      summaryAbort = new AbortController();
      void repository.counts(summaryAbort.signal).then(value => { if (!summaryAbort?.signal.aborted) counts = value; }).catch(() => { /* The primary list surface reports request failures. */ });
      void repository.facets(summaryAbort.signal).then(value => { if (!summaryAbort?.signal.aborted) { facets = value; facetsStatus = 'ready'; } }).catch(error => { if (!summaryAbort?.signal.aborted) facetsStatus = errorState(error); });
    }
    return () => {
      removeEventListener('hashchange', sync);
      removeEventListener('popstate', sync);
      if (searchTimer) clearTimeout(searchTimer);
      summaryAbort?.abort(); listAbort?.abort(); referenceAbort?.abort(); detailAbort?.abort();
    };
  });
</script>
<svelte:head><title>Until Every Cage — Map</title></svelte:head>
<div class="lab" data-review-sentinel={mode === 'synthetic' ? LAB_SENTINEL : undefined} data-direction="field" data-scenario={state.scenario} data-data-mode={mode}>
  <main aria-label="Map preview"><h1 class="sr-only">Investigative map</h1>
    <Field {state} records={mode === 'real-preview' ? apiRecords : model.listRecords} mapRecords={mode === 'real-preview' ? [] : model.mapRecords} {mode}
      dataStatus={dataStatus} {dataError}
      {detailRecord} {detailStatus} {detailError} {nextCursor} {pageLoading}
      {facets} {facetsStatus} {mapDiagnostics} {aggregateMemberRecords} {aggregateNextCursor} {aggregateLoading} {aggregateError} onMapTiming={timing=>{sourceMaterializeMs=timing.sourceMaterializeMs;clusterReadyMs=timing.clusterReadyMs;if(timing.zoomSettleMs!==undefined)zoomSettleMs=timing.zoomSettleMs;}} onLoadMore={() => void loadPage(state.query, false)} onMapReference={(key, refSourceId) => void loadReference(key, true, refSourceId)} onLoadMoreAggregate={() => { if (aggregateReferenceKey) void loadReference(aggregateReferenceKey, false); }} {dispatch}/>
    {#if mode === 'real-preview' && counts}
      <p class="private-counts" role="status">{counts.facilityCandidateCount.toLocaleString()} private candidates · {counts.mapVisibleCount.toLocaleString()} map locations · {counts.cityPostalCount.toLocaleString()} city or postal</p>
    {/if}
  </main>
</div>
<style>.lab,main{height:100dvh;overflow:hidden}.sr-only{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}.private-counts{position:fixed;z-index:6;bottom:.45rem;right:.55rem;max-width:40vw;margin:0;padding:.18rem .32rem;border:1px solid #48504b;background:#171a18e8;color:#c6cbc4;font:500 .58rem system-ui}@media(max-width:40rem){.private-counts{max-width:48vw;font-size:.5rem}}</style>
