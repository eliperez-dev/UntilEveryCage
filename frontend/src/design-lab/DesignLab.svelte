<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { language, tr } from '../app/language';
  import { writable } from 'svelte/store';
  import type { LabAction, LabRecord, LabState, MapDiagnostics, NearbySearchCommand } from './contract';
  import { decodeLabHash, encodeLabHash, reduceLabState } from './state';
  import { createLabViewModel } from './viewModel';
  import { createRealPreviewRepository, mapRealPreviewCandidate, RealPreviewError, type RealPreviewCounts, type RealPreviewFacet } from '../api/RealPreviewRepository';
  import { LocalLocationRepository } from '../api/LocalLocationRepository';
  import { FacetsRepository } from '../api/FacetsRepository';
  import { PublicMapMatchesRepository } from '../api/PublicMapMatchesRepository';
  import { publicSearchFilters } from '../features/search/powerSearch';
  import { PublicReleaseRepository, type PublicReleaseIdentity } from '../api/PublicReleaseRepository';
  import { TestReleaseRepository, type CandidateFacets } from '../api/TestReleaseRepository';
  import { TestReleaseDetailRepository } from '../api/TestReleaseDetailRepository';
  import type { Location } from '../domain/location';
  import { CATEGORY_PRESENTATIONS } from '../features/locations/categoryPresentation';
  import { publicReleaseLabel } from '../features/locations/releasePresentation';
  import type { PublicMapFeed } from '../api/PublicMapFeedRepository';
  import { selectDesignLabDataMode, shouldScheduleListLoad } from './dataMode';
  import Field from './variants/field/Field.svelte';
  import PreviewMasthead from '../app/PreviewMasthead.svelte';
  import { createMapResumeGuard, releaseIdentityKey } from './mapResume';
  import { createPinHoverLabels } from './pinHoverLabels';

  let { active = true, activationId = 0, nearbyCommand = null, onnearbyconsumed }: {
    active?: boolean; activationId?: number; nearbyCommand?: NearbySearchCommand | null; onnearbyconsumed?(id: number): void;
  } = $props();
  let handledNearbyCommand = -1;
  let mounted = $state(false);
  let verifiedActivation = $state(-1);
  let resumeStatus = $state<'checking' | 'ready' | 'error'>('checking');
  const resumeGuard = createMapResumeGuard();

  let labState = $state<LabState>(decodeLabHash(typeof location === 'undefined' ? '' : location.hash));
  let pendingSelectionDismissalCamera: Pick<LabState, 'viewport' | 'navigationViewport' | 'basemap' | 'listOpen' | 'filters'> | null = null;
  const serverMode = typeof document === 'undefined' ? null : document.querySelector<HTMLMetaElement>('meta[name="uec-local-data-mode"]')?.content ?? null;
  // A configured candidate server is itself the explicit local preview
  // boundary. Requiring an extra hash flag here accidentally sent the map to
  // frozen public layers while App routed database and record views to the
  // candidate workspace.
  const privatePreview = (typeof location !== 'undefined' && new URLSearchParams(location.hash.split('?')[1] ?? '').has('f1a')) || serverMode === 'candidate-preview';
  const mode = selectDesignLabDataMode(import.meta.env.DEV, serverMode, privatePreview);
  const dataActive = $derived(active && (mode !== 'public-release' || (resumeStatus === 'ready' && verifiedActivation === activationId)));
  // Fixture projections run only in the synthetic mode.
  let syntheticRecords = $state<readonly LabRecord[]>([]);
  let labSentinel = $state<string | undefined>();
  const model = $derived(createLabViewModel(mode === 'synthetic' ? syntheticRecords : [], labState));
  const repository = createRealPreviewRepository();
  const publicLocationRepository = new LocalLocationRepository();
  const publicMapMatchesRepository = new PublicMapMatchesRepository();
  let mapMatchingIds = $state<readonly string[] | null>(null);
  let mapMatchesStatus = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
  let mapMatchesError = $state('');
  let mapMatchesSearchKey = $state<string | null>(null);
  let mapMatchesTotalCount = $state<number | null>(null);
  let mapMatchesMappedCount = $state<number | null>(null);
  let mapMatchesAttempt = $state(0);
  let matchesAbort: AbortController | undefined;
  let matchesTimer: ReturnType<typeof setTimeout> | undefined;
  let observedMatchKey: string | undefined;
  const publicFacetsRepository = new FacetsRepository();
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
  const pinHoverLabels = createPinHoverLabels(async (id, signal) => {
    const releaseId = $publicReleaseManifestIdentity?.releaseId;
    if (!dataActive || mode !== 'public-release' || !releaseId) return null;
    let loaded: LabRecord | undefined;
    if (detailStatus === 'ready' && detailRecord?.id === id && observedSelection === `${$publicReleaseIdentity}:${id}`) loaded = detailRecord;
    if (!loaded && $dataStatus === 'ready' && !listRefreshing && !pageLoading
      && apiRecordsIdentity === $publicReleaseIdentity && apiRecordsSearchKey === JSON.stringify(publicSearchFilters(labState))) loaded = apiRecords.find(record => record.id === id);
    if (loaded) return { name: loaded.name, categoryKey: loaded.taxonomy?.displayCategory ?? 'unclassified' };
    const result = await publicLocationRepository.detail(id, 'official', signal, releaseId);
    return { name: result.location.name, categoryKey: result.location.taxonomy?.displayCategory ?? 'unclassified' };
  });
  const pinHoverContext = $derived(dataActive && mode === 'public-release' && $publicReleaseManifestIdentity
    && $publicReleaseManifestIdentity.releaseId === $publicReleaseId
    && mapMatchesStatus !== 'loading' && mapMatchesStatus !== 'error'
    ? JSON.stringify([releaseIdentityKey($publicReleaseManifestIdentity), labState.query, labState.sourceId, labState.filters, labState.searchScope, mapMatchesAttempt])
    : null);
  $effect(() => { pinHoverLabels.setContext(pinHoverContext); });
  function resolvePinHover(id: string, signal: AbortSignal) {
    // Synchronise at the call boundary too: no old-label window between an
    // identity/filter update and the next effect flush.
    pinHoverLabels.setContext(pinHoverContext);
    return pinHoverLabels.resolve(id, signal);
  }
  const V0_ARCHIVE_RELEASE_ID = 'v0-candidate-2026-10-04-r3';
  const v0ArchiveVerified = writable(false);
  let refreshPinnedPublicRelease: (() => void) | undefined;
  const publicReleaseOptions = $derived([
    ...($activePublicReleaseId ? [{ id: $activePublicReleaseId, label: publicReleaseLabel($activePublicReleaseId)! }] : []),
    ...($v0ArchiveVerified && $activePublicReleaseId !== V0_ARCHIVE_RELEASE_ID ? [{ id: V0_ARCHIVE_RELEASE_ID, label: publicReleaseLabel(V0_ARCHIVE_RELEASE_ID)! }] : []),
  ]);
  const resumeMapHref = $derived(`${encodeLabHash(labState, false, true)}${$pinnedPublicReleaseId ? `&release_id=${encodeURIComponent($pinnedPublicReleaseId)}` : ''}`);
  function selectPublicRelease(releaseId: string) {
    const hash = new URL(location.href).hash;
    const [path, rawQuery = ''] = hash.split('?');
    const query = new URLSearchParams(rawQuery); query.set('release_id', releaseId);
    location.hash = `${path}?${query}`;
  }
  function mapPublicLocation(location: Location): LabRecord {
    const precision = location.evidence?.displayPrecision === 'provider_locality_approximate' ? 'city' : location.evidence?.displayPrecision ?? 'unmapped';
    const geometry = location.evidence?.geometryProvenance;
    const confidence = geometry?.confidence?.trim() ? Number(geometry.confidence) : NaN;
    return {
      id: location.id,
      name: location.name,
      category: CATEGORY_PRESENTATIONS[location.taxonomy?.displayCategory ?? 'unclassified'].label,
      country: location.countryCode ?? location.region,
      locality: location.region,
      precision,
      latitude: location.lat,
      longitude: location.lon,
      ...(geometry?.method ? { coordinateMethod: geometry.method } : {}),
      ...(geometry?.provider ? { coordinateProvider: geometry.provider } : {}),
      ...(Number.isFinite(confidence) && confidence >= 0 && confidence <= 1 ? { coordinateConfidence: confidence } : {}),
      ...(geometry?.confidence_band === 'high' || geometry?.confidence_band === 'medium' || geometry?.confidence_band === 'low' ? { coordinateConfidenceBand: geometry.confidence_band } : {}),
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
  let apiRecordsIdentity: string | null = null;
  let apiRecordsSearchKey: string | undefined;
  const dataStatus = writable<'loading' | 'ready' | 'empty' | 'error' | 'unauthorized'>('loading');
  const dataError = writable('');
  let nextCursor = $state<string | null>(null);
  let pageLoading = $state(false);
  let listRefreshing = $state(false);
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
  let publicFacetAbort: AbortController | undefined;
  let publicFacetRelease: string | null = null;
  async function loadPublicFacets(releaseId: string, ruleset: string) {
    publicFacetAbort?.abort();
    const controller = new AbortController();
    publicFacetAbort = controller;
    publicFacetRelease = releaseId;
    facetsStatus = 'loading';
    try {
      const response = await publicFacetsRepository.get('official', {}, { releaseId, ruleset }, controller.signal);
      if (controller.signal.aborted || $publicReleaseId !== releaseId) return;
      const countries = new Intl.DisplayNames(['en'], { type: 'region' });
      candidateFacets = {
        countries: (response.dimensions.country_code ?? []).map(facet => ({ ...facet, label: countries.of(facet.value) ?? facet.value })),
        sources: (response.dimensions.source_id ?? []).map(facet => ({ ...facet, label: facet.label ?? facet.value })),
        categories: [], activities: [],
      };
      facetsStatus = 'ready';
    } catch {
      if (!controller.signal.aborted) { facetsStatus = 'error'; publicFacetRelease = null; }
    }
  }
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
  const mapReadyToShow = $derived(mode !== 'public-release' || dataActive);
  // This is intentionally memory-only. Private preview rows and credentials never reach
  // browser persistence; the repository continues to issue no-store network requests.

  function dispatch(action: LabAction) {
    // The map can emit a final viewport event while a link is navigating away.
    // Never let that event replace the landing or another destination route.
    if (location.hash.split('?')[0] !== '#/map') return;
    const wasSelected = labState.selectedId !== null;
    const dismissSelection = wasSelected && ((action.type === 'select' && !action.value) || action.type === 'results' || action.type === 'close-workspace');
    const dismissalCamera = dismissSelection && history.state?.uecMapSelection
      ? { viewport: labState.viewport, ...(labState.navigationViewport ? { navigationViewport: labState.navigationViewport } : {}), basemap: labState.basemap, listOpen: action.type === 'results' ? true : action.type === 'close-workspace' ? false : labState.listOpen, filters: labState.filters }
      : null;
    labState = reduceLabState(labState, action);
    const nextHash = `${encodeLabHash(labState, mode !== 'public-release', mode === 'public-release')}${$pinnedPublicReleaseId ? `&release_id=${encodeURIComponent($pinnedPublicReleaseId)}` : ''}`;
    if (action.type === 'select' && action.value && !wasSelected) {
      // Selection is a navigable map state: Back dismisses the dossier. Other
      // frequent map updates (especially viewport movement) stay replace-only.
      history.pushState({ ...history.state, uecMapSelection: true }, '', nextHash);
    } else if (dismissSelection && history.state?.uecMapSelection) {
      // Return to the preceding unselected map entry, carrying the camera and
      // style from the selected entry so the map does not jump back on close.
      pendingSelectionDismissalCamera = dismissalCamera;
      history.back();
    } else {
      history.replaceState(wasSelected && !labState.selectedId ? { ...history.state, uecMapSelection: false } : history.state, '', nextHash);
    }
  }

  $effect(() => {
    const command = nearbyCommand;
    if (!active || mode !== 'public-release' || !command || command.id === handledNearbyCommand) return;
    handledNearbyCommand = command.id;
    dispatch({ type: 'near-device', value: { latitude: command.latitude, longitude: command.longitude } });
    onnearbyconsumed?.(command.id);
  });

  function errorState(error: unknown): 'error' | 'unauthorized' {
    return error instanceof RealPreviewError && error.kind === 'unauthorized' ? 'unauthorized' : 'error';
  }

  async function loadPage(query: string, reset: boolean) {
    if (!dataActive) return;
    if (mode === 'public-release' && !$publicReleaseId) return;
    listAbort?.abort();
    const controller = new AbortController();
    listAbort = controller;
    if (reset) {
      if (!apiRecords.length) $dataStatus = 'loading';
      $dataError = '';
      nextCursor = null;
    } else pageLoading = true;
    try {
      if (mode === 'public-release') {
        if (!$publicReleaseId) return;
        const requestedIdentity = $publicReleaseIdentity;
        const filters = publicSearchFilters({ ...labState, query });
        const page = await publicLocationRepository.list('official', { ...filters, cursor: reset ? undefined : nextCursor ?? undefined, limit: 100 }, controller.signal, $publicReleaseId);
        if (controller.signal.aborted || requestedIdentity !== $publicReleaseIdentity) return;
        const mapped = page.locations.map(mapPublicLocation);
        apiRecords = reset ? mapped : [...new Map([...apiRecords, ...mapped].map(record => [record.id, record])).values()];
        apiRecordsIdentity = requestedIdentity; apiRecordsSearchKey = JSON.stringify(filters);
        nextCursor = page.nextCursor;
        candidateTotalCount = page.totalCount ?? null;
        if (page.ruleset && publicFacetRelease !== page.releaseId) void loadPublicFacets(page.releaseId, page.ruleset);
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
      if (listAbort === controller) {
        pageLoading = false;
        listRefreshing = false;
      }
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
    if (!dataActive) return;
    const listKey = `${labState.query}\u0000${sourceId ?? ''}\u0000${labState.filters.categories.join(',')}\u0000${labState.filters.precisions.join(',')}\u0000${labState.filters.countries.join(',')}\u0000${labState.filters.sources.join(',')}\u0000${labState.filters.activities.join(',')}\u0000${JSON.stringify(labState.searchScope)}\u0000${mode === 'public-release' ? $publicReleaseIdentity ?? '' : ''}`;
    if (shouldScheduleListLoad(mode, $publicReleaseId, observedListKey, listKey)) {
      observedListKey = listKey;
      if (searchTimer) clearTimeout(searchTimer);
      listAbort?.abort();
      listRefreshing = true;
      nextCursor = null;
      $dataError = '';
      if (!apiRecords.length) $dataStatus = 'loading';
      const query = labState.query;
      searchTimer = setTimeout(() => void loadPage(query, true), 180);
    }
  });


  // The compact feed has no searchable names. Query/scope matching comes from
  // one authoritative all-ID response, never from the currently loaded list page.
  $effect(() => {
    if (!dataActive) return;
    const required = mode === 'public-release' && (!!labState.query.trim() || labState.searchScope !== null);
    const identity = $publicReleaseManifestIdentity;
    if (!required) {
      mapMatchesSearchKey = null; mapMatchesTotalCount = null; mapMatchesMappedCount = null;
      if (matchesTimer) clearTimeout(matchesTimer);
      matchesAbort?.abort(); observedMatchKey = undefined;
      mapMatchingIds = null; mapMatchesStatus = 'idle'; mapMatchesError = '';
      return;
    }
    if (!identity) {
      mapMatchesSearchKey = null; mapMatchesTotalCount = null; mapMatchesMappedCount = null;
      if (matchesTimer) clearTimeout(matchesTimer);
      matchesAbort?.abort(); observedMatchKey = undefined;
      mapMatchingIds = []; mapMatchesStatus = 'loading'; mapMatchesError = '';
      return;
    }
    let filters: import('../api/LocalLocationRepository').LocationFilters;
    try { filters = publicSearchFilters(labState); }
    catch {
      mapMatchesSearchKey = null; mapMatchesTotalCount = null; mapMatchesMappedCount = null;
      if (matchesTimer) clearTimeout(matchesTimer);
      matchesAbort?.abort(); observedMatchKey = undefined;
      mapMatchingIds = []; mapMatchesStatus = 'error'; mapMatchesError = 'The selected search area is invalid.';
      return;
    }
    // This comparison is transient request coordination, never a search cache.
    const requestKey = JSON.stringify([identity.releaseId, identity.manifestSha256, identity.suppressionGeneration, filters, mapMatchesAttempt]);
    if (requestKey === observedMatchKey) return;
    observedMatchKey = requestKey;
    mapMatchesSearchKey = null; mapMatchesTotalCount = null; mapMatchesMappedCount = null;
    if (matchesTimer) clearTimeout(matchesTimer);
    matchesAbort?.abort();
    const controller = new AbortController();
    matchesAbort = controller;
    mapMatchingIds = []; mapMatchesStatus = 'loading'; mapMatchesError = '';
    matchesTimer = setTimeout(() => {
      void publicMapMatchesRepository.get(filters, identity, controller.signal).then(matches => {
        if (controller.signal.aborted || matchesAbort !== controller || $publicReleaseManifestIdentity?.releaseId !== identity.releaseId || $publicReleaseManifestIdentity.manifestSha256 !== identity.manifestSha256 || $publicReleaseManifestIdentity.suppressionGeneration !== identity.suppressionGeneration) return;
        mapMatchingIds = matches.facilityIds;
        mapMatchesSearchKey = JSON.stringify([identity.releaseId, identity.manifestSha256, identity.suppressionGeneration, filters]);
        mapMatchesTotalCount = matches.totalCount;
        mapMatchesMappedCount = matches.mappedCount;
        mapMatchesStatus = 'ready';
      }).catch(() => {
        if (controller.signal.aborted || matchesAbort !== controller) return;
        mapMatchingIds = []; mapMatchesStatus = 'error';
        mapMatchesError = 'Matching map locations could not be loaded. Try again.';
      });
    }, 180);
  });


  let observedSelection: string | null | undefined;
  $effect(() => { if (dataActive && mode !== 'synthetic' && (mode !== 'public-release' || !!$publicReleaseId) && observedSelection !== `${mode === 'public-release' ? $publicReleaseIdentity : mode}:${labState.selectedId ?? ''}`) {
    observedSelection = `${mode === 'public-release' ? $publicReleaseIdentity : mode}:${labState.selectedId ?? ''}`;
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
          detailError = 'This facility could not be loaded. Please try again.';
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
        const decodedHash = decodeLabHash(location.hash);
        const decoded = { ...decodedHash, query: new URLSearchParams(location.hash.split('?')[1] ?? '').has('q') ? decodedHash.query : labState.query, searchScope: labState.searchScope, ...(labState.navigationViewport ? { navigationViewport: labState.navigationViewport, viewport: labState.viewport } : {}) };
        // Browser Back and the dossier close button both leave a selected
        // history entry. Preserve its final camera/style over the older URL.
        const camera = pendingSelectionDismissalCamera
          ?? (labState.selectedId && !decoded.selectedId
            ? { viewport: labState.viewport, ...(labState.navigationViewport ? { navigationViewport: labState.navigationViewport } : {}), basemap: labState.basemap }
            : null);
        pendingSelectionDismissalCamera = null;
        labState = camera ? { ...decoded, ...camera } : decoded;
        if (camera) {
          const preservedHash = `${encodeLabHash(labState, mode !== 'public-release', mode === 'public-release')}${$pinnedPublicReleaseId ? `&release_id=${encodeURIComponent($pinnedPublicReleaseId)}` : ''}`;
          history.replaceState(history.state, '', preservedHash);
        }
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
      const invalidate = () => {
        $publicReleaseId = null; $publicReleaseManifestIdentity = null; $publicReleaseIdentity = null; $publicMapMeta = null;
        apiRecords = []; nextCursor = null; candidateTotalCount = null; detailRecord = null; aggregateMemberRecords = [];
        mapMatchingIds = []; mapMatchesStatus = 'loading'; observedMatchKey = undefined;
        listAbort?.abort(); matchesAbort?.abort(); detailAbort?.abort(); publicFacetAbort?.abort(); referenceAbort?.abort();
        observedListKey = undefined; observedSelection = undefined; publicFacetRelease = null; candidateFacets = null;
      };
      const checkRelease = () => {
        if (!active || summaryAbort?.signal.aborted) return;
        const requestedActivation = activationId;
        if (verifiedActivation !== requestedActivation) resumeStatus = 'checking';
        void resumeGuard.verify(async signal => {
          const latest = await publicReleaseRepository.current('official', signal);
          const current = $pinnedPublicReleaseId ? await publicReleaseRepository.current('official', signal, $pinnedPublicReleaseId) : latest;
          if (!current) throw new Error('Selected release unavailable');
          return { latest, current };
        }, ({ latest, current }) => {
          if (!active || activationId !== requestedActivation) return;
          $activePublicReleaseId = latest?.releaseId ?? null;
          const identity = releaseIdentityKey(current);
          if (identity !== $publicReleaseIdentity) {
            invalidate();
            $publicReleaseId = current.releaseId;
            $publicReleaseManifestIdentity = current;
            $publicReleaseIdentity = identity;
            $dataStatus = 'loading'; $dataError = ''; listRefreshing = false;
          }
          verifiedActivation = requestedActivation; resumeStatus = 'ready';
        }, () => {
          invalidate();
          verifiedActivation = -1; resumeStatus = 'error';
          $dataStatus = 'error'; $dataError = 'The public release could not be checked.';
        });
      };
      refreshPinnedPublicRelease = checkRelease;
      void publicReleaseRepository.current('official', summaryAbort.signal, V0_ARCHIVE_RELEASE_ID).then(archive => {
        if (!summaryAbort?.signal.aborted) $v0ArchiveVerified = archive?.releaseId === V0_ARCHIVE_RELEASE_ID;
      }).catch(() => { if (!summaryAbort?.signal.aborted) $v0ArchiveVerified = false; });
      const timer = setInterval(() => { if (active && !document.hidden) checkRelease(); }, 60_000);
      document.addEventListener('visibilitychange', () => { if (active && !document.hidden) checkRelease(); }, { signal: summaryAbort.signal });
      (summaryAbort as AbortController & { releaseTimer?: ReturnType<typeof setInterval> }).releaseTimer = timer;
    } else if (mode === 'candidate-preview') {
      summaryAbort = new AbortController();
      void testReleaseRepository.facets(summaryAbort.signal).then(value => { if (!summaryAbort?.signal.aborted) { candidateFacets = value; facetsStatus = 'ready'; } }).catch(error => { if (!summaryAbort?.signal.aborted) facetsStatus = errorState(error); });
    } else if (mode === 'real-preview') {
      summaryAbort = new AbortController();
      void repository.counts(summaryAbort.signal).then(value => { if (!summaryAbort?.signal.aborted) counts = value; }).catch(() => { /* The primary list surface reports request failures. */ });
      void repository.facets(summaryAbort.signal).then(value => { if (!summaryAbort?.signal.aborted) { facets = value; facetsStatus = 'ready'; } }).catch(error => { if (!summaryAbort?.signal.aborted) facetsStatus = errorState(error); });
    }
    mounted = true;
    return () => {
      mounted = false;
      resumeGuard.pause();
      removeEventListener('hashchange', sync);
      removeEventListener('popstate', sync);
      if (searchTimer) clearTimeout(searchTimer);
      if (matchesTimer) clearTimeout(matchesTimer);
      matchesAbort?.abort();
      summaryAbort?.abort();
      refreshPinnedPublicRelease = undefined;
      const releaseTimer = (summaryAbort as (AbortController & { releaseTimer?: ReturnType<typeof setInterval> }) | undefined)?.releaseTimer;
      if (releaseTimer) clearInterval(releaseTimer);
      listAbort?.abort(); referenceAbort?.abort(); detailAbort?.abort(); publicFacetAbort?.abort();
    };
  });
  $effect(() => {
    if (!mounted || mode !== 'public-release') return;
    activationId;
    if (active) {
      untrack(() => refreshPinnedPublicRelease?.());
    } else {
      resumeGuard.pause(); verifiedActivation = -1;
      if (searchTimer) clearTimeout(searchTimer);
      if (matchesTimer) clearTimeout(matchesTimer);
      if (listRefreshing || pageLoading || facetsStatus === 'loading') observedListKey = undefined;
      if (detailStatus === 'loading') observedSelection = undefined;
      if (mapMatchesStatus === 'loading') observedMatchKey = undefined;
      listAbort?.abort(); matchesAbort?.abort(); detailAbort?.abort(); publicFacetAbort?.abort(); referenceAbort?.abort();
      listRefreshing = false; pageLoading = false;
    }
  });
</script>
<svelte:head>{#if active}<title>Until Every Cage: Map</title>{/if}</svelte:head>
<div class="lab" data-review-sentinel={mode === 'synthetic' ? labSentinel : undefined} data-direction="field" data-scenario={labState.scenario} data-data-mode={mode}>
  <div class="map-preview"><h1 class="sr-only">Investigative map</h1>
    {#if active && !mapReadyToShow}<div class="resume-error-header"><PreviewMasthead current="map" mapHref={resumeMapHref} /></div>{/if}
    {#if active && !mapReadyToShow}<main class="resume-status" aria-live="polite">{#if resumeStatus === 'error'}<p role="alert">{tr('The public release could not be checked.', $language)}</p><button type="button" onclick={() => refreshPinnedPublicRelease?.()}>{tr('Retry', $language)}</button>{:else}<p role="status">{tr('Preparing the map…', $language)}</p>{/if}</main>{/if}
    <div class="retained-map-content" hidden={!mapReadyToShow} inert={!mapReadyToShow}>
    <Field active={dataActive} state={labState} {coverageOpen} records={mode !== 'synthetic' ? apiRecords : model.listRecords} mapRecords={mode !== 'synthetic' ? [] : model.mapRecords} {mode} publicReleaseId={$publicReleaseId} selectedPublicReleaseId={$publicReleaseId ?? $pinnedPublicReleaseId ?? null} publicReleaseIdentity={$publicReleaseIdentity} publicReleaseManifestIdentity={$publicReleaseManifestIdentity} publicMapMeta={$publicMapMeta} releaseOptions={publicReleaseOptions} onreleasechange={selectPublicRelease} onMapFeedMeta={(meta) => { $publicMapMeta = meta; }}
      dataStatus={$dataStatus} dataError={$dataError} {listRefreshing} {mapMatchingIds} {mapMatchesStatus} {mapMatchesError} {mapMatchesSearchKey} {mapMatchesTotalCount} {mapMatchesMappedCount} onRetryMapMatches={() => mapMatchesAttempt += 1}
      {detailRecord} {detailStatus} {detailError} {nextCursor} {pageLoading} {resolvePinHover}
      {facets} {facetsStatus} {candidateFacets} {candidateTotalCount} {mapDiagnostics} {aggregateMemberRecords} {aggregateNextCursor} {aggregateLoading} {aggregateError} onMapTiming={timing=>{sourceMaterializeMs=timing.sourceMaterializeMs;clusterReadyMs=timing.clusterReadyMs;if(timing.zoomSettleMs!==undefined)zoomSettleMs=timing.zoomSettleMs;}} onLoadMore={() => void loadPage(labState.query, false)} onMapReference={(key, refSourceId) => void loadReference(key, true, refSourceId)} onLoadMoreAggregate={() => { if (aggregateReferenceKey) void loadReference(aggregateReferenceKey, false); }} {dispatch}/>
    </div>
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
  .retained-map-content[hidden] { display: block; visibility: hidden; }
  .retained-map-content { height: 100%; }
  .resume-status { position: absolute; z-index: 5; inset: 0; display: grid; place-content: center; padding: 2rem; background: var(--page, #141414); color: var(--ink, #f2f0e8); text-align: center; }
  .resume-status button { min-height: 2.75rem; padding: .6rem 1rem; border: 1px solid currentColor; color: inherit; background: transparent; }
  .resume-error-header { position: relative; z-index: 6; }
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
