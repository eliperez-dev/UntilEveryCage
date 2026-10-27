<script lang="ts">
  import { tick } from "svelte";
  import { writable } from "svelte/store";
  import type {
    DirectionViewProps,
    LabRecord,
    MapDiagnostics,
    Precision,
    ViewportBounds,
    LabFilters,
  } from "../../contract";
  import type { RealPreviewFacet } from "../../../api/RealPreviewRepository";
  import type { CandidateFacets } from "../../../api/TestReleaseRepository";
  import MapSurface from "../../components/MapSurface.svelte";
  import MapNavigation from "../../components/MapNavigation.svelte";
  import RecordList from "../../components/RecordList.svelte";
  import MobileSearchSheet from "../../components/MobileSearchSheet.svelte";
  import { filterViewportHeight } from "../../components/mobileSheet";
  import type { LayoutTuning } from "../../components/mapDebug";
  import RecordDetail from "../../../app/RecordDetail.svelte";
  import PreviewMasthead from "../../../app/PreviewMasthead.svelte";
  import { encodeLabHash, encodeMapNavigationHash } from "../../state";
  import type { PlaceSuggestion } from "../../../features/placeSearch/placeSearch";
  import { publicReleaseLabel } from "../../../features/locations/releasePresentation";
  import { CATEGORY_PRESENTATIONS } from "../../../features/locations/categoryPresentation";
  import { language, tr } from '../../../app/language';
  import { serializeRoute } from "../../../app/routeState";
  import { parseSearch, searchSuggestions, applySearchSuggestion, areaScopeFromBounds, type SearchSuggestion } from "../../../features/search/powerSearch";
  let {
    active = true,
    state,
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
    onRetryMapMatches,
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
    detailRecord ??
      recordPool.find((record) => record.id === state.selectedId) ??
      null,
  );
  const facilityPageHref = $derived(selected ? serializeRoute({
    kind: 'record', facilityId: selected.id,
    ...(mode === 'public-release' ? { profile: 'official', ...(publicReleaseId ? { releaseId: publicReleaseId } : {}) } : {}),
  }) : null);
  const aggregateRecords = $derived(
    state.aggregateMemberIds === null
      ? records
      : recordPool.filter((record) =>
          state.aggregateMemberIds!.includes(record.id),
        ),
  );
  const aggregateOpen = $derived(state.aggregateMemberIds !== null);
  const aggregateRequestedCount = $derived(
    state.aggregateMemberIds?.length ?? 0,
  );
  const aggregateContext = $derived(aggregateContextFor(aggregateRecords));
  const mapped = $derived(
    mapRows.filter(
      (record) => record.latitude !== null && record.longitude !== null,
    ),
  );
  const resultCount = $derived(aggregateRecords.length);
  const workspaceOpen = $derived(state.listOpen || Boolean(state.selectedId) || aggregateOpen);
  const railWidth = writable<number | null>(null);
  const layoutTuning = writable<LayoutTuning>({ panelWidthPercent: 100 / 3, rowPadding: 16, typeScale: 1, mobileSheetPercent: 48, mobileExpandedPercent: 90 });
  const sheetHeight = writable(56);
  const workspaceHeight = writable(0);
  const detailMapPreview = writable(false);
  const showingDetail = $derived(Boolean(state.selectedId) && !$detailMapPreview);
  function measureWorkspace(node: HTMLDivElement) {
    const measure = () => {
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
      if (!disclosure?.open || !matchMedia('(max-width:40rem)').matches) return;
      const viewportBottom = window.visualViewport ? window.visualViewport.offsetTop + window.visualViewport.height : window.innerHeight;
      const safeArea = parseFloat(getComputedStyle(node).getPropertyValue('--filter-safe-bottom')) || 0;
      node.style.setProperty('--filter-available-height', `${filterViewportHeight(node.getBoundingClientRect().top, viewportBottom, safeArea)}px`);
    };
    const schedule = () => { if (frame) cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    const observer = new ResizeObserver(schedule);
    const workspace = node.closest('.workspace');
    const map = workspace?.querySelector('.map-stage');
    const search = node.closest('.search-tools');
    if (map) observer.observe(map);
    if (search) observer.observe(search);
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
      mobileSheetPercent: Math.max(35, Math.min(65, value.mobileSheetPercent ?? 48)),
      mobileExpandedPercent: Math.max(75, Math.min(95, value.mobileExpandedPercent ?? 90)),
    });
    railWidth.set(null);
  }
  function resetLayoutTuning() {
    layoutTuning.set({ panelWidthPercent: 100 / 3, rowPadding: 16, typeScale: 1, mobileSheetPercent: 48, mobileExpandedPercent: 90 });
    railWidth.set(null);
  }
  function resizeRail(event: PointerEvent) {
    const startX = event.clientX;
    const startWidth = $railWidth ?? window.innerWidth * $layoutTuning.panelWidthPercent / 100;
    const resize = (move: PointerEvent) => { railWidth.set(Math.max(300, Math.min(Math.floor(window.innerWidth * 0.55), startWidth + move.clientX - startX))); };
    const stop = () => { window.removeEventListener('pointermove', resize); window.removeEventListener('pointerup', stop); };
    window.addEventListener('pointermove', resize); window.addEventListener('pointerup', stop, { once: true });
  }
  function resizeRailKey(event: KeyboardEvent) {
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault(); railWidth.update(width => Math.max(300, Math.min(Math.floor(window.innerWidth * 0.55), (width ?? window.innerWidth * $layoutTuning.panelWidthPercent / 100) + (event.key === 'ArrowRight' ? 24 : -24))));
    }
  }
  const activeFilters = $derived(
    (state.query.trim() ? 1 : 0) +
    (state.sourceId ? 1 : 0) +
    (state.searchScope ? 1 : 0) +
    state.filters.categories.length + state.filters.precisions.length + state.filters.countries.length + state.filters.sources.length + state.filters.activities.length,
  );
  function toggleCandidateFilter(field: 'countries' | 'sources' | 'categories' | 'activities', value: string, checked: boolean) {
    const current = state.filters[field];
    dispatch({ type: 'filters', value: { ...state.filters, [field]: checked ? [...new Set([...current, value])] : current.filter(item => item !== value) } });
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
        ...state.filters,
        categories: checked
          ? [...state.filters.categories, value]
          : state.filters.categories.filter((item) => item !== value),
      },
    });
    dispatch({ type: 'results' });
  }
  function precision(value: Precision, checked: boolean) {
    dispatch({
      type: "filters",
      value: {
        ...state.filters,
        precisions: checked
          ? [...state.filters.precisions, value]
          : state.filters.precisions.filter((item) => item !== value),
      },
    });
    dispatch({ type: 'results' });
  }
  const sources = $derived(
    [...new Set(facets.map((facet) => facet.sourceId))].sort(),
  );
  let selectionOrigin: HTMLElement | null = null;
  let selectionOriginRecordId: string | null = null;
  // `state` is a prop in this component, so $state is interpreted as a store
  // subscription rather than Svelte's rune. Use a store for this DOM binding.
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
  const flightTarget = writable<{
    id: number;
    longitude: number;
    latitude: number;
    zoom: number;
  } | null>(null);
  let flightSequence = 0;
  const mapCameraPitch = writable(0);
  const mapControlsReady = writable(false);
  let cameraRequestSequence = 0;
  const cameraViewRequest = writable<{ id: number; enable3d: boolean } | null>(null);
  function toggleMapCameraView() {
    cameraViewRequest.set({ id: ++cameraRequestSequence, enable3d: $mapCameraPitch <= 0.5 });
  }
  let placeSearchGeneration = 0;
  let placeSearchModule: Promise<typeof import("../../../features/placeSearch/placeSearch")> | undefined;
  // The gazetteer is lazy and local: typing a place never contacts a geocoder.
  $effect(() => {
    const query = state.query.trim();
    placesExpanded.set(false);
    if (!active || !state.listOpen || query.length < 2 || aggregateOpen) {
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
  $effect(() => {
    if (state.selectedId) {
      hadSelection = true;
      if (activeSelectionId !== state.selectedId) {
        detailMapPreview.set(false);
        activeSelectionId = state.selectedId;
        pendingRailFocusId = state.selectedId;
      }
      // A Forward navigation can restore the dossier without calling
      // selectRecord again. Keep its row as the dismissal fallback.
      selectionOriginRecordId ??= state.selectedId;
      // Wait for evidence loading to finish: the loading and ready rails are
      // separate branches, so focusing the loading close button would leave
      // focus on BODY when that branch is replaced.
      if (pendingRailFocusId === state.selectedId && detailStatus !== "loading") {
        const id = state.selectedId;
        void tick().then(() => {
          if (state.selectedId === id) {
            const close = document.querySelector<HTMLButtonElement>(".dossier-header .detail-close");
            if (close) {
              close.focus();
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
          : restoredRecord ?? (matchMedia('(max-width:40rem)').matches ? document.querySelector<HTMLButtonElement>('.mobile-sheet-handle') : $searchToggle);
        const focused = document.activeElement;
        const editingSearch = focused instanceof HTMLElement && focused.isConnected && focused.closest('.search-tools');
        if (!editingSearch) target?.focus();
        selectionOrigin = null;
        selectionOriginRecordId = null;
      });
    }
  });
  function selectRecord(id: string) {
    detailMapPreview.set(false);
    autocompleteOpen.set(false);
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
    // Keep the drawer in the hit-test tree until this pointer click finishes.
    // Removing it synchronously can send the tail of the gesture to the map.
    setTimeout(() => dispatch({ type: "list", value: false }), 0);
  }
  function dismissSelection() {
    detailMapPreview.set(false);
    dispatch({ type: "results" });
  }
  function openMobileSearch() {
    if ($detailMapPreview && state.selectedId) {
      detailMapPreview.set(false);
      void tick().then(() => document.querySelector<HTMLButtonElement>('.dossier .detail-close')?.focus());
      return;
    }
    dispatch({ type: 'list', value: true });
  }
  function collapseMobileSearch() {
    autocompleteOpen.set(false);
    if ($filterDisclosure) $filterDisclosure.open = false;
    dispatch({ type: 'list', value: false });
  }
  async function showSelectedOnMap() {
    if (!selected || selected.latitude === null || selected.longitude === null) return;
    const record = selected;
    detailMapPreview.set(true);
    await tick();
    document.querySelector<HTMLButtonElement>(matchMedia('(max-width:40rem)').matches ? '.mobile-sheet-handle' : '.search-toggle')?.focus({ preventScroll: true });
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (state.selectedId === record.id && record.longitude !== null && record.latitude !== null) {
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
    if (state.selectedId) {
      dismissSelection();
      return;
    }
    if (aggregateOpen) {
      dispatch({ type: "aggregate", value: null });
      return;
    }
    if (state.listOpen) dispatch({ type: "list", value: false });
  }
  function onKeydown(event: KeyboardEvent) {
    if (!active) return;
    const target = event.target;
    const editing = target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
    if (event.key === "/" && !editing && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      detailMapPreview.set(false);
      if (state.selectedId) dispatch({ type: 'results' });
      dispatch({ type: "list", value: true });
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
    if (event.key === "Escape" && (state.selectedId || aggregateOpen || state.listOpen)) {
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
      const navigationViewport = state.navigationViewport ?? state.viewport;
      if (mode === "real-preview" || mode === "candidate-preview") q.set("f1a", "field");
      if (mode === "public-release" && selectedPublicReleaseId) q.set("release_id", selectedPublicReleaseId);
      if (state.sourceId) q.set("source", state.sourceId);
      for (const value of state.filters.categories) q.append('category', value);
      for (const value of state.filters.precisions) q.append('precision', value);
      for (const value of state.filters.countries) q.append('country', value);
      for (const value of state.filters.sources) q.append('source_filter', value);
      for (const value of state.filters.activities) q.append('activity', value);
      if (state.selectedId) q.set("selected", state.selectedId);
      q.set("lat", String(navigationViewport.centerLat));
      q.set("lon", String(navigationViewport.centerLon));
      q.set("z", String(navigationViewport.zoom));
      if (navigationViewport.pitch) q.set("pitch", String(navigationViewport.pitch));
      if (navigationViewport.bearing) q.set("bearing", String(navigationViewport.bearing));
      if (!state.listOpen) q.set("list", "closed");
      if (state.basemap !== "vector") q.set("basemap", state.basemap);
      return `#/database?${q}`;
    })(),
  );
  const mapHref = $derived(encodeMapNavigationHash(databaseHref, mode === "public-release" ? undefined : state.scenario));
  const downloadsHref = $derived.by(() => {
    const context = encodeLabHash(state, mode === 'real-preview' || mode === 'candidate-preview', mode === 'public-release');
    const params = new URLSearchParams(context.split('?')[1] ?? '');
    if (mode === 'public-release' && (selectedPublicReleaseId || publicReleaseId)) params.set('release_id', selectedPublicReleaseId || publicReleaseId!);
    return serializeRoute({ kind: 'downloads', returnMapHref: `#/map?${params}` });
  });

  const currentBounds = writable<ViewportBounds | null>(null);
  const autocompleteOpen = writable(false);
  const suggestionIndex = writable(-1);
  const scopeError = writable("");
  const nearbyRadius = writable(25);
  const filterDisclosure = writable<HTMLDetailsElement | undefined>(undefined);
  const suggestions = $derived(searchSuggestions(state.query, candidateFacets, $language));
  const countries = $derived(new Intl.DisplayNames([$language], { type: 'region' }));
  function countryName(value: string) { try { return countries.of(value) ?? value; } catch { return value; } }
  function sourceName(value: string) { return candidateFacets?.sources.find(facet => facet.value === value)?.label ?? value; }
  function categoryName(value: string) { return value in CATEGORY_PRESENTATIONS ? tr(CATEGORY_PRESENTATIONS[value as keyof typeof CATEGORY_PRESENTATIONS].label, $language) : value; }
  function removeFilter(field: keyof LabFilters, value: string) {
    dispatch({ type: 'filters', value: { ...state.filters, [field]: state.filters[field].filter(item => item !== value) } });
    dispatch({ type: 'results' });
  }
  function applyParsedSearch() {
    const parsed = parseSearch(state.query, state.filters, candidateFacets, $language);
    dispatch({ type: 'search', value: parsed });
    autocompleteOpen.set(false);
  }
  function applySuggestion(suggestion: SearchSuggestion) {
    dispatch({ type: 'search', value: applySearchSuggestion(suggestion, state.filters) });
    autocompleteOpen.set(false);
    void tick().then(() => { document.querySelector<HTMLInputElement>('#field-search')?.focus(); autocompleteOpen.set(false); });
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
    autocompleteOpen.set(false);
    scopeError.set('');
    detailMapPreview.set(false);
    dispatch({ type: 'close-workspace' });
  }
  function searchArea() {
    if (!$currentBounds) return;
    const scope = areaScopeFromBounds($currentBounds);
    if (!scope) { scopeError.set(tr('This map area crosses the date line. Zoom in and try again.', $language)); return; }
    scopeError.set('');
    dispatch({ type: 'scope', value: scope });
    dispatch({ type: 'results' });
  }
  function searchNear(place: PlaceSuggestion) {
    scopeError.set('');
    dispatch({ type: 'search', value: { query: '', filters: state.filters } });
    dispatch({ type: 'scope', value: { kind: 'radius', label: place.label, latitude: place.latitude, longitude: place.longitude, radiusKm: $nearbyRadius } });
    dispatch({ type: 'results' });
    flyTo(place.longitude, place.latitude, 10);
    autocompleteOpen.set(false);
  }
  function detailFilter(field: 'categories' | 'sources', value: string) {
    dispatch({ type: 'filters', value: { ...state.filters, [field]: [...new Set([...state.filters[field], value])] } });
    dispatch({ type: 'results' });
  }

</script>

<svelte:window onkeydown={onKeydown} />
<section class="field-view">
  {#if active}<PreviewMasthead privateTools={mode === "real-preview" || mode === "candidate-preview"} publicReleaseLabel={mode === "candidate-preview" ? $candidatePreviewLabel : publicReleaseLabel(publicMapMeta?.releaseId, publicMapMeta?.releaseLabel)} releaseDescription={mode === "candidate-preview" && $candidatePreviewLabel ? 'Configured private candidate release.' : null} {releaseOptions} selectedReleaseId={mode === "public-release" ? selectedPublicReleaseId : null} {...(onreleasechange ? { onreleasechange } : {})} current="map" {mapHref} {databaseHref} debugEnabled={$debugEnabled} ondebugchange={(enabled) => { debugEnabled.set(enabled); if (!enabled) debugOpen.set(false); }} mapBasemap={state.basemap} mapCameraPitch={$mapCameraPitch} mapControlsReady={$mapControlsReady} onmapbasemap={(value) => dispatch({ type: "basemap", value })} onmapviewtoggle={toggleMapCameraView} />{/if}
  <div class="workspace" use:measureWorkspace class:workspace-open={workspaceOpen && !$detailMapPreview} class:detail-active={showingDetail} style:--mobile-sheet-height={`${$sheetHeight}px`} style:--visual-workspace-height={`${$workspaceHeight}px`} style:--workspace-width={$railWidth === null ? `${$layoutTuning.panelWidthPercent}%` : `${$railWidth}px`} style:--result-row-padding={`${$layoutTuning.rowPadding}px`} style:--result-type-scale={$layoutTuning.typeScale}>
    <main class="map-stage" aria-label={tr('Investigative map field', $language)}>
    {#if mode === "synthetic" && state.scenario === "loading"}<div class="status" role="status">
        {tr('Loading records…', $language)}
      </div>{:else if mode === "synthetic" && state.scenario === "error"}<div
        class="status"
        role="alert"
      >
        {tr('Records unavailable. No live fallback was attempted.', $language)}
      </div>{:else if mode === "public-release" && dataStatus === "error" && records.length === 0}<div class="status" role="alert">{dataError}</div>{:else}<MapSurface
        {active}
        records={mapped}
        {state}
        {mode}
        {publicReleaseId}
        {publicReleaseIdentity}
        {publicReleaseManifestIdentity}
        {onMapFeedMeta}
        onCandidatePreviewLabel={(label) => { candidatePreviewLabel.set(label); onCandidatePreviewLabel?.(label); }}
        {mapStatus}
        {mapError}
        {mapTruncated}
        {mapDiagnostics}
        {mapMatchingIds}
        {mapMatchesStatus}
        {mapMatchesError}
        searchScope={state.searchScope}
        flightTarget={$flightTarget}
        cameraViewRequest={$cameraViewRequest}
        onCameraPitchChange={(pitch) => { mapCameraPitch.set(pitch); }}
        onMapControlsReady={(ready) => { mapControlsReady.set(ready); }}
        debugEnabled={$debugEnabled}
        layoutTuning={$layoutTuning}
        onLayoutTuningChange={updateLayoutTuning}
        onLayoutTuningReset={resetLayoutTuning}
        searchDiagnostics={{ total: candidateTotalCount, shown: resultCount, listStatus: dataStatus, matchesStatus: mapMatchesStatus, matchingMappedCount: mapMatchingIds?.length ?? null, scope: state.searchScope?.kind ?? null }}
        referenceLoading={aggregateLoading}
        onmaptiming={(timing) => onMapTiming?.(timing)}
        onselect={selectRecord}
        onaggregate={(ids) => dispatch({ type: "aggregate", value: ids })}
        onreference={(key, sourceId) => onMapReference?.(key, sourceId)}
        onbasemap={(value) => dispatch({ type: "basemap", value })}
        ondebugopenchange={(open) => debugOpen.set(open)}
        onviewport={(value) => dispatch({ type: "viewport", value })}
        onbounds={(bounds) => { currentBounds.set(bounds); onViewportBounds?.(bounds); }}
      />{/if}
    {#if (mode === "synthetic" && (state.scenario === "empty" || (state.scenario !== "loading" && state.scenario !== "error" && records.length === 0))) || (mode !== "synthetic" && dataStatus === "empty")}<div
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
    {#if (!workspaceOpen || $detailMapPreview) && !$debugOpen}<button
      class="search-toggle"
      bind:this={$searchToggle}
      type="button"
      aria-expanded={workspaceOpen}
      aria-controls="field-record-list"
      onclick={openMobileSearch}
      ><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg><span class="search-toggle-copy"><strong>{tr($detailMapPreview ? 'View facility details' : 'Search map', $language)}</strong><small>{state.query || state.sourceId ? tr('Search or filters active', $language) : tr('Places, facilities, sources', $language)}</small></span></button>{/if}
      {#if active}<MapNavigation viewport={state.viewport} ready={$mapControlsReady} areaEnabled={Boolean($currentBounds) && mode === 'public-release'} areaActive={state.searchScope?.kind === 'area'} onviewport={(value) => dispatch({ type: 'viewport', value })} onarea={searchArea} onlocate={(value) => dispatch({ type: 'private-camera', value })} />{/if}
    </main>
    <aside class="results" class:rail-collapsed={!workspaceOpen} class:map-preview={$detailMapPreview} id="field-record-list" aria-label={tr('Search, filters, and results', $language)}>
      <div class="mobile-sheet-control" hidden={showingDetail}><MobileSearchSheet open={workspaceOpen && !$detailMapPreview} detail={showingDetail} preview={$detailMapPreview} available={$workspaceHeight} middlePercent={$layoutTuning.mobileSheetPercent ?? 48} expandedPercent={$layoutTuning.mobileExpandedPercent ?? 90} onopen={openMobileSearch} oncollapse={collapseMobileSearch} onheight={height => sheetHeight.set(height)} /></div>
      <button class="rail-resize" type="button" aria-label="Resize search panel" title="Use left and right arrows to resize" onpointerdown={resizeRail} onkeydown={resizeRailKey}></button>
      <header hidden={Boolean(state.selectedId) || !workspaceOpen}><strong>{tr('Search records', $language)}</strong><button type="button" aria-label={tr('Close workspace', $language)} onclick={closeWorkspace}>×</button></header>
        <div class="search-tools" id="field-search-content" hidden={Boolean(state.selectedId) || !workspaceOpen}>
          <form class="search" role="search" onsubmit={(event) => { event.preventDefault(); applyParsedSearch(); }}>
            <label for="field-search">{tr(mode === "public-release" ? 'Search across public release records' : 'Search across preview records', $language)}</label>
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg>
            <input id="field-search" type="search" role="combobox" aria-autocomplete="list" aria-haspopup="listbox" maxlength="120" placeholder={tr('Name, activity, source, or place', $language)}
              value={state.query} aria-activedescendant={$autocompleteOpen && $suggestionIndex >= 0 ? `field-suggestion-${$suggestionIndex}` : undefined} aria-expanded={$autocompleteOpen && suggestions.length > 0} aria-controls="search-suggestions" onfocus={() => { autocompleteOpen.set(true); suggestionIndex.set(-1); }} onblur={(event) => { if (!(event.relatedTarget instanceof HTMLElement) || !event.relatedTarget.closest('.search-autocomplete')) autocompleteOpen.set(false); }} oninput={(event) => { autocompleteOpen.set(true); suggestionIndex.set(-1); dispatch({ type: 'search', value: { query: event.currentTarget.value, filters: state.filters } }); }} onkeydown={(event) => {
                if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && suggestions.length) { event.preventDefault(); autocompleteOpen.set(true); suggestionIndex.update(index => (index + (event.key === 'ArrowDown' ? 1 : -1) + suggestions.length) % suggestions.length); }
                if (event.key === 'Enter') { event.preventDefault(); if ($autocompleteOpen && $suggestionIndex >= 0 && suggestions[$suggestionIndex]) applySuggestion(suggestions[$suggestionIndex]!); else applyParsedSearch(); }
              }} />
          </form>
          {#if $autocompleteOpen && suggestions.length > 0}<div id="search-suggestions" class="search-autocomplete" role="listbox" aria-label={tr('Search suggestions', $language)}>
            {#each suggestions as suggestion, index (`${suggestion.kind}:${suggestion.value}`)}<button id={`field-suggestion-${index}`} role="option" aria-selected={$suggestionIndex === index} tabindex="-1" type="button" onclick={() => applySuggestion(suggestion)}><strong>{suggestion.label}</strong><small>{tr(suggestion.kind === 'country' ? 'Country' : suggestion.kind === 'category' ? 'Category' : 'Source', $language)}</small></button>{/each}
          </div>{/if}
          <div class="filter-chips" aria-label={tr('Search filters', $language)}>
            {#each state.filters.countries as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${countryName(value)}`} onclick={() => removeFilter('countries', value)}>{countryName(value)} <span aria-hidden="true">×</span></button>{/each}
            {#each state.filters.categories as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${categoryName(value)}`} onclick={() => removeFilter('categories', value)}>{categoryName(value)} <span aria-hidden="true">×</span></button>{/each}
            {#each state.filters.sources as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${sourceName(value)}`} onclick={() => removeFilter('sources', value)}>{sourceName(value)} <span aria-hidden="true">×</span></button>{/each}
            {#each state.filters.precisions as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${tr(value, $language)}`} onclick={() => removeFilter('precisions', value)}>{tr(value, $language)} <span aria-hidden="true">×</span></button>{/each}
            {#each state.filters.activities as value}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${value}`} onclick={() => removeFilter('activities', value)}>{value} <span aria-hidden="true">×</span></button>{/each}
            {#if state.sourceId}<button type="button" aria-label={`${tr('Remove filter', $language)}: ${sourceName(state.sourceId)}`} onclick={() => chooseSource(null)}>{sourceName(state.sourceId)} <span aria-hidden="true">×</span></button>{/if}
            {#if state.searchScope}<button type="button" aria-label={tr('Remove filter', $language)} onclick={() => dispatch({ type: 'scope', value: null })}>{state.searchScope.kind === 'area' ? tr('This map area', $language) : `${state.searchScope.radiusKm} km · ${state.searchScope.label}`} <span aria-hidden="true">×</span></button>{/if}
          </div>
          <div class="search-toolbar">
          <details class="filters" bind:this={$filterDisclosure} ontoggle={() => { if ($filterDisclosure?.open) autocompleteOpen.set(false); }}>
            <summary><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h7m5 0h4M4 17h3m5 0h8M11 4v6M7 14v6"/></svg>{tr('Filters', $language)} {#if activeFilters}<b>{activeFilters}</b>{/if}</summary>
            <div class="filter-sheet" use:fitFilterViewport>
              {#if mode === "candidate-preview" || mode === "public-release"}
                {#if facetsStatus === "loading"}<small>Loading filters…</small>
                {:else if facetsStatus === "error" || facetsStatus === "unauthorized"}<small role="alert">Filters are unavailable. Search remains available.</small>
                {:else if candidateFacets}
                  {#if mode === "public-release"}
                  <fieldset><legend>{tr('Activity category', $language)}</legend>{#each Object.entries(CATEGORY_PRESENTATIONS).filter(([key]) => key !== 'unclassified') as [key, presentation]}<label><input type="checkbox" checked={state.filters.categories.includes(key)} onchange={(event) => toggleCandidateFilter('categories', key, event.currentTarget.checked)} /><span class="category-swatch" style:background={presentation.color} aria-hidden="true"></span>{tr(presentation.label, $language)}</label>{/each}</fieldset>
                  <fieldset><legend>Country</legend>{#each candidateFacets.countries as facet (facet.value)}<label><input type="checkbox" checked={state.filters.countries.includes(facet.value)} onchange={(event) => toggleCandidateFilter('countries', facet.value, event.currentTarget.checked)} />{facet.label ?? facet.value} ({facet.count})</label>{/each}</fieldset>
                  {#if candidateFacets.activities.length}<fieldset><legend>Activity</legend>{#each candidateFacets.activities as facet (facet.value)}<label><input type="checkbox" checked={state.filters.activities.includes(facet.value)} onchange={(event) => toggleCandidateFilter('activities', facet.value, event.currentTarget.checked)} />{facet.label ?? facet.value} ({facet.count})</label>{/each}</fieldset>{/if}
                  <fieldset><legend>{tr('Location precision', $language)}</legend>{#each ['source_reported', 'approximate', 'unmapped', 'exact'] as value}<label><input type="checkbox" checked={state.filters.precisions.includes(value as Precision)} onchange={(event) => precision(value as Precision, event.currentTarget.checked)} />{tr(value === 'source_reported' ? 'Source-provided coordinates' : value === 'approximate' ? 'Approximate location' : value === 'unmapped' ? 'Unmapped' : 'Exact', $language)}</label>{/each}</fieldset>
                  <fieldset class="source-options"><legend>Source</legend>{#each candidateFacets.sources as facet (facet.value)}<label><input type="checkbox" checked={state.filters.sources.includes(facet.value)} onchange={(event) => toggleCandidateFilter('sources', facet.value, event.currentTarget.checked)} />{facet.label ?? facet.value} ({facet.count})</label>{/each}</fieldset>
                  {:else}
                  <fieldset><legend>Country</legend>{#each candidateFacets.countries as facet (facet.value)}<label><input type="checkbox" checked={state.filters.countries.includes(facet.value)} onchange={(event) => toggleCandidateFilter('countries', facet.value, event.currentTarget.checked)} />{facet.label ?? facet.value} ({facet.count})</label>{/each}</fieldset>
                  <fieldset class="source-options"><legend>Source</legend>{#each candidateFacets.sources as facet (facet.value)}<label><input type="checkbox" checked={state.filters.sources.includes(facet.value)} onchange={(event) => toggleCandidateFilter('sources', facet.value, event.currentTarget.checked)} />{facet.label ?? facet.value} ({facet.count})</label>{/each}</fieldset>
                  <fieldset><legend>Activity category</legend>{#each candidateFacets.categories as facet (facet.value)}<label><input type="checkbox" checked={state.filters.categories.includes(facet.value)} onchange={(event) => toggleCandidateFilter('categories', facet.value, event.currentTarget.checked)} />{facet.label ?? facet.value} ({facet.count})</label>{/each}</fieldset>
                  {#if candidateFacets.activities.length}<fieldset><legend>Activity</legend>{#each candidateFacets.activities as facet (facet.value)}<label><input type="checkbox" checked={state.filters.activities.includes(facet.value)} onchange={(event) => toggleCandidateFilter('activities', facet.value, event.currentTarget.checked)} />{facet.label ?? facet.value} ({facet.count})</label>{/each}</fieldset>{/if}
                  {/if}
                {/if}
              {:else if mode === "real-preview"}
                <fieldset class="source-filter">
                  <legend>Source</legend>
                  {#if facetsStatus === "loading"}<small>Loading sources…</small>
                  {:else if facetsStatus === "error" || facetsStatus === "unauthorized"}<small role="alert">Sources unavailable. Search remains available.</small>
                  {:else}
                    <label><input type="radio" name="source" checked={state.sourceId === null} onchange={() => chooseSource(null)} />All sources</label>
                    {#each sources as value}<label><input type="radio" name="source" checked={state.sourceId === value} onchange={() => chooseSource(value)} />{value}</label>{/each}
                  {/if}
                </fieldset>
              {:else}
                <p class="category-key"><i class="poultry"></i>Poultry <i class="pig"></i>Pig <i class="dairy"></i>Dairy <i class="processing"></i>Processing <i class="laboratory"></i>Lab <i class="aquaculture"></i>Aquaculture</p>
                <fieldset><legend>Category</legend>{#each categories as value}<label><input type="checkbox" checked={state.filters.categories.includes(value)} onchange={(event) => category(value, event.currentTarget.checked)} />{value}</label>{/each}</fieldset>
                <fieldset><legend>Location precision</legend>{#each precisions as value}<label><input type="checkbox" checked={state.filters.precisions.includes(value)} onchange={(event) => precision(value, event.currentTarget.checked)} />{value}</label>{/each}</fieldset>
              {/if}
              {#if activeFilters}<button type="button" class="clear-filters" onclick={clearSearch}>Clear all filters</button>{/if}
            </div>
          </details>
          {#if mode === 'public-release'}<a class="csv-download" href={downloadsHref} aria-label={tr('Download CSV', $language)} title={tr('Download CSV', $language)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M5 16v5h14v-5"/></svg><span>CSV</span></a>{/if}
          <div class="result-status"><strong class="sr-only">{aggregateOpen ? "Members" : "Facility records"}</strong><span role="status" aria-live="polite">{!aggregateOpen && listRefreshing ? (resultCount ? "Searching · showing previous results" : "Searching…") : !aggregateOpen && (dataStatus === "error" || dataStatus === "unauthorized") && resultCount ? "Search unavailable · showing previous results" : aggregateOpen ? `${resultCount} loaded` : (mode === "candidate-preview" || mode === "public-release") && candidateTotalCount !== null ? `${candidateTotalCount} matching · ${resultCount} shown` : `${resultCount} loaded`}</span></div>
          </div>
        </div>
      {#if $scopeError}<p class="search-error" hidden={Boolean(state.selectedId) || !workspaceOpen} role="alert">{$scopeError}</p>{/if}
      {#if mapMatchesStatus === 'error'}<p class="search-error" hidden={Boolean(state.selectedId) || !workspaceOpen} role="alert">{mapMatchesError} {#if onRetryMapMatches}<button type="button" onclick={() => onRetryMapMatches?.()}>{tr('Retry', $language)}</button>{/if}</p>{/if}
      <div class="workspace-body">
        <div class="list-content" hidden={Boolean(state.selectedId) || !workspaceOpen}>
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
          <section class="place-suggestions" aria-label="Places">
            <div class="results-heading"><strong>{tr('Places', $language)}</strong><label class="radius-choice">{tr('Radius', $language)} <select bind:value={$nearbyRadius}>{#each [5,25,50,100] as km}<option value={km}>{km} km</option>{/each}</select></label>{#if $placeSuggestions.length > 1}<button class="places-expand" type="button" aria-label={tr('Places', $language)} aria-expanded={$placesExpanded} onclick={() => placesExpanded.update(value => !value)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d={$placesExpanded ? 'm6 15 6-6 6 6' : 'm6 9 6 6 6-6'}/></svg></button>{/if}</div>
            <ol>
              {#each $placeSuggestions as place, index (place.id)}
                <li class:extra-place={index > 0 && !$placesExpanded}><button type="button" onclick={(event) => { event.stopPropagation(); selectPlace(place); }}>
                  <strong>{place.label}</strong>
                  <small>Navigate to city centre · Natural Earth, not a facility location</small>
                </button>{#if mode === 'public-release'}<button type="button" class="nearby-search" aria-label={`${tr('Search nearby', $language)}: ${place.label}, ${$nearbyRadius} km`} onclick={() => searchNear(place)}><span class="nearby-label">{tr('Search nearby', $language)} · </span>{$nearbyRadius} km</button>{/if}</li>
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
          </p>{/if}<RecordList
          records={aggregateRecords}
          selectedId={state.selectedId}
          onselect={selectSearchRecord}
        />{#if !aggregateOpen && !resultCount && !listRefreshing && (dataStatus === 'empty' || mode === 'synthetic')}<p class="list-empty" role="status">{tr('No records match this search and these filters.', $language)}</p>{/if}{#if aggregateOpen && aggregateLoading && !resultCount}<p class="list-empty" role="status">Loading members…</p>{/if}{#if mode !== "synthetic" && nextCursor && !aggregateOpen}<button
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
          </p>{:else if mode !== "synthetic" && (dataStatus === "unauthorized" || dataStatus === "error")}<p
            role="alert"
            class="search-error"
          >
            {dataError}
          </p>{/if}
        </div>
    {#if active && state.selectedId && mode !== "synthetic" && detailStatus === "loading"}<section
        class="reading-sheet dossier"
        role="status"
        aria-label="Record evidence" hidden={$detailMapPreview}
      >
        <header class="dossier-header"><button class="back-to-results" type="button" onclick={dismissSelection}>← {tr('Back to results', $language)}</button><button class="detail-close" type="button" aria-label="Close record detail" onclick={dismissSelection}>×</button></header>
        <p class="dossier-message">Loading record evidence…</p>
      </section>{:else if active && state.selectedId && mode !== "synthetic" && (detailStatus === "error" || detailStatus === "unauthorized")}<section
        class="reading-sheet dossier"
        role="alert"
        aria-label="Record evidence" hidden={$detailMapPreview}
      >
        <header class="dossier-header"><button class="back-to-results" type="button" onclick={dismissSelection}>← {tr('Back to results', $language)}</button><button class="detail-close" type="button" aria-label="Close record detail" onclick={dismissSelection}>×</button></header>
        <p class="dossier-message">{detailError}</p>
      </section>{:else if active && state.selectedId && selected}<section class="reading-sheet dossier" aria-label="Record evidence" hidden={$detailMapPreview}>
        <header class="dossier-header"><button class="back-to-results" type="button" onclick={dismissSelection}>← {tr('Back to results', $language)}</button><button class="detail-close" type="button" aria-label="Close record detail" onclick={dismissSelection}>×</button></header>
        {#if aggregateOpen}<button type="button" class="back" onclick={dismissSelection}>← Members</button>{/if}
        <RecordDetail record={selected} presentation="rail" fullRecordHref={facilityPageHref} publicRelease={mode === "public-release"} publicReleaseId={mode === "public-release" ? publicReleaseId : null} onshowmap={selected.latitude !== null && selected.longitude !== null ? showSelectedOnMap : undefined} oncategoryfilter={mode === 'public-release' ? (value) => detailFilter('categories', value) : undefined} onsourcefilter={mode === 'public-release' ? (value) => detailFilter('sources', value) : undefined} />
      </section>{/if}
      </div>
    </aside>
  </div>
</section>

<style>
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
  .search { display: flex; align-items: center; gap: .65rem; min-width: 0; height: 3.25rem; padding: 0 3.25rem 0 1rem; }
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
  .filter-sheet { position: absolute; z-index: 8; top: 100%; left: -1px; right: -1px; max-height: min(30rem, 58dvh); overflow: auto; overscroll-behavior: contain; padding: .25rem 1rem 1rem; border: 1px solid var(--line); background: var(--panel); box-shadow: 0 .7rem 1.5rem #0002; }
  .filter-sheet fieldset { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(11rem, 100%), 1fr)); gap: .1rem .75rem; margin: .8rem 0 0; padding: .6rem 0 0; border: 0; border-top: 1px solid var(--line); }
  .filter-sheet fieldset.source-options { grid-template-columns: minmax(0, 1fr); }
  .filter-sheet legend { padding: 0 .5rem 0 0; color: var(--muted); font-size: .75rem; font-weight: 500; }
  .filter-sheet label { display: flex; align-items: center; gap: .6rem; min-height: 2.75rem; padding: .3rem .1rem; font-size: .8rem; line-height: 1.4; overflow-wrap: anywhere; cursor: pointer; }
  .category-swatch { width: .5rem; height: .5rem; flex: none; border-radius: 50%; }
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
  .search-toggle-copy { display: grid; gap: .12rem; }
  .search-toggle-copy strong { font-size: .8125rem; font-weight: 500; }
  .search-toggle-copy small { color: var(--muted); font-size: .6875rem; }
  .results { position: absolute; z-index: 5; top: 1.5rem; bottom: 2rem; left: 1.5rem; display: flex; flex-direction: column; width: min(35rem, calc(100% - 3rem)); min-height: 0; border: 1px solid var(--line); background: var(--panel); }
  .rail-resize { position: absolute; z-index: 2; top: 0; right: -.45rem; bottom: 0; width: .9rem; padding: 0; border: 0; background: transparent; cursor: ew-resize; touch-action: none; }
  .rail-resize::after { content: ""; position: absolute; top: 45%; left: .34rem; width: 2px; height: 2.5rem; background: var(--muted); opacity: .6; }
  .results > header { position: absolute; z-index: 2; top: .25rem; right: .25rem; }
  .results > header button { display: grid; place-items: center; width: 2.75rem; height: 2.75rem; padding: 0; border: 0; color: var(--muted); background: transparent; font: 400 1.3rem/1 system-ui, sans-serif; cursor: pointer; }
  .results :global(.record-list) { flex: 1 1 auto; min-height: 0; overflow: auto; overscroll-behavior: contain; border: 0; background: transparent; }
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
  button:focus-visible, summary:focus-visible, a:focus-visible, .filter-sheet input:focus-visible { outline: 2px solid var(--ink); outline-offset: 3px; }
  .rail-resize:focus-visible { outline-offset: -3px; }
  .field-view [hidden] { display: none !important; }
  .workspace { position: relative; display: block; grid-template-columns: none; grid-template-rows: none; flex: 1 1 auto; min-height: 0; height: auto; border: 0; }
  .workspace-open { display: grid; grid-template-columns: minmax(0, var(--workspace-width)) minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); }
  .workspace .map-stage { width: 100%; height: 100%; min-width: 0; min-height: 0; }
  .workspace-open .map-stage { grid-column: 2; grid-row: 1; }
  .workspace .results { position: relative; inset: auto; grid-column: 1; grid-row: 1; width: 100%; max-width: none; min-width: 0; min-height: 0; border: 0; border-right: 1px solid var(--line); background: var(--panel); }
  .workspace .results > header { z-index: 5; }
  .workspace .results.rail-collapsed, .workspace .results.map-preview { display:none; }
  .mobile-sheet-control { display:none; }
  .results :global(.record-list strong) { font-size:calc(.9375rem * var(--result-type-scale,1)); }
  .results :global(.record-list small) { font-size:calc(.75rem * var(--result-type-scale,1)); }
  .workspace-body { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }
  .list-content { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; overflow: auto; overscroll-behavior: contain; }
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
  .filters { flex: 0 0 auto; }
  .filters summary { max-width: none; }
  .result-status { position: static; width: auto; min-width: 0; min-height: auto; margin-left: auto; padding: .25rem 0; text-align: right; font-size: .6875rem; }
  .csv-download { display: inline-flex; align-items: center; justify-content: center; gap: .3rem; flex: 0 0 auto; min-height: 2.75rem; padding: .3rem .4rem; color: var(--ink); text-decoration: none; font-size: .6875rem; }
  .csv-download:hover { background: var(--panel-hover); }
  .csv-download svg { width: .9rem; height: .9rem; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
  .places-expand { display: none; }
  .radius-choice { display: flex; align-items: center; gap: .35rem; color: var(--muted); font-size: .6875rem; }
  .radius-choice select { min-height: 2.25rem; padding: .25rem; border: 1px solid var(--line); border-radius: 0; color: var(--ink); background: var(--panel); font: inherit; }
  .place-suggestions .nearby-search { min-height: 2.75rem; padding-top: .25rem; color: var(--muted); font-size: .6875rem; text-decoration: underline; text-underline-offset: .2rem; }
  @media (max-width: 60rem) {
    .search-toolbar { flex-wrap: wrap; gap: 0 .25rem; }
    .result-status { flex: 1 1 5rem; }
    .workspace .dossier-header .back-to-results { flex: 1 1 calc(100% - 3.5rem); }
    .workspace .dossier-header > button:last-child { flex: 0 0 2.75rem; }
  }
  @media (max-width: 40rem) {
    .workspace, .workspace-open { display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(0,1fr) minmax(0,var(--mobile-sheet-height,56px));flex:0 1 var(--visual-workspace-height);height:var(--visual-workspace-height);max-height:var(--visual-workspace-height); }
    .workspace .map-stage, .workspace-open .map-stage { grid-column:1;grid-row:1; }
    .workspace .results { grid-column:1;grid-row:2;border-right:0;border-top:1px solid var(--line);border-radius:12px 12px 0 0; }
    .workspace .results.rail-collapsed, .workspace .results.map-preview { display:flex; }
    .mobile-sheet-control { display:block;flex:0 0 auto; }
    .workspace.detail-active .results { position:absolute;inset:0;grid-row:1 / -1;grid-column:1 / -1;z-index:20;width:100%;max-height:none;border:0;border-radius:0;padding:0 env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left); }
    .workspace .reading-sheet.dossier { position: relative; inset: auto; width: 100%; height: auto; max-height: none; padding: 0; }
    .search-toggle { display:none; }
    .workspace .results > header { top:2.9rem; }
    .workspace .results.rail-collapsed .workspace-body,.workspace .results.map-preview .workspace-body { display:none; }
    .rail-resize { display: none; }
    .search input { font-size: 1rem; }
    .filter-sheet { --filter-safe-bottom:env(safe-area-inset-bottom);position:absolute;top:100%;max-height:min(45dvh,22rem,var(--filter-available-height,45dvh)); }
    .filter-sheet label { min-height: 2.75rem; }
    .workspace .aggregate-sheet dl, .workspace .aggregate-sheet .evidence-note, .workspace .aggregate-sheet .open-members { display: block; }
    .place-suggestions .results-heading { min-height: 2.75rem; gap: .4rem; padding: 0 .65rem; }
    .radius-choice { margin-left: auto; }
    .radius-choice select { min-height: 2.75rem; }
    .places-expand { display: grid; place-items: center; min-width: 2.75rem; min-height: 2.75rem; padding: .4rem; border: 0; color: var(--ink); background: transparent; }
    .places-expand svg { width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-width: 1.5; }
    .place-suggestions .extra-place { display: none; }
    .place-suggestions li { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
    .place-suggestions li > button { min-width: 0; min-height: 2.75rem; padding: .45rem .65rem; }
    .place-suggestions strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .place-suggestions small { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
    .place-suggestions .nearby-search { padding: .45rem .65rem; }
    .nearby-label { display: none; }
    .workspace .dossier-header { padding-top: .35rem; }
    .filter-chips button { min-height:2.75rem;font-size:.75rem; }
    .result-status,.csv-download { font-size:.75rem; }
    .search-toolbar { gap:0 .4rem;padding-right:.75rem; }
  }
  @media (pointer: coarse) { .filter-chips button { min-height: 2.75rem; } }
</style>
