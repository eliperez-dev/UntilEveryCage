<script lang="ts">
  import { tick } from "svelte";
  import { get, writable } from "svelte/store";
  import type {
    DirectionViewProps,
    LabRecord,
    MapDiagnostics,
    Precision,
    ViewportBounds,
    LabFilters,
    MapDisplaySettings,
    MapDisplaySettingsRequest,
    AreaSummary as AreaSummaryData,
    SearchScope,
  } from "../../contract";
  import type { RealPreviewFacet } from "../../../api/RealPreviewRepository";
  import type { CandidateFacets } from "../../../api/TestReleaseRepository";
  import MapSurface from "../../components/MapSurface.svelte";
  import MapNavigation from "../../components/MapNavigation.svelte";
  import RecordList from "../../components/RecordList.svelte";
  import MobileSearchSheet from "../../components/MobileSearchSheet.svelte";
  import { type SheetSnap } from "../../components/mobileSheet";
  import type { LayoutTuning } from "../../components/mapDebug";
  import RecordDetail from "../../../app/RecordDetail.svelte";
  import PreviewMasthead from "../../../app/PreviewMasthead.svelte";
  import { encodeMapNavigationHash } from "../../state";
  import type { PlaceSuggestion } from "../../../features/placeSearch/placeSearch";
  import { publicReleaseLabel } from "../../../features/locations/releasePresentation";
  import { CATEGORY_PRESENTATIONS } from "../../../features/locations/categoryPresentation";
  import { classificationLabel } from "../../../features/locations/classificationSummary";
  import { language, tr } from '../../../app/language';
  import { serializeRoute } from "../../../app/routeState";
  import { canSearchRecords, parseSearch, searchSuggestions, applySearchSuggestion, areaScopeFromBounds, stateSearchName, type SearchSuggestion } from "../../../features/search/powerSearch";
  import AreaSummary from '../../../features/search/AreaSummary.svelte';
  import type { TaxonomyPrimaryKey } from '../../../domain/taxonomy';
  import MobileSearchFilters from '../../../features/search/MobileSearchFilters.svelte';
  import MobileSearchRecords from '../../../features/search/MobileSearchRecords.svelte';
  import { recordNamePresentation } from '../../../features/locations/recordNamePresentation';
  import { requestDeviceLocation } from '../../../features/search/nearbySearch';
  import { precisionPresentation } from '../../../features/locations/precisionPresentation';
  let {
    active = true,
    state: mapState,
    records,
    mapRecords,
    coverageOpen = false,
    mode = "synthetic",
    publicReleaseId = null,
    selectedPublicReleaseId = null,
    publicReleaseIdentity = null,
    publicReleaseManifestIdentity = null,
    publicMapMeta = null,
    onMapFeedMeta,
    onCandidatePreviewLabel,
    dataStatus = "ready",
    dataError = "",
    mapStatus = "idle",
    mapError = "",
    mapTruncated = false,
    mapMatchingIds = null,
    mapMatchesStatus = "idle",
    mapMatchesError = "",
    mapMatchesSearchKey = null,
    onRetryMapMatches,
    onRetrySearch,
    resolvePinHover,
    mapDiagnostics,
    onMapTiming,
    detailRecord = null,
    detailStatus = "ready",
    detailError = "",
    nextCursor = null,
    pageLoading = false,
    listRefreshing = false,
    onLoadMore,
    onMapReference,
    aggregateMemberRecords = [],
    aggregateNextCursor = null,
    aggregateLoading = false,
    aggregateError = "",
    onLoadMoreAggregate,
    onViewportBounds,
    facets = [],
    facetsStatus = "loading",
    candidateFacets = null,
    candidateTotalCount = null,
    releaseOptions = [],
    onreleasechange,
    dispatch,
  }: DirectionViewProps & {
    active?: boolean;
    selectedPublicReleaseId?: string | null;
    coverageOpen?: boolean;
    mapDiagnostics?: MapDiagnostics;
    facets?: readonly RealPreviewFacet[];
    facetsStatus?: "loading" | "ready" | "error" | "unauthorized";
    candidateFacets?: CandidateFacets | null;
    candidateTotalCount?: number | null;
    listRefreshing?: boolean;
    releaseOptions?: readonly { id: string; label: string }[];
    onreleasechange?(releaseId: string): void;
  } = $props();
  const candidatePreviewLabel = writable<string | null>(null);
  const categories = [
    "Poultry",
    "Pig",
    "Dairy",
    "Processing",
    "Laboratory",
    "Aquaculture",
  ];
  const precisions: readonly Precision[] = [
    "exact",
    "source_reported",
    "approximate",
    "city",
    "coarse",
    "unmapped",
  ];
  const mapRows = $derived(mapRecords ?? records);
  const recordPool = $derived([
    ...new Map(
      [...records, ...mapRows, ...aggregateMemberRecords].map((record) => [
        record.id,
        record,
      ]),
    ).values(),
  ]);
  const selected = $derived(
    (detailRecord?.id === mapState.selectedId ? detailRecord : null) ??
      recordPool.find((record) => record.id === mapState.selectedId) ??
      null,
  );
  const publicMap = $derived(mode === 'public-release');
  const popupLocation = $derived(publicMap && selected?.id === mapState.selectedId && selected?.longitude != null && selected.latitude != null
    ? { longitude: selected.longitude, latitude: selected.latitude } : null);
  const popupSource = $derived(selected?.sourceName ?? (selected?.sourceId ? sourceName(selected.sourceId) : ''));
  let popupAnchor = $state<{ x: number; y: number } | null>(null);
  let mapSummary = $state<HTMLElement>();
  let popupHeight = $state(184);
  let mapWidth = $state(0);
  const popupInset = $derived(Math.min(148, mapWidth / 2));
  const popupLeft = $derived(popupAnchor ? Math.max(popupInset, Math.min(mapWidth - popupInset, popupAnchor.x)) : mapWidth / 2);
  const popupBelow = $derived(!!popupAnchor && popupAnchor.y < popupHeight + 84);
  const popupTop = $derived(popupAnchor ? popupAnchor.y + (popupBelow ? 16 : -34) : null);
  let mapStyle = $state<'automatic' | 'vector' | 'satellite'>('automatic');
  const automaticBasemap = $derived(publicMap && mapStyle === 'automatic' && mapState.basemap !== 'satellite');
  const facilityPageHref = $derived(selected ? serializeRoute({
    kind: 'record', facilityId: selected.id,
    ...(mode === 'public-release' ? { profile: 'official', ...(publicReleaseId ? { releaseId: publicReleaseId } : {}) } : {}),
  }) : null);
  const aggregateRecords = $derived(
    mapState.aggregateMemberIds === null
      ? records
      : recordPool.filter((record) =>
          mapState.aggregateMemberIds!.includes(record.id),
        ),
  );
  const aggregateOpen = $derived(mapState.aggregateMemberIds !== null);
  const aggregateRequestedCount = $derived(
    mapState.aggregateMemberIds?.length ?? 0,
  );
  const aggregateContext = $derived(aggregateContextFor(aggregateRecords));
  const mapped = $derived(
    mapRows.filter(
      (record) => record.latitude !== null && record.longitude !== null,
    ),
  );
  const resultCount = $derived(aggregateRecords.length);
  const areaSummary = writable<AreaSummaryData | null>(null);
  let fitResultsRequest = $state(0);
  const workspaceOpen = $derived(mapState.listOpen || Boolean(mapState.selectedId) || aggregateOpen);
  const railWidth = writable<number | null>(null);
  const layoutTuning = writable<LayoutTuning>({ panelWidthPercent: 100 / 3, rowPadding: 16, typeScale: 1, mobileSheetPercent: 60, mobileExpandedPercent: 90 });
  const sheetHeight = writable(56);
  const workspaceHeight = writable(0);
  const detailMapPreview = writable(false);
  const mobileLayout = writable(false);
  const resultsSheetSnap = writable<SheetSnap>('middle');
  const detailSheetSnap = writable<SheetSnap>('middle');
  const mobileFiltersOpen = writable(false);
  let locationRequest: AbortController | undefined;
  let locationError = $state('');
  let locating = $state(false);
  $effect(() => {
    if (!active) {
      locationRequest?.abort();
      if (get(mobileFiltersOpen)) mobileFiltersOpen.set(false);
    }
    return () => locationRequest?.abort();
  });
  async function locateFromTools() {
    if (locating) return;
    const request = new AbortController();
    locationRequest = request;
    locationError = '';
    locating = true;
    try {
      const position = await requestDeviceLocation(request.signal);
      if (request.signal.aborted) return;
      searchMode.set('radius');
      dispatch({ type: 'near-device', value: { ...position, radiusKm: $radiusMiles * 1.609344 } });
    } catch (error) {
      if (!request.signal.aborted) locationError = error instanceof Error ? error.message : 'Your location is unavailable.';
    } finally {
      if (locationRequest === request) { locationRequest = undefined; locating = false; }
    }
  }
  let previousResultsOpen = $state(false);
  const detailCollapsed = $derived((publicMap && Boolean(mapState.selectedId)) || $detailMapPreview || ($mobileLayout && Boolean(mapState.selectedId) && $detailSheetSnap === 'collapsed'));
  const showingDetail = $derived(Boolean(mapState.selectedId) && !detailCollapsed);
  function measureWorkspace(node: HTMLDivElement) {
    const measure = () => {
      mapWidth = node.clientWidth;
      mobileLayout.set(matchMedia('(max-width:40rem)').matches);
      const viewportBottom = window.visualViewport ? window.visualViewport.offsetTop + window.visualViewport.height : window.innerHeight;
      const available = Math.max(0, viewportBottom - node.getBoundingClientRect().top);
      workspaceHeight.set(available);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    window.addEventListener('resize', measure);
    window.visualViewport?.addEventListener('resize', measure);
    window.visualViewport?.addEventListener('scroll', measure);
    measure();
    return { destroy() { observer.disconnect(); window.removeEventListener('resize', measure); window.visualViewport?.removeEventListener('resize', measure); window.visualViewport?.removeEventListener('scroll', measure); } };
  }
  function fitFilterViewport(node: HTMLDivElement) {
    let frame = 0;
    const disclosure = node.closest('details');
    const measure = () => {
      frame = 0;
      if (!disclosure?.open) return;
      const viewportBottom = window.visualViewport ? window.visualViewport.offsetTop + window.visualViewport.height : window.innerHeight;
      const bottom = Math.min(viewportBottom, sheet?.getBoundingClientRect().bottom ?? viewportBottom);
      node.style.setProperty('--filter-available-height', `${Math.max(0, bottom - node.getBoundingClientRect().top)}px`);
    };
    const schedule = () => { if (frame) cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    const observer = new ResizeObserver(schedule);
    const workspace = node.closest('.workspace');
    const map = workspace?.querySelector('.map-stage');
    const search = node.closest('.search-tools');
    const sheet = node.closest('.results');
    if (map) observer.observe(map);
    if (search) observer.observe(search);
    if (sheet) observer.observe(sheet);
    disclosure?.addEventListener('toggle', schedule);
    window.addEventListener('resize', schedule);
    window.visualViewport?.addEventListener('resize', schedule);
    window.visualViewport?.addEventListener('scroll', schedule);
    schedule();
    return { destroy() { if (frame) cancelAnimationFrame(frame); observer.disconnect(); disclosure?.removeEventListener('toggle', schedule); window.removeEventListener('resize', schedule); window.visualViewport?.removeEventListener('resize', schedule); window.visualViewport?.removeEventListener('scroll', schedule); } };
  }
  function updateLayoutTuning(value: LayoutTuning) {
    layoutTuning.set({
      panelWidthPercent: Math.max(25, Math.min(55, value.panelWidthPercent)),
      rowPadding: Math.max(10, Math.min(22, value.rowPadding)),
      typeScale: Math.max(.9, Math.min(1.15, value.typeScale)),
      mobileSheetPercent: Math.max(35, Math.min(65, value.mobileSheetPercent ?? 60)),
      mobileExpandedPercent: Math.max(75, Math.min(95, value.mobileExpandedPercent ?? 90)),
    });
    railWidth.set(null);
  }
  function resetLayoutTuning() {
    layoutTuning.set({ panelWidthPercent: 100 / 3, rowPadding: 16, typeScale: 1, mobileSheetPercent: 60, mobileExpandedPercent: 90 });
    railWidth.set(null);
  }
  function boundedRailWidth(width: number) {
    const available = Math.max(0, window.innerWidth - 48);
    const minimum = Math.min(448, available);
    const maximum = Math.min(available, Math.max(minimum, Math.floor(window.innerWidth * .55)));
    return Math.max(minimum, Math.min(maximum, width));
  }
  function resizeRail(event: PointerEvent) {
    const startX = event.clientX;
    const startWidth = event.currentTarget instanceof HTMLElement ? event.currentTarget.closest('.results')?.getBoundingClientRect().width ?? 448 : 448;
    const resize = (move: PointerEvent) => { railWidth.set(boundedRailWidth(startWidth + move.clientX - startX)); };
    const stop = () => { window.removeEventListener('pointermove', resize); window.removeEventListener('pointerup', stop); };
    window.addEventListener('pointermove', resize); window.addEventListener('pointerup', stop, { once: true });
  }
  function resizeRailKey(event: KeyboardEvent) {
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault();
      const width = event.currentTarget instanceof HTMLElement ? event.currentTarget.closest('.results')?.getBoundingClientRect().width ?? 448 : 448;
      railWidth.set(boundedRailWidth(width + (event.key === 'ArrowRight' ? 24 : -24)));
    }
  }
  const activeFilters = $derived(
    (mapState.query.trim() ? 1 : 0) +
    (mapState.sourceId ? 1 : 0) +
    (mapState.searchScope ? 1 : 0) +
    mapState.filters.categories.length + mapState.filters.precisions.length + mapState.filters.countries.length + mapState.filters.sources.length + mapState.filters.activities.length,
  );
  function toggleCandidateFilter(field: 'countries' | 'sources' | 'categories' | 'activities', value: string, checked: boolean) {
    const current = mapState.filters[field];
    dispatch({ type: 'filters', value: { ...mapState.filters, [field]: checked ? [...new Set([...current, value])] : current.filter(item => item !== value) } });
    dispatch({ type: 'results' });
  }
  const precisionLabel = (record: LabRecord) =>
    mode === "real-preview"
      ? record.sourceId === 'us.fsis' && record.coordinatePrecision === 'source-provided'
        ? 'Source-provided coordinates'
        : record.precision === "city"
        ? "Approximate city location · not a facility point"
        : record.precision === "exact"
          ? "Numeric source coordinate · pending review"
          : record.precision === "approximate" &&
              record.coordinatePrecision === "source-precision-unknown"
            ? "Approximate source coordinate · precision unknown"
            : record.precision === "approximate"
              ? "Approximate source coordinate · pending review"
              : record.precision === "coarse"
                ? "City or postal · no approved map geometry"
                : "Unmapped · list only"
      : record.precision === 'source_reported' ? 'Source-provided coordinates'
        : record.precision === 'approximate' ? 'Approximate location · not an exact facility point'
          : record.precision === 'exact' ? 'Exact location shown from an approved source coordinate'
            : `${record.precision} precision`;
  function category(value: string, checked: boolean) {
    dispatch({
      type: "filters",
      value: {
        ...mapState.filters,
        categories: checked
          ? [...mapState.filters.categories, value]
          : mapState.filters.categories.filter((item) => item !== value),
      },
    });
    dispatch({ type: 'results' });
  }
  function precision(value: Precision, checked: boolean) {
    dispatch({
      type: "filters",
      value: {
        ...mapState.filters,
        precisions: checked
          ? [...mapState.filters.precisions, value]
          : mapState.filters.precisions.filter((item) => item !== value),
      },
    });
    dispatch({ type: 'results' });
  }
  const sources = $derived(
    [...new Set(facets.map((facet) => facet.sourceId))].sort(),
  );
  let selectionOrigin: HTMLElement | null = null;
  let selectionOriginRecordId: string | null = null;
  const searchToggle = writable<HTMLButtonElement | undefined>(undefined);
  const debugOpen = writable(false);
  const debugEnabled = writable(false);
  const initialSelectedId = (() => {
    if (typeof location === "undefined") return null;
    const route = new URLSearchParams(location.hash.split("?")[1] ?? "");
    return route.get("focus") === "selected" ? route.get("selected") : null;
  })();
  let initialSelectionFlightHandled = false;
  const placeSuggestions = writable<readonly PlaceSuggestion[]>([]);
  const placesExpanded = writable(false);
  let searchDraft = $state('');
  let shortQuery = $state(false);
  let searchFocused = $state(false);
  const committedQuery = $derived(mapState.query);
  $effect(() => { searchDraft = committedQuery; });
  const flightTarget = writable<{
    id: number;
    longitude: number;
    latitude: number;
    zoom: number;
  } | null>(null);
  let flightSequence = 0;
  const mapCameraPitch = writable(0);
  const mapControlsReady = writable(false);
  const mapDisplaySettings = writable<MapDisplaySettings>({ clusterMode:'auto', pinScale:.8, optimizedPins:false, coordinateRadius:6.5 });
  const displaySettingsRequest = writable<MapDisplaySettingsRequest | null>(null);
  let displayRequestSequence = 0;
  function changeMapDisplay(patch: Partial<MapDisplaySettings>) {
    displaySettingsRequest.set({ id:++displayRequestSequence, patch });
  }
  function receiveMapDisplaySettings(snapshot: MapDisplaySettings) {
    mapDisplaySettings.set(snapshot);
  }
  let cameraRequestSequence = 0;
  const cameraViewRequest = writable<{ id: number; enable3d: boolean } | null>(null);
  function toggleMapCameraView() {
    cameraViewRequest.set({ id: ++cameraRequestSequence, enable3d: $mapCameraPitch <= 0.5 });
  }
  let placeSearchGeneration = 0;
  let placeSearchModule: Promise<typeof import("../../../features/placeSearch/placeSearch")> | undefined;
  // The gazetteer is lazy and local: typing a place never contacts a geocoder.
  $effect(() => {
    const query = (publicMap && searchFocused ? searchDraft : committedQuery).trim();
    placesExpanded.set(false);
    placeSuggestions.set([]);
    if (!active || (!publicMap && !mapState.listOpen) || query.length < 2 || aggregateOpen) {
      placeSuggestions.set([]);
      return;
    }
    const generation = ++placeSearchGeneration;
    placeSearchModule ??= import("../../../features/placeSearch/placeSearch");
    void placeSearchModule.then(({ searchPlaces }) => {
      if (generation === placeSearchGeneration) {
        placeSuggestions.set(searchPlaces(query, 5));
      }
    }).catch(() => {
      if (generation === placeSearchGeneration) placeSuggestions.set([]);
    });
    return () => { placeSearchGeneration++; };
  });
  let hadSelection = false;
  let activeSelectionId: string | null = null;
  let pendingRailFocusId: string | null = null;
  function selectionSheetSnap(): SheetSnap {
    const expanded = hadSelection && mapState.selectedId
      ? !get(detailMapPreview) && get(detailSheetSnap) === 'expanded'
      : mapState.listOpen && get(resultsSheetSnap) === 'expanded';
    return expanded ? 'expanded' : 'middle';
  }
  $effect(() => {
    if (mapState.selectedId) {
      if (activeSelectionId !== mapState.selectedId) {
        detailSheetSnap.set(selectionSheetSnap());
        detailMapPreview.set(false);
        activeSelectionId = mapState.selectedId;
        pendingRailFocusId = mapState.selectedId;
      }
      hadSelection = true;
      // A Forward navigation can restore the dossier without calling
      // selectRecord again. Keep its row as the dismissal fallback.
      selectionOriginRecordId ??= mapState.selectedId;
      // Wait for evidence loading to finish: the loading and ready rails are
      // separate branches, so focusing the loading close button would leave
      // focus on BODY when that branch is replaced.
      if (pendingRailFocusId === mapState.selectedId && (publicMap || detailStatus !== "loading")) {
        const id = mapState.selectedId;
        void tick().then(() => {
          if (mapState.selectedId === id) {
            const close = publicMap ? mapSummary : document.querySelector<HTMLButtonElement>(".dossier-header .detail-close");
            if (close) {
              close.focus({ preventScroll: true });
              pendingRailFocusId = null;
            }
          }
        });
      }
    } else if (hadSelection) {
      hadSelection = false;
      activeSelectionId = null;
      pendingRailFocusId = null;
      void tick().then(() => {
        const restoredRecord = selectionOriginRecordId
          ? [...document.querySelectorAll<HTMLElement>("[data-record-id]")]
              .find((item) => item.dataset.recordId === selectionOriginRecordId)
          : null;
        const target = selectionOrigin?.isConnected && selectionOrigin.getClientRects().length
          ? selectionOrigin
          : restoredRecord ?? (publicMap ? $searchToggle : matchMedia('(max-width:40rem)').matches ? document.querySelector<HTMLButtonElement>('.mobile-sheet-handle') : $searchToggle);
        const focused = document.activeElement;
        const editingSearch = focused instanceof HTMLElement && focused.isConnected && focused.closest('.search-tools');
        if (!editingSearch) target?.focus();
        selectionOrigin = null;
        selectionOriginRecordId = null;
      });
    }
  });
  function selectRecord(id: string) {
    if (!mapState.selectedId) previousResultsOpen = mapState.listOpen || aggregateOpen;
    detailSheetSnap.set(selectionSheetSnap());
    detailMapPreview.set(false);
    autocompleteOpen.set(false);
    mobileFiltersOpen.set(false);
    selectionOrigin = document.activeElement instanceof HTMLElement && document.activeElement !== document.body
      ? document.activeElement
      : null;
    selectionOriginRecordId = selectionOrigin?.dataset.recordId ?? null;
    dispatch({ type: "select", value: id });
  }
  function flyTo(longitude: number, latitude: number, zoom: number) {
    flightTarget.set({ id: ++flightSequence, longitude, latitude, zoom });
  }
  $effect(() => {
    if (!active || initialSelectionFlightHandled || !initialSelectedId || detailStatus !== "ready" || detailRecord?.id !== initialSelectedId) return;
    initialSelectionFlightHandled = true;
    if (detailRecord.latitude != null && detailRecord.longitude != null) {
      flyTo(detailRecord.longitude, detailRecord.latitude,
        detailRecord.precision === "city" ? 10 : 14);
    }
  });
  function selectSearchRecord(id: string) {
    const record = recordPool.find((item) => item.id === id);
    if (record?.latitude !== null && record?.longitude !== null &&
        record?.latitude !== undefined && record?.longitude !== undefined) {
      // A city reference remains an approximation; do not zoom into a parcel.
      flyTo(record.longitude, record.latitude,
        record.precision === "city" ? 10 : 14);
    }
    selectRecord(id);
  }
  function selectPlace(place: PlaceSuggestion) {
    // Natural Earth supplies a city-centre navigation point, not a facility.
    flyTo(place.longitude, place.latitude, 10);
    if (publicMap) {
      autocompleteOpen.set(false);
      searchDraft = mapState.query;
      document.querySelector<HTMLInputElement>('#field-search')?.blur();
    }
    // Keep the drawer in the hit-test tree until this pointer click finishes.
    // Removing it synchronously can send the tail of the gesture to the map.
    setTimeout(() => dispatch({ type: "list", value: false }), 0);
  }
  function dismissSelection() {
    detailMapPreview.set(false);
    if (publicMap) {
      dispatch({ type: mapState.listOpen || previousResultsOpen ? 'results' : 'close-workspace' });
      return;
    }
    dispatch({ type: "results" });
    if (!previousResultsOpen) dispatch({ type: 'list', value:false });
  }
  function changeMobileSheet(next: SheetSnap) {
    if($mobileFiltersOpen) mobileFiltersOpen.set(false);
    if (mapState.selectedId) {
      detailMapPreview.set(false);
      detailSheetSnap.set(next);
    } else if (next === 'collapsed') collapseMobileSearch();
    else { resultsSheetSnap.set(next); dispatch({ type:'list', value:true }); }
  }
  function openMobileSearch() {
    if ($detailMapPreview && mapState.selectedId) {
      detailMapPreview.set(false);
      detailSheetSnap.set('middle');
      void tick().then(() => document.querySelector<HTMLButtonElement>('.dossier .detail-close')?.focus());
      return;
    }
    if (!mapState.listOpen) resultsSheetSnap.set('middle');
    dispatch({ type: 'list', value: true });
  }
  function openSearchResults() {
    mobileFiltersOpen.set(false);
    const expanded = mapState.selectedId ? get(detailSheetSnap) === 'expanded' : mapState.listOpen && get(resultsSheetSnap) === 'expanded';
    resultsSheetSnap.set(expanded ? 'expanded' : 'middle');
    detailMapPreview.set(false);
    dispatch({type:'results'});
  }
  function collapseMobileSearch() {
    autocompleteOpen.set(false);
    if ($filterDisclosure) $filterDisclosure.open = false;
    dispatch({ type: 'list', value: false });
  }
  function revealOverlapGroup() {
    // Make room for the existing ring without changing selection or camera.
    if (mapState.selectedId) {
      detailMapPreview.set(true);
      detailSheetSnap.set('collapsed');
    } else collapseMobileSearch();
  }
  async function showSelectedOnMap() {
    if (!selected || selected.latitude === null || selected.longitude === null) return;
    const record = selected;
    detailMapPreview.set(true);
    detailSheetSnap.set('collapsed');
    await tick();
    document.querySelector<HTMLButtonElement>(matchMedia('(max-width:40rem)').matches ? '.mobile-sheet-handle' : '.search-toggle')?.focus({ preventScroll: true });
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (mapState.selectedId === record.id && record.longitude !== null && record.latitude !== null) {
        flyTo(record.longitude, record.latitude, record.precision === 'city' ? 10 : 14);
      }
    }));
  }
  function aggregateContextFor(items: readonly LabRecord[]) {
    const mostFrequent = (values: readonly string[]) => {
      const counts = new Map<string, number>();
      for (const value of values) {
        if (value.trim()) counts.set(value, (counts.get(value) ?? 0) + 1);
      }
      return (
        [...counts].sort(
          (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
        )[0]?.[0] ?? null
      );
    };
    const locality = mostFrequent(items.map((item) => item.locality));
    const country = mostFrequent(items.map((item) => item.country));
    const sources = [
      ...new Set(
        items.flatMap((item) => (item.sourceId ? [item.sourceId] : [])),
      ),
    ].sort();
    const precision = new Set(items.map((item) => item.precision));
    const treatment =
      precision.size === 1 && precision.has("city")
        ? "Administrative city reference · approximate, not a facility point"
        : precision.size === 1 && precision.has("coarse")
          ? "Coarse area reference · no approved facility geometry"
          : "Approximate location reference · not a facility pin";
    return {
      locality,
      place:
        [locality, country].filter(Boolean).join(", ") ||
        "Approximate area reference",
      treatment,
      sourceText:
        sources.length === 0
          ? "Source context unavailable"
          : sources.length === 1
            ? sources[0]
            : `${sources.length} source feeds`,
    };
  }
  function closeOverlay() {
    if (mapState.selectedId) {
      dismissSelection();
      return;
    }
    if (aggregateOpen) {
      dispatch({ type: "aggregate", value: null });
      return;
    }
    if (mapState.listOpen) dispatch({ type: "list", value: false });
  }
  function onKeydown(event: KeyboardEvent) {
    if (!active || event.defaultPrevented) return;
    if (document.querySelector('#shared-language-menu, #shared-tools-menu')) return;
    if(event.key==='Escape'&&$mobileFiltersOpen){event.preventDefault();closeMobileFilters();return;}
    if($mobileFiltersOpen)return;
    const target = event.target;
    const editing = target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
    if (event.key === "/" && !editing && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      if (!publicMap) openMobileSearch();
      void tick().then(() => document.querySelector<HTMLInputElement>("#field-search")?.focus());
      return;
    }
    if (event.key === "Escape" && $autocompleteOpen) {
      event.preventDefault(); autocompleteOpen.set(false); return;
    }
    if (event.key === "Escape" && $filterDisclosure?.open) {
      event.preventDefault();
      if ($filterDisclosure) { $filterDisclosure.open = false; $filterDisclosure.querySelector('summary')?.focus(); }
      return;
    }
    if (event.key === 'Escape' && $debugOpen) return;
    if (event.key === "Escape" && (mapState.selectedId || aggregateOpen || mapState.listOpen)) {
      event.preventDefault();
      closeOverlay();
    }
  }
  function browseAggregate() {
    if (!aggregateContext.locality) return;
    dispatch({ type: "aggregate", value: null });
    dispatch({ type: "query", value: aggregateContext.locality });
    dispatch({ type: "list", value: true });
  }
  const databaseHref = $derived(
    (() => {
      const q = new URLSearchParams();
      const navigationViewport = mapState.navigationViewport ?? mapState.viewport;
      if (mode === "real-preview" || mode === "candidate-preview") q.set("f1a", "field");
      if (mode === "public-release" && selectedPublicReleaseId) q.set("release_id", selectedPublicReleaseId);
      if (mapState.sourceId) q.set("source", mapState.sourceId);
      for (const value of mapState.filters.categories) q.append('category', value);
      for (const value of mapState.filters.precisions) q.append('precision', value);
      for (const value of mapState.filters.countries) q.append('country', value);
      for (const value of mapState.filters.sources) q.append('source_filter', value);
      for (const value of mapState.filters.activities) q.append('activity', value);
      if (mapState.selectedId) q.set("selected", mapState.selectedId);
      q.set("lat", String(navigationViewport.centerLat));
      q.set("lon", String(navigationViewport.centerLon));
      q.set("z", String(navigationViewport.zoom));
      if (navigationViewport.pitch) q.set("pitch", String(navigationViewport.pitch));
      if (navigationViewport.bearing) q.set("bearing", String(navigationViewport.bearing));
      if (!mapState.listOpen) q.set("list", "closed");
      if (mapState.basemap !== "vector") q.set("basemap", mapState.basemap);
      return `#/database?${q}`;
    })(),
  );
  const mapHref = $derived(encodeMapNavigationHash(databaseHref, mode === "public-release" ? undefined : mapState.scenario));

  const currentBounds = writable<ViewportBounds | null>(null);
  const autocompleteOpen = writable(false);
  const suggestionIndex = writable(-1);
  const scopeError = writable("");
  const nearbyRadius = writable(25);
  function nearbyRadiusLabel(km: number) {
    return tr('{count} miles', $language).replace('{count}', new Intl.NumberFormat($language).format(Math.round(km / 1.609344)));
  }
  const searchMode = writable<'box' | 'radius'>('box');
  const radiusMiles = writable(50);
  const filterDisclosure = writable<HTMLDetailsElement | undefined>(undefined);
  let beforeFilterSnap: SheetSnap | null = null;
  function filterToggled() {
    if ($filterDisclosure?.open) {
      autocompleteOpen.set(false);
      if ($mobileLayout && beforeFilterSnap === null) {
        beforeFilterSnap = $resultsSheetSnap;
        resultsSheetSnap.set('expanded');
      }
    } else if (beforeFilterSnap !== null) {
      resultsSheetSnap.set(beforeFilterSnap);
      beforeFilterSnap = null;
    }
  }
  const suggestions = $derived([
    ...searchSuggestions(publicMap ? searchDraft : mapState.query, candidateFacets, $language, 5, publicMap),
    ...(publicMap ? $placeSuggestions.slice(0, 3) : []),
  ].slice(0, 8));
  const countries = $derived(new Intl.DisplayNames([$language], { type: 'region' }));
  function countryName(value: string) { try { return countries.of(value) ?? value; } catch { return value; } }
  function sourceName(value: string) { return candidateFacets?.sources.find(facet => facet.value === value)?.label ?? value; }
  const shortCategoryLabels: Readonly<Record<string,string>> = { animal_keeping_and_production:'Animal keeping', slaughter:'Slaughter', processing_and_preparation:'Processing', research_and_animal_use:'Research', other_regulated_premises:'Other premises', unclassified:'Unclassified' };
  function categoryName(value: string) { return tr(shortCategoryLabels[value] ?? (value in CATEGORY_PRESENTATIONS ? CATEGORY_PRESENTATIONS[value as keyof typeof CATEGORY_PRESENTATIONS].label : value), $language); }
  function removeFilter(field: keyof LabFilters, value: string) {
    dispatch({ type: 'filters', value: { ...mapState.filters, [field]: mapState.filters[field].filter(item => item !== value) } });
    dispatch({ type: 'results' });
  }
  function applyParsedSearch() {
    const parsed = parseSearch(publicMap ? searchDraft : mapState.query, mapState.filters, candidateFacets, $language, publicMap);
    if (parsed.filters.countries !== mapState.filters.countries && mapState.searchScope?.kind === 'state' && !parsed.scope) parsed.scope = null;
    submitSearch(parsed);
  }
  function submitSearch(selection: ReturnType<typeof parseSearch>) {
    if (publicMap && selection.query && !canSearchRecords(selection.query)) {
      shortQuery = true;
      return;
    }
    shortQuery = false;
    if (publicMap && (selection.scope?.kind === 'state' || (selection.filters.countries !== mapState.filters.countries && selection.filters.countries.length))) fitResultsRequest += 1;
    mobileFiltersOpen.set(false);
    detailMapPreview.set(false);
    dispatch({ type: 'search', value: selection });
    searchDraft = selection.query;
    autocompleteOpen.set(false);
    if (publicMap) document.querySelector<HTMLInputElement>('#field-search')?.blur();
  }
  function applySuggestion(suggestion: SearchSuggestion | PlaceSuggestion) {
    if (suggestion.kind === 'place') selectPlace(suggestion);
    else submitSearch(applySearchSuggestion(suggestion, mapState.filters, candidateFacets, $language));
  }
  function editSearch(value: string) {
    searchDraft = value;
    shortQuery = false;
    autocompleteOpen.set(true);
    suggestionIndex.set(-1);
    if (!publicMap) dispatch({ type: 'search', value: { query: value, filters: mapState.filters } });
  }
  function clearSearchInput() {
    editSearch('');
    if (mapState.query) submitSearch({ query: '', filters: mapState.filters });
    void tick().then(() => document.querySelector<HTMLInputElement>('#field-search')?.focus());
  }
  function clearSearch() {
    dispatch({ type: 'reset-filters' });
    dispatch({ type: 'results' });
    autocompleteOpen.set(false);
  }
  function chooseSource(value: string | null) {
    dispatch({ type: 'source', value });
    dispatch({ type: 'results' });
  }
  function closeWorkspace() {
    mobileFiltersOpen.set(false);
    autocompleteOpen.set(false);
    shortQuery = false;
    scopeError.set('');
    detailMapPreview.set(false);
    dispatch({ type: 'close-workspace' });
  }
  function searchArea() {
    if(mapState.searchScope) { clearMapArea(); return; }
    if ($searchMode === 'radius') runRadiusSearch();
    else updateSearchArea();
  }
  function clearMapArea() {
    const focused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const fromFilter = Boolean(focused?.closest('.scope-filter'));
    const fromChip = Boolean(focused?.closest('.scope-chip'));
    scopeError.set(''); dispatch({type:'scope',value:null,preserveWorkspace:true});
    if(fromFilter || fromChip) void tick().then(() => document.querySelector<HTMLElement>(fromFilter ? '.filters > summary' : publicMap ? '#field-search' : '.map-navigation .area-button')?.focus({preventScroll:true}));
  }
  function runRadiusSearch() {
    openSearchResults();
    const prior = mapState.searchScope?.kind === 'radius' ? mapState.searchScope : null;
    dispatch({type:'scope',value:{kind:'radius', label:prior?.label ?? 'This map area',
      latitude:prior?.latitude ?? mapState.viewport.centerLat, longitude:prior?.longitude ?? mapState.viewport.centerLon,
      radiusKm:$radiusMiles * 1.609344, ...(prior?.deviceDerived ? {deviceDerived:true} : {})}});
    dispatch({type:'results'});
  }
  function openMobileFilters() {
    if(mode!=='public-release'){if($filterDisclosure)$filterDisclosure.open=true;return;}
    autocompleteOpen.set(false);
    mobileFiltersOpen.set(!$mobileFiltersOpen);
    if ($mobileFiltersOpen) void tick().then(()=>document.querySelector<HTMLButtonElement>('.mobile-filter-view header button')?.focus({preventScroll:true}));
  }
  function closeMobileFilters() {
    mobileFiltersOpen.set(false);
    document.querySelector<HTMLButtonElement>('.public-filter-button')?.focus({preventScroll:true});
  }
  function applyMobileFilters(value:{filters:LabFilters;sourceId:string|null}) {
    if(value.sourceId!==mapState.sourceId)dispatch({type:'source',value:value.sourceId});
    const clearState = mapState.searchScope?.kind === 'state' && value.filters.countries.length > 0;
    dispatch({type:'search',value:{query:mapState.query,filters:value.filters,...(clearState ? {scope:null} : {})}});
    closeMobileFilters();
  }
  const mobileScopeLabel = $derived.by(() => {
    const scope = mapState.searchScope;
    if (!scope) return tr('Everywhere', $language);
    if (scope.kind === 'state') return stateSearchName(scope.code) ?? scope.code;
    if (scope.kind === 'area') return tr('This map area', $language);
    return `${scope.deviceDerived ? tr('Near me', $language) : scope.label} · ${nearbyRadiusLabel(scope.radiusKm)}`;
  });
  const retainedFilterCount=$derived(mapState.filters.categories.length+mapState.filters.countries.length+mapState.filters.sources.length+(mapState.sourceId?1:0));
  function searchSettings(value: {mode:'box'|'radius';radiusMiles:number}) {
    searchMode.set(value.mode); radiusMiles.set(value.radiusMiles);
    if (!mapState.searchScope) return;
    if(value.mode === 'radius') runRadiusSearch(); else updateSearchArea();
  }
  function updateSearchArea() {
    if (!$currentBounds) return;
    const scope = areaScopeFromBounds($currentBounds);
    if (!scope) { scopeError.set(tr('This map area crosses the date line. Zoom in and try again.', $language)); return; }
    scopeError.set('');
    openSearchResults();
    dispatch({ type: 'scope', value: scope });
    dispatch({ type:'results' });
  }
  function summaryCategory(key: TaxonomyPrimaryKey) {
    openSearchResults();
    const categories = mapState.filters.categories.length === 1 && mapState.filters.categories[0] === key ? [] : [key];
    dispatch({ type:'filters', value:{ ...mapState.filters, categories } });
  }
  function searchNear(place: PlaceSuggestion) {
    openSearchResults();
    scopeError.set('');
    dispatch({ type: 'search', value: { query: '', filters: mapState.filters } });
    dispatch({ type: 'scope', value: { kind: 'radius', label: place.label, latitude: place.latitude, longitude: place.longitude, radiusKm: $nearbyRadius } });
    dispatch({ type: 'results' });
    flyTo(place.longitude, place.latitude, 10);
    autocompleteOpen.set(false);
  }

</script>

<svelte:window onkeydown={onKeydown} />
{#snippet searchInput()}
          <form class="search" role="search" onsubmit={(event) => { event.preventDefault(); applyParsedSearch(); }}>
            <div class="query-box">
            <label for="field-search">{tr(mode === "public-release" ? 'Search across public release records' : 'Search across preview records', $language)}</label>
            {#if publicMap || !$mobileLayout}<button class="search-toggle" bind:this={$searchToggle} type={publicMap ? 'submit' : 'button'} aria-label={tr($detailMapPreview ? 'View facility details' : 'Search map', $language)} aria-controls="field-record-list" onclick={publicMap ? undefined : openMobileSearch}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg></button>{:else}<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg>{/if}
            <input id="field-search" type="search" role="combobox" aria-autocomplete="list" aria-haspopup="listbox" maxlength="120" enterkeyhint="search" placeholder={tr(publicMap || !workspaceOpen ? 'Search map' : 'Name, activity, source, or place', $language)}
              value={publicMap ? searchDraft : mapState.query} aria-invalid={shortQuery || undefined} aria-describedby={shortQuery ? 'search-query-hint' : undefined} aria-activedescendant={$autocompleteOpen && suggestions[$suggestionIndex] ? `field-suggestion-${$suggestionIndex}` : undefined} aria-expanded={$autocompleteOpen && !shortQuery && suggestions.length > 0} aria-controls={$autocompleteOpen && !shortQuery && suggestions.length > 0 ? 'search-suggestions' : undefined} onfocus={() => { searchFocused = true; if (!publicMap && mapState.selectedId) openSearchResults(); else if (!publicMap && !$mobileLayout) openMobileSearch(); autocompleteOpen.set(true); suggestionIndex.set(-1); }} onblur={(event) => { searchFocused = false; if (!(event.relatedTarget instanceof HTMLElement) || !event.relatedTarget.closest('.search-autocomplete')) autocompleteOpen.set(false); }} oninput={(event) => editSearch(event.currentTarget.value)} onkeydown={(event) => {
                if (event.isComposing) return;
                if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && suggestions.length) { event.preventDefault(); autocompleteOpen.set(true); suggestionIndex.update(index => index === -1 ? (event.key === 'ArrowDown' ? 0 : suggestions.length - 1) : (index + (event.key === 'ArrowDown' ? 1 : -1) + suggestions.length) % suggestions.length); }
                if (event.key === 'Enter' && $autocompleteOpen && suggestions[$suggestionIndex]) { event.preventDefault(); applySuggestion(suggestions[$suggestionIndex]!); }
              }} />
            {#if publicMap && searchDraft}<button class="mobile-clear-query" type="button" aria-label={tr('Clear search',$language)} onclick={clearSearchInput}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>{/if}
            </div>
          </form>
          {#if shortQuery}<p class="search-autocomplete query-hint" id="search-query-hint" role="status">{tr('Enter at least 3 letters or numbers.', $language)}</p>
          {:else if $autocompleteOpen && suggestions.length > 0}<div id="search-suggestions" class="search-autocomplete" role="listbox" aria-label={tr('Search suggestions', $language)}>
            {#each suggestions as suggestion, index (`${suggestion.kind}:${suggestion.kind === 'place' ? suggestion.id : suggestion.value}`)}
              <button id={`field-suggestion-${index}`} role="option" aria-selected={$suggestionIndex === index} tabindex="-1" type="button" onpointerdown={(event) => event.preventDefault()} onclick={() => applySuggestion(suggestion)}><strong>{suggestion.label}</strong><small>{tr(suggestion.kind === 'country' ? 'Country' : suggestion.kind === 'state' ? 'State' : suggestion.kind === 'place' ? 'City' : suggestion.kind === 'category' ? 'Category' : 'Source', $language)}</small></button>
            {/each}
          </div>{/if}

{/snippet}
{#snippet mapTools()}
  {#if publicMap}
    <section class="map-tool-settings">
      <label>{tr('Map style', $language)}
        <select aria-label={tr('Map style', $language)} value={mapStyle === 'automatic' && mapState.basemap === 'satellite' ? 'satellite' : mapStyle} onchange={(event) => {
          const value = event.currentTarget.value as typeof mapStyle;
          mapStyle = value;
          if (value !== 'automatic') dispatch({ type: 'basemap', value });
          else if (mapState.basemap === 'satellite') dispatch({ type: 'basemap', value: 'vector' });
        }}>
          <option value="automatic">{tr('Automatic', $language)}</option>
          <option value="vector">{tr('Street', $language)}</option>
          <option value="satellite">{tr('Satellite', $language)}</option>
        </select>
      </label>
      <label>{tr('Search area', $language)}
        <select aria-label={tr('Search area', $language)} value={$searchMode} onchange={(event) => searchSettings({ mode: event.currentTarget.value === 'radius' ? 'radius' : 'box', radiusMiles: $radiusMiles })}>
          <option value="box">{tr('Visible map', $language)}</option>
          <option value="radius">{tr('Radius', $language)}</option>
        </select>
      </label>
      {#if $searchMode === 'radius'}<label>{tr('Radius', $language)}
        <input type="number" min="5" max="250" step="5" value={$radiusMiles} onchange={(event) => {
          const value = event.currentTarget.valueAsNumber;
          if (Number.isFinite(value)) searchSettings({ mode: 'radius', radiusMiles: Math.max(5, Math.min(250, value)) });
        }} />
      </label>{/if}
      <button type="button" disabled={!$mapControlsReady || !$currentBounds} onclick={searchArea}>{tr(mapState.searchScope ? 'Clear map area' : 'Search this area', $language)}</button>
      <button type="button" disabled={!$mapControlsReady || locating} onclick={locateFromTools}>{tr(locating ? 'Finding your location…' : 'Your location', $language)}</button>
      {#if locationError}<small role="alert">{tr(locationError, $language)}</small>{/if}
    </section>
  {/if}
{/snippet}
<section class="field-view">
  {#if active}<PreviewMasthead privateTools={mode === "real-preview" || mode === "candidate-preview"} publicReleaseLabel={mode === "candidate-preview" ? $candidatePreviewLabel : publicReleaseLabel(publicMapMeta?.releaseId, publicMapMeta?.releaseLabel)} releaseDescription={mode === "candidate-preview" && $candidatePreviewLabel ? 'Configured private candidate release.' : null} {releaseOptions} selectedReleaseId={mode === "public-release" ? selectedPublicReleaseId : null} {...(onreleasechange ? { onreleasechange } : {})} current="map" {mapHref} {databaseHref} debugEnabled={$debugEnabled} ondebugchange={(enabled) => { debugEnabled.set(enabled); if (!enabled) debugOpen.set(false); }} mapControlsReady={$mapControlsReady} mapDisplaySettings={$mapDisplaySettings} onmapdisplaychange={changeMapDisplay} {mapTools} />{/if}
  <div class="workspace" use:measureWorkspace class:public-map={publicMap} class:workspace-open={workspaceOpen && !detailCollapsed} class:detail-active={showingDetail} class:debug-active={$debugOpen} class:mobile-discovery={$mobileLayout&&mode==='public-release'} style:--mobile-sheet-height={`${$sheetHeight}px`} style:--visual-workspace-height={`${$workspaceHeight}px`} style:--workspace-width={$railWidth === null ? `${$layoutTuning.panelWidthPercent}vw` : `${$railWidth}px`} style:--result-row-padding={`${$layoutTuning.rowPadding}px`} style:--result-type-scale={$layoutTuning.typeScale}>
    <main class="map-stage" aria-label={tr('Investigative map field', $language)}>
    {#if mode === "synthetic" && mapState.scenario === "loading"}<div class="status" role="status">
        {tr('Loading records…', $language)}
      </div>{:else if mode === "synthetic" && mapState.scenario === "error"}<div
        class="status"
        role="alert"
      >
        {tr('Records unavailable. No live fallback was attempted.', $language)}
      </div>{:else}<MapSurface
        {active}
        records={mapped}
        state={mapState}
        {automaticBasemap}
        {popupLocation}
        onPopupAnchor={(point) => { popupAnchor = point; }}
        {mode}
        {publicReleaseId}
        {publicReleaseIdentity}
        {publicReleaseManifestIdentity}
        {onMapFeedMeta}
        {...(resolvePinHover ? { resolvePinHover } : {})}
        onCandidatePreviewLabel={(label) => { candidatePreviewLabel.set(label); onCandidatePreviewLabel?.(label); }}
        {mapStatus}
        {mapError}
        {mapTruncated}
        {mapDiagnostics}
        {mapMatchingIds}
        {mapMatchesStatus}
        {mapMatchesError}
        {mapMatchesSearchKey}
        onAreaSummary={(summary) => { areaSummary.set(summary); }}
        {fitResultsRequest}
        searchScope={mapState.searchScope}
        flightTarget={$flightTarget}
        cameraViewRequest={$cameraViewRequest}
        displaySettingsRequest={$displaySettingsRequest}
        onDisplaySettingsChange={receiveMapDisplaySettings}
        onCameraPitchChange={(pitch) => { mapCameraPitch.set(pitch); }}
        onMapControlsReady={(ready) => { mapControlsReady.set(ready); }}
        debugEnabled={$debugEnabled}
        layoutTuning={$layoutTuning}
        onLayoutTuningChange={updateLayoutTuning}
        onLayoutTuningReset={resetLayoutTuning}
        searchDiagnostics={{ total: candidateTotalCount, shown: resultCount, listStatus: dataStatus, matchesStatus: mapMatchesStatus, matchingMappedCount: mapMatchingIds?.length ?? null, scope: mapState.searchScope?.kind ?? null }}
        referenceLoading={aggregateLoading}
        onmaptiming={(timing) => onMapTiming?.(timing)}
        onselect={selectRecord}
        onrevealoverlap={revealOverlapGroup}
        onaggregate={(ids) => dispatch({ type: "aggregate", value: ids })}
        onreference={(key, sourceId) => onMapReference?.(key, sourceId)}
        onbasemap={(value) => {
          if (publicMap && !automaticBasemap) mapStyle = value === 'satellite' ? 'satellite' : 'vector';
          dispatch({ type: "basemap", value });
        }}
        ondebugopenchange={(open) => debugOpen.set(open)}
        onviewport={(value) => dispatch({ type: "viewport", value })}
        onbounds={(bounds) => { currentBounds.set(bounds); onViewportBounds?.(bounds); }}
      />{/if}
    {#if mode === 'public-release' && dataStatus === 'error' && !workspaceOpen && !mapState.selectedId}<div class="search-recovery" role="alert"><span>{tr('Search unavailable', $language)}</span>{#if onRetrySearch}<button type="button" disabled={listRefreshing} onclick={onRetrySearch}>{tr('Retry', $language)}</button>{/if}</div>{/if}
    {#if (mode === "synthetic" && (mapState.scenario === "empty" || (mapState.scenario !== "loading" && mapState.scenario !== "error" && records.length === 0))) || (mode !== "synthetic" && dataStatus === "empty")}<div
        class="status"
        role="status"
      >
        {tr('No records match this search and these filters.', $language)}
      </div>{/if}
    {#if mode !== "synthetic" && dataStatus === "error" && mode !== "public-release"}<div
        class="status"
        role="alert"
      >
        {dataError}
      </div>{:else if mode !== "synthetic" && dataStatus === "unauthorized"}<div
        class="status"
        role="alert"
      >
        {dataError}
      </div>{/if}
    {#if active && publicMap && mapState.selectedId}
      <section class="map-summary" class:map-summary-anchored={popupTop !== null} class:map-summary-below={popupBelow}
        bind:this={mapSummary} bind:offsetHeight={popupHeight} tabindex="-1" aria-label={tr('Location', $language)}
        style:--popup-x={`${popupLeft}px`} style:--popup-y={popupTop === null ? undefined : `${popupTop}px`}
        style:--popup-arrow={popupAnchor ? `clamp(12px, calc(50% + ${popupAnchor.x - popupLeft}px), 100% - 12px)` : undefined}>
        <button class="summary-close" type="button" aria-label={tr('Close record detail', $language)} onclick={dismissSelection}>×</button>
        {#if detailStatus === 'error' || detailStatus === 'unauthorized'}
          <p role="alert">{tr(detailError, $language)}</p>
        {:else if selected?.id === mapState.selectedId}
          <strong>{recordNamePresentation(selected, label => tr(label, $language))}</strong>
          <p>{[categoryName(selected.category), selected.locality, selected.country ? countryName(selected.country) : ''].filter(Boolean).join(' · ')}</p>
          {#if popupSource}<p class="summary-source" title={popupSource}>{popupSource}</p>{/if}
          <p>{tr(precisionPresentation(selected.precision), $language)}</p>
        {:else}
          <p role="status">{tr('Loading record…', $language)}</p>
        {/if}
        <a href={serializeRoute({ kind: 'record', facilityId: mapState.selectedId, profile: 'official', ...(publicReleaseId ? { releaseId: publicReleaseId } : {}), returnMapHref: mapHref })}>{tr('View full record', $language)}</a>
        {#if mapState.listOpen || previousResultsOpen}<button class="summary-back" type="button" onclick={dismissSelection}>{tr('Back to results', $language)}</button>{/if}
      </section>
    {/if}
    </main>
    <div class="map-tool-shell">
      <div class="map-toolbar" class:toolbar-hidden={!publicMap && $mobileLayout && $workspaceHeight - $sheetHeight < 100}>
        <div class="desktop-search search-tools">{#if publicMap || !$mobileLayout}{@render searchInput()}{/if}</div>
      {#if publicMap}<button class="public-filter-button" type="button" aria-expanded={$mobileFiltersOpen} aria-controls="public-map-filters" onclick={openMobileFilters}>{tr('Filters', $language)}{#if retainedFilterCount} <span>{retainedFilterCount}</span>{/if}</button>{/if}
      {#if active && !publicMap}<MapNavigation ready={$mapControlsReady} basemap={mapState.basemap} pitch={$mapCameraPitch} onbasemap={(value) => dispatch({type:'basemap',value})} onviewtoggle={toggleMapCameraView} />{/if}
      </div>
    {#if publicMap && $mobileFiltersOpen}<div class="public-filter-panel" id="public-map-filters"><MobileSearchFilters filters={mapState.filters} sourceId={mapState.sourceId} facets={candidateFacets} {facetsStatus} onapply={applyMobileFilters} onclose={closeMobileFilters}/></div>{/if}
    <aside class="results" inert={$debugOpen && $mobileLayout} aria-hidden={$debugOpen && $mobileLayout ? true : undefined} class:rail-collapsed={!workspaceOpen} class:map-preview={detailCollapsed} class:behind-filters={publicMap && $mobileFiltersOpen} class:typing={publicMap && searchFocused} style:--results-height={$resultsSheetSnap === 'expanded' ? '88%' : '55%'} id="field-record-list" aria-label={tr('Search, filters, and results', $language)}>
      {#if !publicMap}<div class="mobile-sheet-control"><MobileSearchSheet open={workspaceOpen && !detailCollapsed} snap={mapState.selectedId ? $detailSheetSnap : $resultsSheetSnap} detail={Boolean(mapState.selectedId)} preview={Boolean(mapState.selectedId)} available={$workspaceHeight} middlePercent={$layoutTuning.mobileSheetPercent ?? 60} expandedPercent={$layoutTuning.mobileExpandedPercent ?? 90} onchange={changeMobileSheet} onheight={height => sheetHeight.set(height)} /></div>{/if}
      <button class="rail-resize" type="button" aria-label={tr('Resize search panel', $language)} title={tr('Use left and right arrows to resize', $language)} onpointerdown={resizeRail} onkeydown={resizeRailKey}></button>
      <header hidden={Boolean(mapState.selectedId) || !workspaceOpen}><strong>{tr('Search records', $language)}</strong><button type="button" aria-label={tr('Close workspace', $language)} onclick={closeWorkspace}>×</button></header>
        <div class="search-tools" id="field-search-content" hidden={Boolean(mapState.selectedId) || !workspaceOpen || $mobileFiltersOpen}>
          {#if publicMap && (mapState.searchScope || retainedFilterCount)}
            <div class="public-scope filter-chips" aria-label={tr('Search filters', $language)}>
              {#if mapState.searchScope}<button class="scope-chip" type="button" aria-label={`${tr('Clear map area', $language)}: ${mobileScopeLabel}`} onclick={clearMapArea}>{mobileScopeLabel} <span aria-hidden="true">×</span></button>{/if}
              {#each mapState.filters.countries as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${countryName(value)}`} onclick={() => removeFilter('countries', value)}>{countryName(value)} <span aria-hidden="true">×</span></button>{/each}
              {#each mapState.filters.categories as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${categoryName(value)}`} onclick={() => removeFilter('categories', value)}>{categoryName(value)} <span aria-hidden="true">×</span></button>{/each}
              {#each mapState.filters.sources as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${sourceName(value)}`} onclick={() => removeFilter('sources', value)}>{sourceName(value)} <span aria-hidden="true">×</span></button>{/each}
              {#if mapState.sourceId}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${sourceName(mapState.sourceId)}`} onclick={() => chooseSource(null)}>{sourceName(mapState.sourceId)} <span aria-hidden="true">×</span></button>{/if}
            </div>
          {/if}
          {#if $mobileLayout && !publicMap}{@render searchInput()}{/if}
          {#if !publicMap}
          <div class="filter-chips" aria-label={tr('Search filters', $language)}>
            {#each mapState.filters.countries as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${countryName(value)}`} onclick={() => removeFilter('countries', value)}>{countryName(value)} <span aria-hidden="true">×</span></button>{/each}
            {#each mapState.filters.categories as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${categoryName(value)}`} onclick={() => removeFilter('categories', value)}>{categoryName(value)} <span aria-hidden="true">×</span></button>{/each}
            {#each mapState.filters.sources as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${sourceName(value)}`} onclick={() => removeFilter('sources', value)}>{sourceName(value)} <span aria-hidden="true">×</span></button>{/each}
            {#each mapState.filters.precisions as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${tr(value, $language)}`} onclick={() => removeFilter('precisions', value)}>{tr(value, $language)} <span aria-hidden="true">×</span></button>{/each}
            {#each mapState.filters.activities as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${value}`} onclick={() => removeFilter('activities', value)}>{value} <span aria-hidden="true">×</span></button>{/each}
            {#if mapState.sourceId}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${sourceName(mapState.sourceId)}`} onclick={() => chooseSource(null)}>{sourceName(mapState.sourceId)} <span aria-hidden="true">×</span></button>{/if}
          </div>
          <div class="search-toolbar">
          <details class="filters" bind:this={$filterDisclosure} ontoggle={filterToggled}>
            <summary><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h7m5 0h4M4 17h3m5 0h8M11 4v6M7 14v6"/></svg>{tr('Filters', $language)} {#if activeFilters}<b>{activeFilters}</b>{/if}</summary>
            <div class="filter-sheet" use:fitFilterViewport><div class="filter-scroll">
              {#if mapState.searchScope}<fieldset class="scope-filter"><legend>{tr('Search area', $language)}</legend><label><input type="checkbox" checked onchange={clearMapArea} />{tr('This map area', $language)}</label></fieldset>{/if}
              {#if mode === "candidate-preview"}
                {#if facetsStatus === "loading"}<small>{tr('Loading filters…', $language)}</small>
                {:else if facetsStatus === "error" || facetsStatus === "unauthorized"}<small role="alert">{tr('Filters are unavailable. Search remains available.', $language)}</small>
                {:else if candidateFacets}
                  <details class="filter-choice"><summary><span>{tr('Country', $language)}</span><span class="choice-value">{mapState.filters.countries.length ? mapState.filters.countries.map(countryName).join(', ') : tr('All countries', $language)}</span></summary><fieldset aria-label="{tr('Country', $language)}">{#each candidateFacets.countries as facet (facet.value)}<label><input type="checkbox" checked={mapState.filters.countries.includes(facet.value)} onchange={(event) => toggleCandidateFilter('countries', facet.value, event.currentTarget.checked)} />{countryName(facet.value)} ({facet.count})</label>{/each}</fieldset></details>
                  <details class="filter-choice"><summary><span>{tr('Source', $language)}</span><span class="choice-value">{mapState.filters.sources.length ? mapState.filters.sources.map(sourceName).join(', ') : tr('All sources', $language)}</span></summary><fieldset aria-label="{tr('Source', $language)}">{#each candidateFacets.sources as facet (facet.value)}<label><input type="checkbox" checked={mapState.filters.sources.includes(facet.value)} onchange={(event) => toggleCandidateFilter('sources', facet.value, event.currentTarget.checked)} />{facet.label ?? facet.value} ({facet.count})</label>{/each}</fieldset></details>
                  <fieldset><legend>{tr('Activity category', $language)}</legend>{#each candidateFacets.categories as facet (facet.value)}<label><input type="checkbox" checked={mapState.filters.categories.includes(facet.value)} onchange={(event) => toggleCandidateFilter('categories', facet.value, event.currentTarget.checked)} />{facet.value in CATEGORY_PRESENTATIONS ? categoryName(facet.value) : tr(classificationLabel(facet.label ?? facet.value), $language)} ({facet.count})</label>{/each}</fieldset>
                  {#if candidateFacets.activities.length}<details class="filter-choice"><summary>{tr('Activity', $language)}</summary><fieldset aria-label="{tr('Activity', $language)}">{#each candidateFacets.activities as facet (facet.value)}<label><input type="checkbox" checked={mapState.filters.activities.includes(facet.value)} onchange={(event) => toggleCandidateFilter('activities', facet.value, event.currentTarget.checked)} />{tr(classificationLabel(facet.label ?? facet.value), $language)} ({facet.count})</label>{/each}</fieldset></details>{/if}
                {/if}
              {:else if mode === "real-preview"}
                <fieldset class="source-filter">
                  <legend>{tr('Source', $language)}</legend>
                  {#if facetsStatus === "loading"}<small>{tr('Loading sources…', $language)}</small>
                  {:else if facetsStatus === "error" || facetsStatus === "unauthorized"}<small role="alert">{tr('Sources unavailable. Search remains available.', $language)}</small>
                  {:else}
                    <label><input type="radio" name="source" checked={mapState.sourceId === null} onchange={() => chooseSource(null)} />{tr('All sources', $language)}</label>
                    {#each sources as value}<label><input type="radio" name="source" checked={mapState.sourceId === value} onchange={() => chooseSource(value)} />{value}</label>{/each}
                  {/if}
                </fieldset>
              {:else}
                <p class="category-key"><i class="poultry"></i>Poultry <i class="pig"></i>Pig <i class="dairy"></i>Dairy <i class="processing"></i>Processing <i class="laboratory"></i>Lab <i class="aquaculture"></i>Aquaculture</p>
                <fieldset><legend>{tr('Category', $language)}</legend>{#each categories as value}<label><input type="checkbox" checked={mapState.filters.categories.includes(value)} onchange={(event) => category(value, event.currentTarget.checked)} />{value}</label>{/each}</fieldset>
                <fieldset><legend>{tr('Location precision', $language)}</legend>{#each precisions as value}<label><input type="checkbox" checked={mapState.filters.precisions.includes(value)} onchange={(event) => precision(value, event.currentTarget.checked)} />{value}</label>{/each}</fieldset>
              {/if}
              </div><footer class="filter-actions"><button type="button" class="clear-filters" onclick={clearSearch}>{tr('Clear filters', $language)}</button><button type="button" class="show-results" onclick={() => { if ($filterDisclosure) $filterDisclosure.open = false; }}>{tr('Show results', $language)}</button></footer>
            </div>
          </details>
          {#if mapState.searchScope}<button class="scope-chip" type="button" aria-label={`${tr('Remove filter', $language)}: ${tr('This map area', $language)}`} onclick={clearMapArea}><span>{tr('This map area', $language)}</span><span aria-hidden="true">×</span></button>{/if}
          <div class="result-status"><strong class="sr-only">{tr(aggregateOpen ? 'Members' : 'Facility records', $language)}</strong><span role="status" aria-live="polite">{!aggregateOpen && listRefreshing ? tr(resultCount ? 'Searching · showing previous results' : 'Searching…', $language) : !aggregateOpen && (dataStatus === 'error' || dataStatus === 'unauthorized') && resultCount ? tr('Search unavailable · showing previous results', $language) : !aggregateOpen && (mode === 'candidate-preview' || mode === 'public-release') && candidateTotalCount !== null ? tr('{count} matching records · {shown} shown', $language).replace('{count}', new Intl.NumberFormat($language).format(candidateTotalCount)).replace('{shown}', new Intl.NumberFormat($language).format(resultCount)) : tr('{count} records loaded', $language).replace('{count}', new Intl.NumberFormat($language).format(resultCount))}</span></div>
          </div>
          {/if}
          {#if $mobileLayout&&mode==='public-release'}<div class="mobile-results-heading"><strong role="status" aria-live="polite">{listRefreshing?tr(resultCount?'Searching · showing previous results':'Searching…',$language):tr((candidateTotalCount??resultCount)===1?'{count} record':'{count} records',$language).replace('{count}',new Intl.NumberFormat($language).format(candidateTotalCount??resultCount))}</strong><span class="sr-only">{tr('{count} matching records · {shown} shown',$language).replace('{count}',new Intl.NumberFormat($language).format(candidateTotalCount??resultCount)).replace('{shown}',new Intl.NumberFormat($language).format(resultCount))}</span><button type="button" aria-label={tr($resultsSheetSnap==='expanded'?'Show fewer results':'Expand search panel',$language)} onclick={()=>resultsSheetSnap.set($resultsSheetSnap==='expanded'?'middle':'expanded')}>{$resultsSheetSnap==='expanded'?tr('Show fewer results',$language):tr('Expand',$language)}<svg viewBox="0 0 24 24" aria-hidden="true"><path d={$resultsSheetSnap==='expanded'?'m6 9 6 6 6-6':'m6 15 6-6 6 6'}/></svg></button></div>{/if}
        </div>
      {#if $scopeError}<p class="search-error" hidden={Boolean(mapState.selectedId) || !workspaceOpen} role="alert">{$scopeError}</p>{/if}
      {#if publicMap && !$mobileLayout && !mapState.selectedId && workspaceOpen}
        <div class="public-results-heading" role="status">{listRefreshing ? tr('Searching…', $language) : tr('{count} records', $language).replace('{count}', new Intl.NumberFormat($language).format(candidateTotalCount ?? resultCount))}</div>
      {/if}
      {#if mapMatchesStatus === 'error' && dataStatus !== 'error'}<p class="search-error" hidden={Boolean(mapState.selectedId) || !workspaceOpen} role="alert">{mapMatchesError} {#if onRetryMapMatches}<button type="button" onclick={() => onRetryMapMatches?.()}>{tr('Retry', $language)}</button>{/if}</p>{/if}
      {#if !aggregateOpen && mode !== "synthetic" && (dataStatus === "unauthorized" || dataStatus === "error")}<p class="search-error search-list-recovery" hidden={Boolean(mapState.selectedId) || !workspaceOpen || $mobileFiltersOpen} role="alert"><span>{mode === 'public-release' ? tr(resultCount ? 'Search unavailable · showing previous results' : 'Search unavailable', $language) : tr(dataError, $language)}</span>{#if onRetrySearch}<button type="button" disabled={listRefreshing} onclick={onRetrySearch}>{tr('Retry', $language)}</button>{/if}</p>{/if}
      <div class="workspace-body" id="field-detail-content" hidden={$mobileFiltersOpen}>
        <div class="list-content" hidden={Boolean(mapState.selectedId) || !workspaceOpen}>
        {#if !$mobileLayout&&mode === 'public-release' && mapState.searchScope && !aggregateOpen}<AreaSummary summary={$areaSummary} selectedCategories={mapState.filters.categories} nearby={mapState.searchScope.kind === 'radius' && Boolean(mapState.searchScope.deviceDerived)} radiusKm={mapState.searchScope.kind === 'radius' ? mapState.searchScope.radiusKm : null} oncategory={summaryCategory} />{/if}
{#if aggregateOpen}<details
        class="reading-sheet aggregate-sheet"
        aria-labelledby="aggregate-title"
      ><summary>{aggregateContext.place}</summary>
        <button
          type="button"
          class="close"
          aria-label="Close aggregate and return to map"
          onclick={() => dispatch({ type: "aggregate", value: null })}>×</button
        >
        <p class="eyebrow">PRIVATE PREVIEW / MAP REFERENCE</p>
        <p class="aggregate-source">{aggregateContext.sourceText}</p>
        <h2 id="aggregate-title">{aggregateContext.place}</h2>
        <p class="place">{aggregateContext.treatment}</p>
        <dl>
          <div>
            <dt>Mapped members</dt>
            <dd>{aggregateRequestedCount}</dd>
          </div>
          <div>
            <dt>Loaded here</dt>
            <dd>{resultCount} records</dd>
          </div>
          <div>
            <dt>Member access</dt>
            <dd>Bounded to this map response</dd>
          </div>
        </dl>
        <p class="evidence-note">
          Use the Members panel to inspect the loaded records. Selecting a
          member opens its own evidence record.
        </p>
        {#if aggregateContext.locality}<p class="continuation-note">
            This preview has no reference-specific member cursor. Continue
            through the global, paginated search for this locality.
          </p>
          <button
            class="continue-members"
            type="button"
            onclick={browseAggregate}
            >Search all records for {aggregateContext.locality}</button
          >{:else}<p class="continuation-note">
            This preview has no reference-specific member cursor. Only the
            bounded map response is available here.
          </p>{/if}<button
          class="open-members"
          type="button"
          onclick={() => dispatch({ type: "list", value: true })}
          >Open member records</button
        >
      </details>{/if}
        {#if $placeSuggestions.length > 0}
          <section class="place-suggestions" aria-label={tr('Places', $language)}>
            <div class="results-heading"><strong>{tr('Places', $language)}</strong><label class="radius-choice">{tr('Radius', $language)} <select bind:value={$nearbyRadius}>{#each [5,25,50,100] as km}<option value={km}>{nearbyRadiusLabel(km)}</option>{/each}</select></label>{#if $placeSuggestions.length > 1}<button class="places-expand" type="button" aria-label={tr('Places', $language)} aria-expanded={$placesExpanded} onclick={() => placesExpanded.update(value => !value)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d={$placesExpanded ? 'm6 15 6-6 6 6' : 'm6 9 6 6 6-6'}/></svg></button>{/if}</div>
            <ol>
              {#each $placeSuggestions as place, index (place.id)}
                <li class:extra-place={index > 0 && !$placesExpanded} class:with-nearby={mode === 'public-release'}><button type="button" onclick={(event) => { event.stopPropagation(); selectPlace(place); }}>
                  <strong>{place.label}</strong>
                  <small>{tr('Navigate to city centre · Natural Earth, not a facility location', $language)}</small>
                </button>{#if mode === 'public-release'}<button type="button" class="nearby-search" aria-label={`${tr('Search nearby', $language)}: ${place.label}, ${nearbyRadiusLabel($nearbyRadius)}`} onclick={() => searchNear(place)}><span class="nearby-label">{tr('Search nearby', $language)}</span><span class="nearby-distance">{nearbyRadiusLabel($nearbyRadius)}</span></button>{/if}</li>
              {/each}
            </ol>
          </section>
        {/if}

        {#if aggregateOpen}<div class="member-context">
            <strong>{aggregateContext.place}</strong><span
              >{aggregateContext.treatment}</span
            ><small>Source context: {aggregateContext.sourceText}</small>
          </div>
          <p class="member-disclosure" role="status">
            Showing {resultCount} loaded member {resultCount === 1
              ? "record"
              : "records"} from this map reference. Members remain private-preview
            records.
          </p>{/if}{#if publicMap}<MobileSearchRecords records={aggregateRecords} selectedId={mapState.selectedId} onselect={selectSearchRecord}/>{:else}<RecordList
          records={aggregateRecords}
          selectedId={mapState.selectedId}
          onselect={selectSearchRecord}
        />{/if}{#if !aggregateOpen && !resultCount && !listRefreshing && (dataStatus === 'empty' || mode === 'synthetic')}<p class="list-empty" role="status">{tr('No records match this search and these filters.', $language)}</p>{/if}{#if aggregateOpen && aggregateLoading && !resultCount}<p class="list-empty" role="status">Loading members…</p>{/if}{#if mode !== "synthetic" && nextCursor && !aggregateOpen}<button
            type="button"
            disabled={pageLoading || listRefreshing}
            class="load-more"
            onclick={() => onLoadMore?.()}
            >{pageLoading ? "Loading…" : (mode === "candidate-preview" || mode === "public-release") && candidateTotalCount !== null ? `Load more (${resultCount} of ${candidateTotalCount})` : "Load more records"}</button
          >{:else if mode === "real-preview" && aggregateOpen && aggregateNextCursor}<button
            type="button"
            disabled={aggregateLoading}
            class="load-more"
            onclick={() => onLoadMoreAggregate?.()}
            >{aggregateLoading
              ? "Loading members…"
              : "Load more members"}</button
          >{/if}{#if aggregateOpen && aggregateError}<p
            role="alert"
            class="search-error"
          >
            {aggregateError}
          </p>{/if}
        </div>
    {#if !publicMap && active && mapState.selectedId && mode !== "synthetic" && detailStatus === "loading"}<section
        class="reading-sheet dossier"
        role="status"
        aria-label="Record evidence" hidden={detailCollapsed}
      >
        <header class="dossier-header"><button class="back-to-results" type="button" onclick={dismissSelection}>← {tr('Back to results', $language)}</button><button class="detail-close" type="button" aria-label={tr('Close record detail', $language)} onclick={dismissSelection}>×</button></header>
        <p class="dossier-message">Loading record evidence…</p>
      </section>{:else if !publicMap && active && mapState.selectedId && mode !== "synthetic" && (detailStatus === "error" || detailStatus === "unauthorized")}<section
        class="reading-sheet dossier"
        role="alert"
        aria-label="Record evidence" hidden={detailCollapsed}
      >
        <header class="dossier-header"><button class="back-to-results" type="button" onclick={dismissSelection}>← {tr('Back to results', $language)}</button><button class="detail-close" type="button" aria-label={tr('Close record detail', $language)} onclick={dismissSelection}>×</button></header>
        <p class="dossier-message">{detailError}</p>
      </section>{:else if !publicMap && active && mapState.selectedId && selected}<section class="reading-sheet dossier" aria-label="Record evidence" hidden={detailCollapsed}>
        <header class="dossier-header"><button class="back-to-results" type="button" onclick={dismissSelection}>← {tr('Back to results', $language)}</button><button class="detail-close" type="button" aria-label={tr('Close record detail', $language)} onclick={dismissSelection}>×</button></header>
        {#if aggregateOpen}<button type="button" class="back" onclick={dismissSelection}>← Members</button>{/if}
        <RecordDetail record={selected} presentation="rail" fullRecordHref={facilityPageHref} onshowmap={selected.latitude !== null && selected.longitude !== null ? showSelectedOnMap : undefined} />
      </section>{/if}
      </div>
    </aside>
    </div>
  </div>
</section>

<style>
  .public-map .map-toolbar { z-index: 7; gap: 0; }
  .public-map .desktop-search { position: relative; }
  .public-map .desktop-search .search { margin: 0; padding: 0; outline: none; }
  .public-map .desktop-search .search:focus-within { outline: 2px solid var(--focus); outline-offset: -2px; }
  .public-map .desktop-search .query-box { display: flex; align-items: center; width: 100%; min-width: 0; padding: 0; border: 0; outline: 0; }
  .public-map .desktop-search .query-box input { flex: 1; min-width: 0; padding-inline: .25rem; outline: 0; }
  .public-map .desktop-search .search-autocomplete { top: 100%; left: 0; right: 0; max-height: min(20rem, max(2.75rem, calc(var(--visual-workspace-height) - 4rem))); }
  .public-map .desktop-search .query-hint { margin: 0; padding: .65rem; }
  .public-filter-button { min-height: 44px; padding: 0 .85rem; border: 0; border-left: 1px solid var(--line); background: var(--panel); color: var(--ink); font: inherit; cursor: pointer; }
  .public-filter-button:hover, .public-filter-button[aria-expanded="true"] { background: var(--panel-hover); }
  .public-filter-button span { margin-left: .25rem; color: var(--muted); }
  .public-filter-panel { position: absolute; z-index: 8; inset: 3.4rem auto auto 0; display: flex; flex-direction: column; width: 100%; max-width: 28rem; max-height: calc(100% - 3.5rem); border: 1px solid var(--line); background: var(--panel); box-shadow: 0 6px 18px #0003; pointer-events: auto; }
  .workspace.public-map .results.behind-filters, .workspace.public-map .results.map-preview, .workspace.public-map .results.rail-collapsed { display: none; }
  .public-results-heading { min-height: 44px; display: flex; align-items: center; padding: 0 3rem 0 1rem; border-bottom: 1px solid var(--line); }
  .map-summary { position: absolute; z-index: 4; top: 48%; left: 50%; transform: translate(-50%, -50%); width: min(272px, calc(100% - 24px)); padding: .85rem 1rem .4rem; border: 1px solid #d5d1c7; border-radius: .4rem; background: #faf8f1; color: #262421; box-shadow: 0 5px 18px #0003; line-height: 1.4; overflow-wrap: anywhere; }
  .map-summary-anchored { top: var(--popup-y); left: var(--popup-x); transform: translate(-50%, -100%); }
  .map-summary-below { top: clamp(72px, var(--popup-y), calc(100% - 142px)); transform: translateX(-50%); }
  .map-summary-anchored::after { position: absolute; top: 100%; left: var(--popup-arrow); width: 0; height: 0; border: .5rem solid transparent; border-top-color: #faf8f1; transform: translateX(-50%); content: ''; }
  .map-summary-below::after { top: auto; bottom: 100%; border-top-color: transparent; border-bottom-color: #faf8f1; }
  .map-summary strong { display: block; padding-right: 2rem; font-weight: 650; }
  .map-summary p { margin: .25rem 0; color: #4d4943; font-size: .8125rem; }
  .summary-source { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; }
  .map-summary a, .map-summary button { color: inherit; font: inherit; }
  .map-summary a, .summary-back { display: inline-flex; align-items: center; min-height: 44px; }
  .summary-close, .summary-back { border: 0; background: none; cursor: pointer; }
  .summary-close { position: absolute; top: 0; right: 0; width: 44px; height: 44px; }
  .summary-back { padding: 0; margin-left: .7rem; text-decoration: underline; }
  @media (max-width:40rem) {
    .public-map .map-toolbar { inset: .65rem .65rem auto; width: auto; max-width: none; transform: none; }
    .public-map .desktop-search { display: grid; }
    .public-map .desktop-search .search input { font-size: 16px; }
    .workspace.public-map .map-tool-shell .results.typing { display: none; }
    .workspace.public-map .map-tool-shell .results { height: min(var(--results-height), max(0px, calc(var(--visual-workspace-height) - 4.25rem))); }
    .public-map .public-filter-panel { inset: 3.75rem .65rem auto; width: auto; max-width: none; max-height: calc(100% - 4.4rem); }
    .public-map:not(.workspace-open) .map-stage :global(.maplibregl-ctrl-bottom-right) { bottom: .35rem; }
    .workspace.public-map .map-tool-shell .results > header { display: block; top: 0; }
    .workspace.public-map .map-tool-shell .results > header[hidden] { display: none; }
    .public-map .mobile-results-heading { padding-right: 3rem; }
  }
  .public-map .public-scope { padding: .4rem .65rem; border-bottom: 1px solid var(--line); }
  .public-map .public-scope button { min-height: 44px; margin: 0; font-size: .8125rem; }
  .search-recovery { position:absolute;z-index:5;left:50%;bottom:calc(var(--mobile-sheet-height, 0px) + 12px);transform:translateX(-50%);display:flex;align-items:center;gap:12px;max-width:calc(100% - 32px);padding:0 10px 0 14px;border:1px solid var(--line);background:var(--panel);color:var(--ink);font-size:.8125rem; }
  .search-recovery button,.search-error button { min-height:44px;min-width:44px;padding:8px;border:0;background:transparent;color:inherit;font:inherit;text-decoration:underline;cursor:pointer; }
  .search-recovery button:focus-visible,.search-error button:focus-visible { outline:2px solid var(--focus,var(--ink));outline-offset:-2px; }
  .field-view {
    --mobile-toolbar-inset: .4rem;
    --mobile-toolbar-gap: .4rem;
    --mobile-toolbar-top: .45rem;
    --mobile-toolbar-height: 4rem;
    position: fixed;
    inset: 0;
    display: flex;
    flex-direction: column;
    min-width: 0;
    background: var(--page);
    color: var(--ink);
    font: .875rem/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  .field-view * { box-sizing: border-box; }
  .field-view :global(.masthead) { position: relative; z-index: 6; flex: 0 0 auto; }
  .map-stage { position: relative; flex: 1 1 auto; min-height: 0; padding: 0; }
  .map-stage :global(.map-surface), .map-stage :global(.map-host) { position: absolute; inset: 0; }
  .workspace .map-stage :global(.diagnostics-toggle) { left:auto;right:.65rem;z-index:8; }
  .workspace .map-stage :global(.map-diagnostics) { left:auto;right:.65rem;width:min(25rem,calc(100% - 1.3rem)); }
  .search { display: flex; align-items: center; gap: .65rem; min-width: 0; height: 3.25rem; padding: 0 3.25rem 0 1rem; outline: 1px solid var(--ink); outline-offset: -1px; }
  .search label, .results > header strong, .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
  .search svg, .search-toggle svg { width: 1.1rem; height: 1.1rem; flex: none; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; color: var(--muted); }
  .search input { width: 100%; min-width: 0; height: 100%; padding: 0; border: 0; color: var(--ink); background: transparent; font: inherit; font-size: .875rem; }
  .search input::placeholder { color: var(--muted); opacity: 1; }
  .search input:focus-visible { outline: 0; }
  .search:focus-within { outline: 2px solid var(--ink); outline-offset: -2px; }
  .search-tools { display: grid; grid-template-columns: minmax(0, 1fr); flex: 0 0 auto; }
  .search-toolbar { position: relative; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
  .filters { min-width: 0; }
  .filters summary { display: flex; align-items: center; gap: .4rem; width: fit-content; max-width: 8rem; min-height: 2.75rem; padding: .4rem .75rem; list-style: none; font-size: .75rem; cursor: pointer; }
  .filters summary > svg { width: .9rem; height: .9rem; flex: none; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; }
  .filters summary::after { content: ""; width: .3rem; height: .3rem; margin-left: .15rem; border-right: 1px solid currentColor; border-bottom: 1px solid currentColor; transform: rotate(45deg) translateY(-2px); }
  .filters[open] summary::after { transform: rotate(225deg) translate(-2px, -1px); }
  .filters summary::-webkit-details-marker { display: none; }
  .filters summary b { min-width: 1.25rem; padding: 0 .3rem; background: var(--panel-selected); text-align: center; font-weight: 500; font-variant-numeric: tabular-nums; }
  .filter-sheet { --filter-safe-bottom:env(safe-area-inset-bottom);position: absolute; z-index: 8; top: 100%; left: -1px; right: -1px; box-sizing:border-box;height:var(--filter-available-height,50dvh);max-height:var(--filter-available-height,50dvh); overflow: auto; overscroll-behavior: contain; padding: .25rem 1rem 1rem; border: 1px solid var(--line); background: var(--panel); box-shadow: 0 .7rem 1.5rem #0002; }
  .filter-sheet fieldset { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(11rem, 100%), 1fr)); gap: .1rem .75rem; margin: .8rem 0 0; padding: .6rem 0 0; border: 0; border-top: 1px solid var(--line); }
  .filter-sheet legend { padding: 0 .5rem 0 0; color: var(--muted); font-size: .75rem; font-weight: 500; }
  .filter-sheet label { display: flex; align-items: center; gap: .6rem; min-height: 2.75rem; padding: .3rem .1rem; font-size: .8rem; line-height: 1.4; overflow-wrap: anywhere; cursor: pointer; }
  .filter-sheet input[type="checkbox"], .filter-sheet input[type="radio"] { inline-size: 1rem; block-size: 1rem; flex: none; accent-color: var(--ink); }
  .filter-sheet .clear-filters { width: 100%; margin-top: .8rem; text-align: left; text-decoration: underline; text-underline-offset: .25rem; }
  .category-key { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; margin: .8rem 0 .4rem; color: var(--muted); font-size: .65rem; }
  .category-key i { width: .55rem; height: .55rem; border-radius: 50%; background: #c83232; }
  .category-key .pig { background: #8c8c8c; }
  .category-key .dairy { background: #7f5c9c; }
  .category-key .processing { background: #ccb44f; }
  .category-key .laboratory { background: #d47b30; }
  .category-key .aquaculture { background: #39804e; }
  .status { position: absolute; z-index: 4; top: 50%; left: 50%; max-width: min(30rem, calc(100% - 2rem)); padding: 1rem; border: 1px solid var(--line); background: var(--panel); transform: translate(-50%, -50%); }
  .search-toggle { position: absolute; z-index: 4; top: 0; left: 0; display: flex; align-items: center; gap: .75rem; min-width: 15rem; min-height: 3.25rem; padding: .6rem 1rem; border: 1px solid var(--line); background: var(--panel); color: var(--ink); text-align: left; cursor: pointer; }
  .results { position: absolute; z-index: 5; top: 1.5rem; bottom: 2rem; left: 1.5rem; display: flex; flex-direction: column; width: min(35rem, calc(100% - 3rem)); min-height: 0; border: 1px solid var(--line); background: var(--panel); }
  .rail-resize { position: absolute; z-index: 2; top: 0; right: -.45rem; bottom: 0; width: .9rem; padding: 0; border: 0; background: transparent; cursor: ew-resize; touch-action: none; }
  .rail-resize::after { content: ""; position: absolute; top: 45%; left: .34rem; width: 2px; height: 2.5rem; background: var(--muted); opacity: .6; }
  .results > header { position: absolute; z-index: 2; top: .25rem; right: .25rem; }
  .results > header button { display: grid; place-items: center; width: 2.75rem; height: 2.75rem; padding: 0; border: 0; color: var(--muted); background: transparent; font: 400 1.3rem/1 system-ui, sans-serif; cursor: pointer; }
  .results :global(.record-list) { flex:0 0 auto;min-height:auto;overflow:visible;border:0;background:transparent; }
  .results :global(.record-list h2) { display: none; }
  .results :global(.record-list ol) { margin: 0; padding: 0; list-style: none; }
  .results :global(.record-list li) { border: 0; }
  .results :global(.record-list button) { width: 100%; padding: var(--result-row-padding, 16px) 1rem; border: 0; border-bottom: 1px solid var(--line); color: var(--ink); background: transparent; text-align: left; }
  .results :global(.record-list button:hover) { background: var(--panel-hover); }
  .results :global(.record-list button.active) { background: var(--panel-selected); }
  .results :global(.record-list button:focus-visible) { outline: 2px solid var(--ink); outline-offset: -2px; }
  .results :global(.record-list strong) { font: 500 calc(.8125rem * var(--result-type-scale, 1))/1.45 system-ui, sans-serif; overflow-wrap: anywhere; }
  .results :global(.record-list small) { display: block; margin-top: .3rem; color: var(--muted); font: 400 calc(.6875rem * var(--result-type-scale, 1))/1.5 system-ui, sans-serif; overflow-wrap: anywhere; }
  .results-heading { display: flex; flex: 0 0 auto; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: .2rem .75rem; padding: .7rem 1rem; border-bottom: 1px solid var(--line); font-size: .6875rem; }
  .results-heading strong { font-weight: 500; }
  .result-status { position: absolute; top: 0; right: .75rem; display: flex; align-items: center; justify-content: flex-end; min-height: 2.75rem; width: calc(100% - 8.5rem); padding: .25rem 0; color: var(--muted); text-align: right; font-size: .625rem; line-height: 1.4; font-variant-numeric: tabular-nums; pointer-events: none; }
  .place-suggestions { flex: 0 0 auto; max-height: min(12rem, 32dvh); overflow-y: auto; border-bottom: 1px solid var(--line); }
  .place-suggestions ol { margin: 0; padding: 0; list-style: none; }
  .place-suggestions li + li { border-top: 1px solid var(--line); }
  .place-suggestions button { display: block; width: 100%; padding: .8rem 1rem; border: 0; color: var(--ink); background: transparent; text-align: left; cursor: pointer; }
  .place-suggestions button:hover { background: var(--panel-hover); }
  .place-suggestions strong, .place-suggestions small { display: block; }
  .place-suggestions strong { font-size: .8125rem; font-weight: 500; }
  .place-suggestions small { margin-top: .2rem; color: var(--muted); font-size: .6875rem; line-height: 1.5; }
  .load-more, .filter-sheet button, .open-members, .continue-members, .back { min-height: 2.75rem; padding: .55rem .75rem; border: 1px solid var(--line); color: var(--ink); background: transparent; font: inherit; font-size: .75rem; cursor: pointer; }
  .load-more { flex: 0 0 auto; width: calc(100% - 2rem); margin: .65rem 1rem; }
  .load-more:disabled { opacity: .55; cursor: default; }
  .search-error { margin: .75rem 1rem; color: var(--ink); font-size: .75rem; line-height: 1.5; }
  .reading-sheet { position: absolute; z-index: 5; top: 0; right: 0; bottom: 0; width: min(25rem, calc(100% - 3rem)); padding: 1.5rem; border-left: 1px solid var(--line); background: var(--page); overflow: auto; overscroll-behavior: contain; }
  .close { position: absolute; top: .65rem; right: .65rem; width: 2.75rem; height: 2.75rem; border: 0; color: var(--ink); background: transparent; font-size: 1.25rem; cursor: pointer; }
  .reading-sheet h2 { margin: 1rem 2rem .5rem 0; font: 500 1.8rem/1.15 system-ui, sans-serif; letter-spacing: -.035em; overflow-wrap: anywhere; }
  .reading-sheet p { color: var(--muted); }
  .dossier { padding: 0; }
  .dossier-header { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; justify-content: space-between; min-height: 3.5rem; gap: .5rem; padding: .35rem .6rem; border-bottom: 1px solid var(--line); background: var(--page); font-size: .75rem; }
  .dossier-header button { min-width: 2.75rem; min-height: 2.75rem; border: 0; color: var(--muted); background: transparent; font-size: 1.25rem; cursor: pointer; }
  .dossier-message { margin: 1.5rem; }
  .eyebrow { margin: 0 0 .3rem; color: var(--muted); font: .625rem/1.5 system-ui, sans-serif; letter-spacing: .08em; }
  .place { margin-top: 0; }
  .reading-sheet dl { margin: 1.3rem 0; }
  .reading-sheet dl div { display: grid; grid-template-columns: 7rem minmax(0, 1fr); gap: .7rem; padding: .7rem 0; border-top: 1px solid var(--line); }
  .reading-sheet dt { color: var(--muted); font-size: .75rem; }
  .reading-sheet dd { margin: 0; font-size: .8125rem; line-height: 1.5; overflow-wrap: anywhere; }
  .evidence-note { padding: .8rem 0; border-top: 1px solid var(--line); font-size: .75rem; line-height: 1.5; }
  .open-members, .continue-members { width: 100%; margin: .3rem 0; }
  .member-context { display: grid; gap: .25rem; padding: .8rem 1rem; border-bottom: 1px solid var(--line); background: var(--panel-selected); }
  .member-context strong { font-size: .8125rem; font-weight: 500; }
  .member-context span, .member-context small { color: var(--muted); font-size: .6875rem; line-height: 1.5; }
  .member-disclosure { margin: 0; padding: .8rem 1rem; border-bottom: 1px solid var(--line); color: var(--muted); font-size: .6875rem; line-height: 1.5; }
  .aggregate-source { margin: .3rem 2rem .25rem 0; color: var(--muted); font: .75rem/1.5 system-ui, sans-serif; }
  .back { margin: .8rem 1.5rem 0; }
  .continuation-note { margin: .6rem 0; font-size: .75rem; line-height: 1.5; }
  .search-toggle:hover, .filters summary:hover, .results > header button:hover, .dossier-header button:hover, .close:hover, .load-more:hover:not(:disabled), .filter-sheet button:hover, .back:hover, .open-members:hover, .continue-members:hover { background: var(--panel-hover); }
  button:focus-visible, summary:focus-visible, .filter-sheet input:focus-visible { outline: 2px solid var(--ink); outline-offset: 3px; }
  .rail-resize:focus-visible { outline-offset: -3px; }
  .field-view [hidden] { display: none !important; }
  .workspace { position: relative; display: block; grid-template-columns: none; grid-template-rows: none; flex: 1 1 auto; min-height: 0; height: auto; border: 0; }
  .workspace-open { display:block; }
  .workspace .map-stage { width: 100%; height: 100%; min-width: 0; min-height: 0; }
  .workspace-open .map-stage { grid-column: 2; grid-row: 1; }
  .workspace .results { position:absolute;inset:0 auto 0 0;width:var(--workspace-width);max-width:none;min-width:0;min-height:0;border:0;border-right:1px solid var(--line);background:var(--panel); }
  .workspace .results > header { z-index: 5; }
  .workspace .results.rail-collapsed, .workspace .results.map-preview { display:none; }
  .mobile-sheet-control { display:none; }
  .results :global(.record-list strong) { font-size:calc(.9375rem * var(--result-type-scale,1)); }
  .results :global(.record-list small) { font-size:calc(.75rem * var(--result-type-scale,1)); }
  .workspace-body { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }
  .list-content { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; overflow: auto; overscroll-behavior: contain; }
  .list-content > :global(*) { flex-shrink:0; }
  .list-empty { margin: 1rem; color: var(--muted); font-size: .8125rem; }
  .workspace .reading-sheet { position: relative; inset: auto; width: 100%; max-width: none; border: 0; background: var(--panel); }
  .workspace .dossier { flex: 1 1 auto; min-height: 0; padding: 0; overflow: auto; scroll-padding-top:4rem; }
  .workspace .dossier-header { position: sticky; top: 0; display: flex; flex-wrap: wrap; gap: .5rem; padding: .35rem .75rem; background: var(--panel); }
  .workspace .dossier-header .back-to-results { flex: 0 1 auto; padding: .35rem .4rem; min-height: 2.75rem; border: 0; font: inherit; font-size: .75rem; color: var(--muted); background: transparent; }
  .workspace .dossier-header > button:last-child { margin-left: auto; }
  .workspace .reading-sheet.aggregate-sheet { flex: 0 0 auto; margin: 0; padding: .75rem 1rem; border-bottom: 1px solid var(--line); }
  .aggregate-sheet > summary { min-height: 2.75rem; padding: .5rem 2.5rem .5rem 0; font-size: .8125rem; cursor: pointer; }
  .workspace .aggregate-sheet h2 { font-size: 1.2rem; }
  .search-tools { position: relative; background: var(--panel); z-index: 3; }
  .search-autocomplete { position: absolute; top: 3.25rem; left: .6rem; right: .6rem; z-index: 9; max-height: min(20rem, 45dvh); overflow: auto; padding: .3rem; border: 1px solid var(--line); background: var(--panel); box-shadow: 0 .5rem 1rem #0002; }
  .search-autocomplete button { display: flex; align-items: center; justify-content: space-between; gap: 1rem; width: 100%; min-height: 2.75rem; padding: .55rem .7rem; border: 0; text-align: left; background: transparent; color: var(--ink); font: inherit; }
  .search-autocomplete button:hover { background: var(--panel-hover); }
  .search-autocomplete button[aria-selected="true"] { background: var(--panel-selected); }
  .search-autocomplete strong { font-size: .8125rem; font-weight: 500; }
  .search-autocomplete small { color: var(--muted); font-size: .6875rem; }
  .filter-chips { display: flex; flex-wrap: wrap; gap: .4rem; padding: 0 1rem .65rem; }
  .filter-chips:empty { display: none; }
  .filter-chips button { display: inline-flex; align-items: center; gap: .6rem; max-width: 100%; min-height: 1.9rem; padding: .2rem .5rem; border: 1px solid var(--line); color: var(--ink); background: transparent; font-size: .6875rem; line-height: 1.4; text-align: left; overflow-wrap: anywhere; }
  .filter-chips span { flex: none; color: var(--muted); font-size: 1rem; }
  .search-toolbar { display: flex; align-items: center; gap: .5rem; min-height: 2.75rem; padding-right: .4rem; }
  .scope-chip { display:inline-flex;align-items:center;gap:.4rem;flex:0 0 auto;min-height:32px;padding:.25rem .4rem;border:1px solid var(--line);color:var(--ink);background:transparent;font:inherit;font-size:.6875rem;cursor:pointer; }
  .scope-chip > span:first-child { white-space:nowrap; }
  .scope-chip > span:last-child { color:var(--muted);font-size:1rem; }
  .filters { flex: 0 0 auto; }
  .filters summary { max-width: none; }
  .result-status { position: static; width: auto; min-width: 0; min-height: auto; margin-left: auto; padding: .25rem 0; text-align: right; font-size: .6875rem; }
  .place-suggestions .results-heading { min-height:44px;align-items:center;flex-wrap:nowrap;gap:.35rem;padding:0 .8rem; }
  .place-suggestions .places-expand { display:grid;place-items:center;flex:0 0 44px;width:44px;height:44px;min-width:44px;min-height:44px;padding:0;border:0;color:var(--ink);background:transparent; }
  .place-suggestions .places-expand svg { display:block;width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round; }
  .place-suggestions .extra-place { display:none; }
  .place-suggestions li { display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center; }
  .place-suggestions li > button { min-width:0;min-height:44px;overflow-wrap:anywhere; }
  .radius-choice { display:flex;align-items:center;gap:.35rem;min-width:0;margin-left:auto;color:var(--muted);font-size:.6875rem; }
  .radius-choice select { width:5.25rem;max-width:100%;min-height:44px;padding:.25rem;border:1px solid var(--line);border-radius:0;color:var(--ink);background:var(--panel);font:inherit; }
  .place-suggestions .nearby-search { display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:.15rem .35rem;min-height:2.75rem;padding-top:.25rem;color:var(--muted);font-size:.6875rem;line-height:1.4;text-decoration:underline;text-underline-offset:.2rem; }
  .nearby-distance { white-space:nowrap; }
  @media (max-width: 60rem) {
    .search-toolbar { flex-wrap: wrap; gap: 0 .25rem; }
    .result-status { flex: 1 1 5rem; }
    .workspace .dossier-header .back-to-results { flex: 1 1 calc(100% - 3.5rem); }
    .workspace .dossier-header > button:last-child { flex: 0 0 2.75rem; }
  }
  @media (max-width: 40rem) {
    .workspace, .workspace-open { display:block;flex:0 1 var(--visual-workspace-height);height:var(--visual-workspace-height);max-height:var(--visual-workspace-height); }
    .workspace .map-stage, .workspace-open .map-stage { grid-column:1;grid-row:1; }
    .workspace .results { position:absolute;inset:auto 0 0;width:100%;height:var(--mobile-sheet-height,56px);border-right:0;border-top:1px solid var(--line);border-radius:12px 12px 0 0; }
    .map-stage :global(.maplibregl-ctrl-bottom-left), .map-stage :global(.maplibregl-ctrl-bottom-right) { left:auto;right:.5rem;bottom:calc(var(--mobile-sheet-height,56px) + .15rem); }
    .map-stage :global(.maplibregl-ctrl-attrib) { box-sizing:border-box;width:128px;margin:0;white-space:normal;overflow-wrap:anywhere; }
    .workspace .map-stage :global(.diagnostics-toggle) { left:.65rem;right:auto;bottom:min(calc(var(--mobile-sheet-height,56px) + 3rem),calc(100% - 3rem)); }
    .workspace .map-stage :global(.map-diagnostics) { left:.65rem;right:auto;width:calc(100% - 1.3rem);bottom:calc(var(--mobile-sheet-height,56px) + .4rem);max-height:calc(100% - var(--mobile-sheet-height,56px) - 1rem); }
    .workspace.debug-active .map-stage { z-index:9; }
    .workspace.debug-active .map-stage :global(.diagnostics-toggle) { top:.65rem;bottom:auto; }
    .workspace.debug-active .map-stage :global(.map-diagnostics) { bottom:.65rem;max-height:calc(100% - 4.5rem); }
    .workspace .results.rail-collapsed, .workspace .results.map-preview { display:flex; }
    .mobile-sheet-control { display:block;flex:0 0 auto; }
    .workspace.detail-active .results { padding:0 env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left); }
    .workspace .reading-sheet.dossier { position: relative; inset: auto; width: 100%; height: auto; max-height: none; padding: 0; }
    .search-toggle { display:none; }
    .workspace .results > header { top:2.9rem; }
    .workspace .results.rail-collapsed .workspace-body,.workspace .results.map-preview .workspace-body { display:none; }
    .rail-resize { display: none; }
    .search input { font-size: 1rem; }
    .filter-sheet label { min-height: 2.75rem; }
    .workspace .aggregate-sheet dl, .workspace .aggregate-sheet .evidence-note, .workspace .aggregate-sheet .open-members { display: block; }
    .place-suggestions .results-heading { min-height: 2.75rem; gap: .4rem; padding: 0 .65rem; }
    .radius-choice { margin-left: auto; }
    .radius-choice select { min-height: 2.75rem; }
    .place-suggestions li { display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center; }
    .place-suggestions li.with-nearby { grid-template-columns:minmax(0,1fr) minmax(7rem,42%); }
    .place-suggestions li > button { min-width: 0; min-height: 2.75rem; padding: .45rem .65rem; }
    .place-suggestions strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .place-suggestions small { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
    .place-suggestions .nearby-search { flex-direction:column;align-items:flex-end;justify-content:center;gap:.15rem;width:100%;padding:.45rem .65rem;text-align:right; }
    .nearby-label { display:block;max-width:100%;overflow-wrap:normal; }
    .workspace .dossier-header { padding-top: .35rem; }
    .filter-chips button { min-height:2.75rem;font-size:.75rem; }
    .result-status { font-size:.75rem; }
    .scope-chip { min-height:44px; }
    .search-toolbar { gap:0 .4rem;padding-right:.75rem; }
  }
  @media (pointer: coarse) { .filter-chips button { min-height: 2.75rem; } }
  @media(max-width:40rem) and (max-height:700px) {
    .search { height:44px; }
    .results :global(.record-list button) { padding-block:8px; }
  }

/* The search input stays anchored as its joined results surface opens below. */
.map-tool-shell { position:absolute;z-index:5;top:1rem;left:1.5rem;width:clamp(28rem,var(--workspace-width),calc(100% - 3rem));max-width:calc(100% - 3rem);height:calc(100% - 2rem);pointer-events:none; }
.map-toolbar { position:relative;display:flex;align-items:stretch;width:100%;max-width:100%;border:1px solid var(--line);background:var(--panel);box-shadow:0 3px 14px #0002;pointer-events:auto; }
.desktop-search { flex:1;min-width:0; }
.desktop-search .search { height:44px;padding:0 .8rem 0 0;gap:0; }
.desktop-search .search-toggle { position:static;display:grid;place-items:center;min-width:44px;width:44px;height:44px;min-height:44px;padding:0;border:0;background:transparent; }
.desktop-search .search-toggle:hover { background:var(--panel-hover); }
.desktop-search .search input { height:44px;font-size:.8125rem; }
.desktop-search .search-autocomplete { top:100%;left:-1px;right:-1px; }
.workspace .map-tool-shell .results { top:45px;bottom:0;left:0;width:100%;border:1px solid var(--line);border-top:0;pointer-events:auto;box-shadow:0 7px 16px #0002; }
.workspace .map-tool-shell .results > header { top:0;right:0; }
.workspace .map-tool-shell .search-toolbar { padding-right:3rem;border-top:0; }
.filter-sheet { display:flex;flex-direction:column;padding:0;overflow:hidden;box-shadow:none; }
.filter-scroll { flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:.35rem 1rem 1rem; }
.filter-sheet fieldset { grid-template-columns:repeat(2,minmax(0,1fr));gap:.1rem .55rem;margin-top:.65rem; }
.filter-choice fieldset { grid-template-columns:minmax(0,1fr); }
.filter-sheet label { min-height:44px;font-size:.75rem;gap:.5rem; }
.filter-choice { border-top:1px solid var(--line);margin-top:.65rem; }
.filter-choice > summary { display:flex;justify-content:space-between;align-items:center;width:100%;max-width:none;min-height:44px;padding:.55rem 0;font-size:.75rem; }
.filter-choice > fieldset { margin:0;padding:0;border:0; }
.filter-actions { display:flex;justify-content:space-between;align-items:center;gap:.5rem;flex:none;padding:.65rem .8rem;border-top:1px solid var(--line);background:var(--panel); }
.filter-actions .clear-filters { width:auto;margin:0;padding:.5rem .45rem;border:0;text-decoration:none; }
.filter-actions .show-results { background:var(--ink);color:var(--panel);border-color:var(--ink);padding-inline:1rem; }
.filter-actions .show-results:hover { opacity:.9;background:var(--ink); }
@media(max-width:40rem) {
  .map-tool-shell { position:static;transform:none;width:auto;height:auto;max-width:none; }
  .map-toolbar { position:absolute;z-index:7;top:.8rem;left:50%;width:max-content;transform:translateX(-50%);max-width:calc(100% - 1.2rem); }
  .map-toolbar.toolbar-hidden { visibility:hidden;pointer-events:none; }
  .desktop-search { display:none; }
  .workspace .map-tool-shell .results { inset:auto 0 0;width:100%;height:var(--mobile-sheet-height,56px);border:0;border-top:1px solid var(--line);border-radius:0; }
  .workspace .map-tool-shell .results > header { top:2.9rem;right:.25rem; }
  .workspace .map-tool-shell .search-toolbar { padding-right:.65rem; }
  .filter-scroll { padding-inline:.85rem; }
  .filter-actions { padding-bottom:max(.65rem,env(safe-area-inset-bottom)); }
  .filter-sheet label { font-size:.75rem; }
}

  .filter-choice .choice-value { margin-left:auto;max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font-weight:400; }
  .filters .filter-choice > summary::after { transform:rotate(45deg) translateY(-2px); }
  .filters .filter-choice[open] > summary::after { transform:rotate(225deg) translate(-2px,-1px); }
  .filter-sheet label,.filter-choice > summary,.filter-actions button { font-size:.875rem; }
  .query-box{display:contents}
  .search-list-recovery{display:flex;align-items:center;justify-content:space-between;gap:.6rem;flex:none}.search-list-recovery[hidden]{display:none}.search-list-recovery button{min-height:44px;flex:none}
  .mobile-clear-query,.mobile-results-heading{display:none}
  @media(max-width:40rem){
    .mobile-discovery .results>header{display:none}
    .mobile-discovery .search{height:44px;margin:0 .75rem;padding:0;gap:.45rem;outline:0}
    .mobile-discovery .search:focus-within{outline:0}
    .mobile-discovery .query-box{display:flex;align-items:center;flex:1;min-width:0;height:44px;padding-left:.6rem;border:1px solid var(--ink);border-radius:3px}
    .mobile-discovery .query-box:focus-within{outline:1px solid var(--ink);outline-offset:1px}
    .mobile-discovery .query-box>svg{width:15px;height:15px}
    .mobile-discovery .query-box input{min-width:0;height:42px;font-size:16px;padding:0 .4rem}
    .mobile-discovery .query-box input:focus-visible{outline:0}
    .mobile-discovery .query-box input::-webkit-search-cancel-button{appearance:none}
    .mobile-clear-query{display:grid;place-items:center;flex:none;width:44px;height:44px;border:0;background:none;color:var(--muted);padding:0}
    .mobile-clear-query svg{width:12px;height:12px;stroke:currentColor}
    .mobile-results-heading{display:flex;justify-content:space-between;align-items:center;min-height:44px;padding:0 .8rem;border-bottom:1px solid var(--line);gap:.65rem}
    .mobile-results-heading strong{font:500 .75rem/1.35 system-ui,sans-serif}
    .mobile-results-heading button{display:flex;align-items:center;gap:.3rem;max-width:48%;min-width:44px;min-height:44px;padding:.25rem 0;border:0;background:none;color:var(--muted);font:inherit;font-size:.625rem;text-align:right}
    .mobile-results-heading svg{width:13px;height:13px;flex:none;fill:none;stroke:currentColor;stroke-width:1.5}
    .mobile-discovery .search-autocomplete{top:44px;left:.75rem;right:.75rem}
    .mobile-discovery .search-error{font-size:.75rem;margin:.45rem .8rem}
    .mobile-discovery .list-empty{font-size:.75rem;margin:.8rem}
  }
</style>
