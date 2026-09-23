<script lang="ts">
  import { onMount } from 'svelte';
  import type { LabAction, LabRecord, LabState, ViewportBounds } from './contract';
  import { labRecords, LAB_SENTINEL } from './fixtures';
  import { decodeLabHash, encodeLabHash, reduceLabState } from './state';
  import { createLabViewModel } from './viewModel';
  import { createRealPreviewRepository, mapRealPreviewCandidate, RealPreviewError, type RealPreviewCounts } from '../api/RealPreviewRepository';
  import { selectDesignLabDataMode } from './dataMode';
  import Field from './variants/field/Field.svelte';

  let state: LabState = decodeLabHash(typeof location === 'undefined' ? '' : location.hash);
  let model = createLabViewModel(labRecords, state);
  $: model = createLabViewModel(labRecords, state);
  const serverMode = typeof document === 'undefined' ? null : document.querySelector<HTMLMetaElement>('meta[name="uec-local-data-mode"]')?.content ?? null;
  const mode = selectDesignLabDataMode(import.meta.env.DEV, serverMode);
  const repository = createRealPreviewRepository();
  let apiRecords: LabRecord[] = [];
  let viewportRecords: LabRecord[] = [];
  let dataStatus: 'loading' | 'ready' | 'empty' | 'error' | 'unauthorized' = 'loading';
  let dataError = '';
  let nextCursor: string | null = null;
  let pageLoading = false;
  let counts: RealPreviewCounts | null = null;
  let viewportStatus: 'idle' | 'loading' | 'ready' | 'empty' | 'error' | 'unauthorized' = 'idle';
  let viewportError = '';
  let viewportTruncated = false;
  let detailRecord: LabRecord | null = null;
  let detailStatus: 'loading' | 'ready' | 'error' | 'unauthorized' = 'ready';
  let detailError = '';
  let listAbort: AbortController | undefined;
  let viewportAbort: AbortController | undefined;
  let detailAbort: AbortController | undefined;
  const MAX_MAP_PAGES = 64; // 32,000 map candidates at the API's 500-row page bound.

  function dispatch(action: LabAction) { state = reduceLabState(state, action); history.replaceState(null, '', encodeLabHash(state)); }

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
      const page = await repository.list({ query, cursor: reset ? null : nextCursor, limit: 200, signal: controller.signal });
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

  async function loadViewport(bounds: ViewportBounds) {
    if (mode !== 'real-preview') return;
    viewportAbort?.abort();
    const controller = new AbortController();
    viewportAbort = controller;
    viewportStatus = 'loading';
    viewportError = '';
    viewportTruncated = false;
    try {
      const boxes = bounds.west <= bounds.east ? [bounds] : [
        { ...bounds, east: 180 },
        { ...bounds, west: -180 },
      ].filter(box => box.west < box.east);
      const accumulated: LabRecord[] = [];
      let pages = 0;
      for (const box of boxes) {
        let cursor: string | null = null;
        do {
          const page = await repository.viewport(box, { cursor, limit: 500, signal: controller.signal });
          accumulated.push(...page.records.map(mapRealPreviewCandidate));
          cursor = page.nextCursor;
          pages += 1;
          if (pages >= MAX_MAP_PAGES && cursor) {
            viewportTruncated = true;
            cursor = null;
          }
          if (controller.signal.aborted) return;
        } while (cursor);
      }
      if (controller.signal.aborted) return;
      viewportRecords = [...new Map(accumulated.map(record => [record.id, record])).values()];
      viewportStatus = viewportRecords.length ? 'ready' : 'empty';
    } catch (error) {
      if (controller.signal.aborted) return;
      viewportStatus = errorState(error);
      viewportError = error instanceof Error ? error.message : 'The map records could not be loaded.';
    }
  }

  let observedQuery: string | undefined;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  $: if (mode === 'real-preview' && observedQuery !== state.query) {
    observedQuery = state.query;
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
    const sync = () => state = decodeLabHash(location.hash);
    addEventListener('hashchange', sync);
    let summaryAbort: AbortController | undefined;
    if (mode === 'real-preview') {
      summaryAbort = new AbortController();
      void repository.counts(summaryAbort.signal).then(value => { if (!summaryAbort?.signal.aborted) counts = value; }).catch(() => { /* The primary list surface reports request failures. */ });
    }
    return () => {
      removeEventListener('hashchange', sync);
      if (searchTimer) clearTimeout(searchTimer);
      summaryAbort?.abort(); listAbort?.abort(); viewportAbort?.abort(); detailAbort?.abort();
    };
  });
</script>
<svelte:head><title>Until Every Cage — Map</title></svelte:head>
<div class="lab" data-review-sentinel={mode === 'synthetic' ? LAB_SENTINEL : undefined} data-direction="field" data-scenario={state.scenario} data-data-mode={mode}>
  <main aria-label="Map preview"><h1 class="sr-only">Investigative map</h1>
    <Field {state} records={mode === 'real-preview' ? apiRecords : model.listRecords} mapRecords={mode === 'real-preview' ? viewportRecords : model.mapRecords} {mode}
      dataStatus={dataStatus} {dataError} mapStatus={viewportStatus} mapError={viewportError} mapTruncated={viewportTruncated}
      {detailRecord} {detailStatus} {detailError} {nextCursor} {pageLoading}
      onLoadMore={() => void loadPage(state.query, false)} onViewportBounds={loadViewport} {dispatch}/>
    {#if mode === 'real-preview' && counts}
      <p class="private-counts" role="status">{counts.facilityCandidateCount.toLocaleString()} private candidates · {counts.numericCoordinateCount.toLocaleString()} numeric coordinates · {counts.cityPostalCount.toLocaleString()} city or postal records</p>
    {/if}
  </main>
</div>
<style>.lab,main{height:100dvh;overflow:hidden}.sr-only{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}.private-counts{position:fixed;z-index:6;bottom:.45rem;right:.55rem;max-width:40vw;margin:0;padding:.18rem .32rem;border:1px solid #48504b;background:#171a18e8;color:#c6cbc4;font:500 .58rem system-ui}@media(max-width:40rem){.private-counts{max-width:48vw;font-size:.5rem}}</style>
