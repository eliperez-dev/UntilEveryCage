<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { writable } from 'svelte/store';
  import type { LabAction, LabRecord, LabState, MapDiagnostics } from './contract';
  import { decodeLabHash, encodeLabHash, reduceLabState } from './state';
  import { createLabViewModel } from './viewModel';
  import { createRealPreviewRepository, mapRealPreviewCandidate, RealPreviewError, type RealPreviewCounts, type RealPreviewFacet } from '../api/RealPreviewRepository';
  import { LocalLocationRepository } from '../api/LocalLocationRepository';
  import { PublicReleaseRepository, type PublicReleaseIdentity } from '../api/PublicReleaseRepository';
  import { TestReleaseRepository, type CandidateFacets } from '../api/TestReleaseRepository';
  import { TestReleaseDetailRepository } from '../api/TestReleaseDetailRepository';
  import type { Location } from '../domain/location';
  import { CATEGORY_PRESENTATIONS } from '../features/locations/categoryPresentation';
  import type { PublicMapFeed } from '../api/PublicMapFeedRepository';
  import { selectDesignLabDataMode, shouldScheduleListLoad } from './dataMode';
  import Field from './variants/field/Field.svelte';

  let labState = $state<LabState>(decodeLabHash(typeof location === 'undefined' ? '' : location.hash));
  const serverMode = typeof document === 'undefined' ? null : document.querySelector<HTMLMetaElement>('meta[name="uec-local-data-mode"]')?.content ?? null;
  // A configured candidate server is itself the explicit local preview
  // boundary. Requiring an extra hash flag here accidentally sent the map to
  // frozen public layers while App routed database and record views to the
  // candidate workspace.
  const privatePreview = (typeof location !== 'undefined' && new URLSearchParams(location.hash.split('?')[1] ?? '').has('f1a')) || serverMode === 'candidate-preview';
  const mode = selectDesignLabDataMode(import.meta.env.DEV, serverMode, privatePreview);
  // Fixture projections run only in the synthetic mode.
  let syntheticRecords = $state<readonly LabRecord[]>([]);
  let labSentinel = $state<string | undefined>();
  const model = $derived(createLabViewModel(mode === 'synthetic' ? syntheticRecords : [], labState));
  const repository = createRealPreviewRepository();
  const publicLocationRepository = new LocalLocationRepository();
  const publicReleaseRepository = new PublicReleaseRepository();
  const releaseFromHash = () => {
    const value = new URLSearchParams(location.hash.split('?')[1] ?? '').get('release_id');
    return value && /^[A-Za-z0-9._-]{1,160}$/.test(value) ? value : undefined;
  };
  const pinnedPublicReleaseId = writable<string | undefined>(typeof location === 'undefined' ? undefined : releaseFromHash());
  const testReleaseRepository = new TestReleaseRepository();
  const testReleaseDetailRepository = new TestReleaseDetailRepository();
  const publicReleaseId = writable<string | null>(null);
  const activePublicReleaseId = writable<string | null>(null);
  const publicReleaseIdentity = writable<string | null>(null);
  const publicReleaseManifestIdentity = writable<PublicReleaseIdentity | null>(null);
  const publicMapMeta = writable<PublicMapFeed['meta'] | null>(null);
  const V0_ARCHIVE_RELEASE_ID = 'v0-candidate-2026-10-04-r3';
  const v0ArchiveVerified = writable(false);
  let refreshPinnedPublicRelease: (() => void) | undefined;
  const publicReleaseOptions = $derived([
    ...($activePublicReleaseId ? [{ id: $activePublicReleaseId, label: `Current verified release ${$activePublicReleaseId}` }] : []),
    ...($v0ArchiveVerified && $activePublicReleaseId !== V0_ARCHIVE_RELEASE_ID ? [{ id: V0_ARCHIVE_RELEASE_ID, label: 'v0 verified archive' }] : []),
  ]);
  function selectPublicRelease(releaseId: string) {
    const hash = new URL(location.href).hash;
    const [path, rawQuery = ''] = hash.split('?');
    const query = new URLSearchParams(rawQuery); query.set('release_id', releaseId);
    location.hash = `${path}?${query}`;
  }
  function mapPublicLocation(location: Location): LabRecord {
    const precision = location.evidence?.displayPrecision === 'provider_locality_approximate' ? 'city' : location.evidence?.displayPrecision ?? 'unmapped';
    return {
      id: location.id,
      name: location.name,
      category: CATEGORY_PRESENTATIONS[location.taxonomy?.displayCategory ?? 'unclassified'].label,
      country: location.region,
      locality: location.region,
      precision,
      latitude: location.lat,
      longitude: location.lon,
      ...(location.sourceId ? { sourceId: location.sourceId } : {}),
      ...(location.source ? { sourceName: location.source } : {}),
      ...(location.evidence?.sourceUrl ? { sourceUrl: location.evidence.sourceUrl } : {}),
      ...(location.evidence?.retrievedAt ? { retrievedAt: location.evidence.retrievedAt } : {}),
      ...(location.observed ? { observedAt: location.observed } : {}),
      ...(location.evidence?.displayPrecision ? { displayPrecision: location.evidence.displayPrecision } : {}),
      ...(location.taxonomy ? { taxonomy: location.taxonomy } : {}),
      ...(location.evidence?.factualReviewStatus ? { factualReviewStatus: location.evidence.factualReviewStatus } : {}),
      ...(location.evidence?.privacyScreeningStatus ? { privacyScreeningStatus: location.evidence.privacyScreeningStatus } : {}),
      projectApproval: location.evidence?.projectApproval === 'approved',
      ...(location.sourceFacts ? { sourceFacts: location.sourceFacts } : {}),
    };
  }
  const sourceId = $derived(labState.sourceId);
  let apiRecords = $state<LabRecord[]>([]);
  const dataStatus = writable<'loading' | 'ready' | 'empty' | 'error' | 'unauthorized'>('loading');
  const dataError = writable('');
  let nextCursor = $state<string | null>(null);
  let pageLoading = $state(false);
  let counts = $state<RealPreviewCounts | null>(null);
  let coverageOpen = $state(false);
  $effect(() => { if (labState.listOpen && coverageOpen) coverageOpen = false; });
  let facets = $state<readonly RealPreviewFacet[]>([]);
  let facetsStatus = $state<'loading' | 'ready' | 'error' | 'unauthorized'>('loading');
  let candidateFacets = $state<CandidateFacets | null>(null);
  let candidateTotalCount = $state<number | null>(null);
  let detailRecord = $state<LabRecord | null>(null);
  let detailStatus = $state<'loading' | 'ready' | 'error' | 'unauthorized'>('ready');
  let detailError = $state('');
  let listAbort: AbortController | undefined;
  let sourceMaterializeMs = $state<number | null>(null); let clusterReadyMs = $state<number | null>(null); let zoomSettleMs = $state<number | null>(null);
  let detailAbort: AbortController | undefined;
  let referenceAbort: AbortController | undefined;
  let aggregateReferenceKey: string | null = null;
  let aggregateReferenceSourceId: string | null = null;
  let aggregateMemberRecords = $state<LabRecord[]>([]);
  let aggregateNextCursor = $state<string | null>(null);
  let aggregateLoading = $state(false);
  let aggregateError = $state('');
  let mapDiagnostics = $state<MapDiagnostics>({ zoom: 0, currentTiles: 0, readyTiles: 0, cacheEntries: 0, cacheCapacity: 0, cacheHits: 0, cacheMisses: 0, inFlight: 0, lastFetchMs: null, renderedRecords: 0, sourceId: null, truncated: false, sourceMaterializeMs: null, clusterReadyMs: null, zoomSettleMs: null });
  // This is intentionally memory-only. Private preview rows and credentials never reach
  // browser persistence; the repository continues to issue no-store network requests.

  function dispatch(action: LabAction) {
    // The map can emit a final viewport event while a link is navigating away.
    // Never let that event replace the destination record/database route.
    if (!location.hash.startsWith('#/map')) return;
    const wasSelected = labState.selectedId !== null;
    labState = reduceLabState(labState, action);
    const nextHash = `${encodeLabHash(labState, mode === 'real-preview')}${$pinnedPublicReleaseId ? `&release_id=${encodeURIComponent($pinnedPublicReleaseId)}` : ''}`;
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
    if (mode === 'public-release' && !$publicReleaseId) return;
    listAbort?.abort();
    const controller = new AbortController();
    listAbort = controller;
    if (reset) {
      $dataStatus = 'loading';
      $dataError = '';
      apiRecords = [];
      nextCursor = null;
      candidateTotalCount = null;
    } else pageLoading = true;
    try {
      if (mode === 'public-release') {
        if (!$publicReleaseId) return;
        const categoryKeys = labState.filters.categories.map(value => ({ Poultry: 'animal_keeping_and_production', Pig: 'animal_keeping_and_production', Dairy: 'animal_keeping_and_production', Processing: 'processing_and_preparation', Laboratory: 'research_and_animal_use', Aquaculture: 'animal_keeping_and_production' } as Record<string, string>)[value]).filter((value): value is import('../domain/taxonomy').TaxonomyPrimaryKey => !!value);
        const page = await publicLocationRepository.list('official', { q: query, category_keys: [...new Set(categoryKeys)], ...(labState.filters.precisions.length ? { precision: labState.filters.precisions.join(',') } : {}), cursor: reset ? undefined : nextCursor ?? undefined, limit: 100 }, controller.signal, $publicReleaseId);
        if (controller.signal.aborted) return;
        const mapped = page.locations.map(mapPublicLocation);
        apiRecords = reset ? mapped : [...new Map([...apiRecords, ...mapped].map(record => [record.id, record])).values()];
        nextCursor = page.nextCursor;
        candidateTotalCount = page.totalCount;
        $dataStatus = apiRecords.length ? 'ready' : 'empty';
        return;
      }
      if (mode === 'candidate-preview') {
        const page = await testReleaseRepository.list({
          q: query,
          sourceIds: [...new Set([...(labState.sourceId ? [labState.sourceId] : []), ...labState.filters.sources])],
          countryCodes: labState.filters.countries,
          categories: labState.filters.categories,
          activities: labState.filters.activities,
          cursor: reset ? null : nextCursor, limit: 100, signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        const mapped = page.locations.map(mapPublicLocation);
        apiRecords = reset ? mapped : [...new Map([...apiRecords, ...mapped].map(record => [record.id, record])).values()];
        nextCursor = page.nextCursor;
        candidateTotalCount = page.totalCount;
        $dataStatus = apiRecords.length ? 'ready' : 'empty';
        return;
      }
      const page = await repository.list({ query, sourceId, cursor: reset ? null : nextCursor, limit: 200, signal: controller.signal });
      if (controller.signal.aborted) return;
      const mapped = page.records.map(mapRealPreviewCandidate);
      const combined = reset ? mapped : [...apiRecords, ...mapped];
      apiRecords = [...new Map(combined.map(record => [record.id, record])).values()];
      nextCursor = page.nextCursor;
      $dataStatus = apiRecords.length ? 'ready' : 'empty';
    } catch (error) {
      if (controller.signal.aborted) return;
      $dataStatus = errorState(error);
      $dataError = error instanceof Error ? error.message : mode === 'public-release' ? 'Public release records could not be loaded.' : 'The private real-data preview could not be loaded.';
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
  $effect(() => { mapDiagnostics = { ...untrack(() => mapDiagnostics), zoom: labState.viewport.zoom, sourceId, sourceMaterializeMs, clusterReadyMs, zoomSettleMs }; });

  let observedListKey: string | undefined;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const listKey = `${labState.query}\u0000${sourceId ?? ''}\u0000${labState.filters.categories.join(',')}\u0000${labState.filters.precisions.join(',')}\u0000${labState.filters.countries.join(',')}\u0000${labState.filters.sources.join(',')}\u0000${labState.filters.activities.join(',')}\u0000${mode === 'public-release' ? $publicReleaseIdentity ?? '' : ''}`;
    if (shouldScheduleListLoad(mode, $publicReleaseId, observedListKey, listKey)) {
      observedListKey = listKey;
      if (searchTimer) clearTimeout(searchTimer);
      listAbort?.abort();
      const query = labState.query;
      searchTimer = setTimeout(() => void loadPage(query, true), 180);
    }
  });


  let observedSelection: string | null | undefined;
  $effect(() => { if (mode !== 'synthetic' && observedSelection !== labState.selectedId) {
    observedSelection = labState.selectedId;
    detailAbort?.abort();
    if (!labState.selectedId) { detailRecord = null; detailStatus = 'ready'; detailError = ''; }
    else {
      const id = labState.selectedId;
      const controller = new AbortController();
      detailAbort = controller;
      detailStatus = 'loading'; detailRecord = null; detailError = '';
      const detailRequest = mode === 'public-release'
        ? $publicReleaseId ? publicLocationRepository.detail(id, 'official', controller.signal, $publicReleaseId).then(result => mapPublicLocation(result.location)) : Promise.reject(new Error('The public release is unavailable.'))
        : mode === 'candidate-preview'
          ? testReleaseDetailRepository.detail(id, controller.signal)
        : repository.detail(id, controller.signal).then(mapRealPreviewCandidate);
      void detailRequest.then(record => {
        if (!controller.signal.aborted) { detailRecord = record; detailStatus = 'ready'; }
      }).catch(error => {
        if (!controller.signal.aborted) {
          detailStatus = errorState(error);
          detailError = error instanceof Error ? error.message : 'The selected record could not be loaded.';
        }
      });
    }
  } });

  onMount(() => {
    if (import.meta.env.DEV && mode === 'synthetic') {
      void import('./fixtures').then(fixtures => {
        syntheticRecords = fixtures.labRecords;
        labSentinel = fixtures.LAB_SENTINEL;
      });
    }
    const sync = () => {
      if (location.hash.startsWith('#/map')) {
        labState = decodeLabHash(location.hash);
        const nextPinnedReleaseId = releaseFromHash();
        if ($pinnedPublicReleaseId !== nextPinnedReleaseId) {
          $pinnedPublicReleaseId = nextPinnedReleaseId;
          refreshPinnedPublicRelease?.();
        }
      }
    };
    addEventListener('hashchange', sync);
    addEventListener('popstate', sync);
    let summaryAbort: AbortController | undefined;
    if (mode === 'public-release') {
      summaryAbort = new AbortController();
      void publicReleaseRepository.current('official', summaryAbort.signal).then(active => {
        if (!summaryAbort?.signal.aborted) $activePublicReleaseId = active?.releaseId ?? null;
      }).catch(() => { if (!summaryAbort?.signal.aborted) $activePublicReleaseId = null; });
      void publicReleaseRepository.current('official', summaryAbort.signal, $pinnedPublicReleaseId).then(current => {
        if (!summaryAbort?.signal.aborted) {
          $publicReleaseId = current?.releaseId ?? null;
          $publicReleaseManifestIdentity = current;
          $publicReleaseIdentity = current ? `${current.releaseId}:${current.manifestSha256}:${current.suppressionGeneration}` : null;
          $dataStatus = current ? 'loading' : 'error';
          $dataError = current ? '' : $pinnedPublicReleaseId ? 'Selected release unavailable.' : 'No verified public release is available.';
        }
      }).catch(() => { if (!summaryAbort?.signal.aborted) { $dataStatus = 'error'; $dataError = 'The public release could not be checked.'; } });
      void publicReleaseRepository.current('official', summaryAbort.signal, V0_ARCHIVE_RELEASE_ID).then(archive => {
        if (!summaryAbort?.signal.aborted) $v0ArchiveVerified = archive?.releaseId === V0_ARCHIVE_RELEASE_ID;
      }).catch(() => { if (!summaryAbort?.signal.aborted) $v0ArchiveVerified = false; });
      const checkRelease = async () => {
        try {
          const active = await publicReleaseRepository.current('official', summaryAbort?.signal);
          if (summaryAbort?.signal.aborted) return;
          $activePublicReleaseId = active?.releaseId ?? null;
          const current = $pinnedPublicReleaseId ? await publicReleaseRepository.current('official', summaryAbort?.signal, $pinnedPublicReleaseId) : active;
          if (summaryAbort?.signal.aborted) return;
          const identity = current ? `${current.releaseId}:${current.manifestSha256}:${current.suppressionGeneration}` : null;
          if (identity !== $publicReleaseIdentity) {
            $publicReleaseId = current?.releaseId ?? null;
            $publicReleaseManifestIdentity = current;
            $publicReleaseIdentity = identity;
            apiRecords = []; nextCursor = null; $publicMapMeta = null;
            observedSelection = undefined;
            $dataStatus = current ? 'loading' : 'error';
            $dataError = current ? '' : $pinnedPublicReleaseId ? 'Selected release unavailable.' : 'No verified public release is available.';
          }
        } catch { /* The map feed and record APIs report current request failures. */ }
      };
      refreshPinnedPublicRelease = () => { void checkRelease(); };
      const timer = setInterval(() => { if (!document.hidden) void checkRelease(); }, 60_000);
      document.addEventListener('visibilitychange', () => { if (!document.hidden) void checkRelease(); }, { signal: summaryAbort.signal });
      // The abort signal removes the listener; the local timer is cleared below.
      (summaryAbort as AbortController & { releaseTimer?: ReturnType<typeof setInterval> }).releaseTimer = timer;
    } else if (mode === 'candidate-preview') {
      summaryAbort = new AbortController();
      void testReleaseRepository.facets(summaryAbort.signal).then(value => { if (!summaryAbort?.signal.aborted) { candidateFacets = value; facetsStatus = 'ready'; } }).catch(error => { if (!summaryAbort?.signal.aborted) facetsStatus = errorState(error); });
    } else if (mode === 'real-preview') {
      summaryAbort = new AbortController();
      void repository.counts(summaryAbort.signal).then(value => { if (!summaryAbort?.signal.aborted) counts = value; }).catch(() => { /* The primary list surface reports request failures. */ });
      void repository.facets(summaryAbort.signal).then(value => { if (!summaryAbort?.signal.aborted) { facets = value; facetsStatus = 'ready'; } }).catch(error => { if (!summaryAbort?.signal.aborted) facetsStatus = errorState(error); });
    }
    return () => {
      removeEventListener('hashchange', sync);
      removeEventListener('popstate', sync);
      if (searchTimer) clearTimeout(searchTimer);
      summaryAbort?.abort();
      refreshPinnedPublicRelease = undefined;
      const releaseTimer = (summaryAbort as (AbortController & { releaseTimer?: ReturnType<typeof setInterval> }) | undefined)?.releaseTimer;
      if (releaseTimer) clearInterval(releaseTimer);
      listAbort?.abort(); referenceAbort?.abort(); detailAbort?.abort();
    };
  });
</script>
<svelte:head><title>Until Every Cage: Map</title></svelte:head>
<div class="lab" data-review-sentinel={mode === 'synthetic' ? labSentinel : undefined} data-direction="field" data-scenario={labState.scenario} data-data-mode={mode}>
  <div class="map-preview"><h1 class="sr-only">Investigative map</h1>
    <Field state={labState} {coverageOpen} records={mode !== 'synthetic' ? apiRecords : model.listRecords} mapRecords={mode !== 'synthetic' ? [] : model.mapRecords} {mode} publicReleaseId={$publicReleaseId} selectedPublicReleaseId={$publicReleaseId ?? $pinnedPublicReleaseId ?? null} publicReleaseIdentity={$publicReleaseIdentity} publicReleaseManifestIdentity={$publicReleaseManifestIdentity} publicMapMeta={$publicMapMeta} releaseOptions={publicReleaseOptions} onreleasechange={selectPublicRelease} onMapFeedMeta={(meta) => { $publicMapMeta = meta; }}
      dataStatus={$dataStatus} dataError={$dataError}
      {detailRecord} {detailStatus} {detailError} {nextCursor} {pageLoading}
      {facets} {facetsStatus} {candidateFacets} {candidateTotalCount} {mapDiagnostics} {aggregateMemberRecords} {aggregateNextCursor} {aggregateLoading} {aggregateError} onMapTiming={timing=>{sourceMaterializeMs=timing.sourceMaterializeMs;clusterReadyMs=timing.clusterReadyMs;if(timing.zoomSettleMs!==undefined)zoomSettleMs=timing.zoomSettleMs;}} onLoadMore={() => void loadPage(labState.query, false)} onMapReference={(key, refSourceId) => void loadReference(key, true, refSourceId)} onLoadMoreAggregate={() => { if (aggregateReferenceKey) void loadReference(aggregateReferenceKey, false); }} {dispatch}/>
    {#if mode === 'real-preview' && counts}
      <aside class:expanded={coverageOpen} class="private-counts" aria-label="Map information">
        <button type="button" aria-expanded={coverageOpen} aria-controls="coverage-details" disabled={labState.listOpen} title={labState.listOpen ? 'Close Search to inspect map information' : undefined} onclick={() => coverageOpen = !coverageOpen}>
          <span>Preview</span><strong>{counts.facilityCandidateCount.toLocaleString()} candidates</strong><span aria-hidden="true">{coverageOpen ? '−' : '+'}</span>
        </button>
        {#if coverageOpen}<div id="coverage-details" class="coverage-details">
          <p>Private development preview · not publication-approved. Counts describe the current private projection, not complete worldwide coverage.</p>
          <dl>
            <div><dt>Source-coordinate locations</dt><dd>{counts.numericCoordinateCount.toLocaleString()}</dd></div>
            <div><dt>Approx. display references</dt><dd>{Math.max(0, counts.mapVisibleCount - counts.numericCoordinateCount).toLocaleString()}</dd></div>
            <div><dt>Private candidates</dt><dd>{counts.facilityCandidateCount.toLocaleString()}</dd></div>
            <div><dt>Source observations</dt><dd>90,164</dd></div>
            <div><dt>Unmapped candidates</dt><dd>{counts.unmappedCandidateCount?.toLocaleString() ?? 'Unavailable'}</dd></div>
          </dl>
          <small>Source: {labState.sourceId ?? 'All available sources'} · Coordinates are precision-unverified; none are labeled exact or approved.</small>
        </div>{/if}
      </aside>
    {/if}
  </div>
</div>
<style>
  .lab, .map-preview { height: 100dvh; overflow: hidden; }
  .sr-only { position: absolute !important; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
  .private-counts {
    position: fixed;
    z-index: 6;
    bottom: 0.35rem;
    left: 50%;
    width: max-content;
    max-width: calc(100vw - .8rem);
    margin: 0;
    border: 1px solid #48504b;
    background: #171a18f2;
    color: #d9ded5;
    font: 500 .7rem/1.3 system-ui;
    font-variant-numeric: tabular-nums;
    transform: translateX(-50%);
  }
  .private-counts > button { display:flex; align-items:center; gap:.45rem; min-height:1.6rem; padding:.2rem .45rem; border:0; background:none; color:#d9ded5; cursor:pointer; font:inherit; }
  .private-counts > button:disabled { cursor:default; }
  .private-counts > button:focus-visible { outline:2px solid #f1efe8; outline-offset:2px; }
  .private-counts > button strong { color:#f1efe8; font-weight:700; white-space:nowrap; }
  .private-counts.expanded { width:min(19rem, calc(100vw - .8rem)); bottom:2.8rem; }
  .coverage-details { padding:.15rem .65rem .65rem; border-top:1px solid #48504b; }
  .coverage-details p, .coverage-details small { display:block; margin:.4rem 0; color:#bac3ba; font-size:.67rem; line-height:1.4; }
  .coverage-details dl { margin:.45rem 0; }
  .coverage-details dl div { display:flex; justify-content:space-between; gap:1rem; padding:.22rem 0; border-bottom:1px solid #343a36; }
  .coverage-details dt { color:#c0c8c0; }
  .coverage-details dd { margin:0; color:#f1efe8; font-weight:700; }
  .lab:has(.private-counts.expanded) :global(.diagnostics-toggle) { display:none; }
  @media (max-width: 40rem) {
    .private-counts { font-size:.72rem; }
    /* MapLibre's attribution sits above the mobile bottom edge. Keep the
       full scope disclosure entirely clear of that control. */
    .private-counts.expanded { bottom:5.3rem; }
  }
</style>
