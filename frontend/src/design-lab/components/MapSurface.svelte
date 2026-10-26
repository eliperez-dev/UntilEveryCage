<script lang="ts">
  import { language, tr } from '../../app/language';
  import MapDebugPanel from './MapDebugPanel.svelte';
  import { safeDiagnosticSnapshot, mapFeedCacheDiagnostics, publicMapLoadingLabel, indexCacheReasonLabel, type CacheTuning, type LayoutTuning, type SearchDiagnostics, type WorldCacheTuning } from './mapDebug';
  import { clearClusterIndexCache, trimClusterIndexCache, INDEX_CACHE_CHANNEL, INDEX_CACHE_FIELD, type IndexCacheDiagnostic } from '../../map/clusterIndexCache';
  import { clearTileCache, getTileCacheDiagnostics, getTileCacheSettings, resetTileCacheSettings, setTileCachePersistenceAllowed, subscribeTileCacheDiagnostics, updateTileCacheSettings } from '../../map/tileCache';
  import { updateMapTileMemoryCache } from '../../map/mapTileMemoryCache';
  import { BASE_RASTER_FADE_MS } from '../../map/baseMapStyle';
  import { applyWorldBaselineBasemap, applyWorldBaselineOpacity, getWorldBaselineSettings, updateWorldBaselineSettings, resetWorldBaselineSettings, getWorldBaselineDiagnostics, subscribeWorldBaselineDiagnostics, warmWorldBaseline, cancelWorldBaselineWarmup, clearWorldBaselineCache } from '../../map/worldBaseline';
  import { syncSelectionOverlayWhenReady } from './selectionOverlay';
  import { waitForTerrainSource } from './terrainReady';
  import { settleTerrainSelection, useCameraZoomLod, type CameraLodSource } from './selectionCamera';
  /**
   * MapSurface is the composition boundary:
   * This component owns MapLibre event wiring. The private preview uses one
   * in-memory native cluster source; camera movement must never reload it.
   * Synthetic fixtures retain their own transition controller.
   */
  import { onMount, tick } from "svelte";
  import * as maplibregl from "maplibre-gl";
  import mapLibreWorkerUrl from "../../map/persistentMapWorker.ts?worker&url";
  import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
  import "maplibre-gl/dist/maplibre-gl.css";
  import type {
    LabRecord,
    LabState,
    Basemap,
    MapDiagnostics,
    MapTiming,
    Viewport,
    ViewportBounds,
  } from "../contract";
  import { MvtMotionController } from "./mvtMotionController";
  import { JsonClusterMotionController } from "./jsonClusterMotionController";
  import { NativeClusterMotionController, DEFAULT_CLUSTER_MOTION_MS, DEFAULT_CLUSTER_MOTION_LIMIT } from './nativeClusterMotion';
  import {
    addJsonLocationLayers,
    createJsonMapCollection,
    loadJsonFallbackImages,
    setJsonFallbackData,
  } from "./jsonMapFallback";
  import type { JsonMapCollection } from "./jsonMapFallback";
  import {
    addMvtLocationLayers,
    baseRasterPaint,
    createSelectedApproximateReferenceArea,
    createSearchRadiusArea,
    createMvtReferenceAreas,
    createBaseStyle,
    removeLocationLayers,
    setMvtClusterCutoff,
  } from "./mapSurfaceLayers";
  import {
    addRealPreviewMapLayers,
    APPROX_MARKER_SCALE,
    applyRealPreviewVisualSettings,
    DEFAULT_CLUSTER_MAX_ZOOM,
    DEFAULT_CLUSTER_RADIUS,
    DEFAULT_REFERENCE_RADIUS_KM,
    nativeClusterMaxZoom,
    setClusterTileRounding,
    useRoundedClusterTiles,
    setRealPreviewMapData,
    setRealPreviewCategoryFilter,
    setRealPreviewPinMode,
    hasRealPreviewMapLayers,
  } from "./realPreviewMapLayers";
  import { clearRealPreviewMapCache, createRealPreviewMapFeedRepository, RealPreviewMapFeedError, realPreviewMapCacheEntryCount } from "../../api/RealPreviewMapFeedRepository";
  import { clearTestReleaseMapCache, createTestReleaseMapFeedRepository, filterTestReleaseMapCollection, testReleaseMapCacheEntryCount } from "../../api/TestReleaseMapFeedRepository";
  import { canReusePublicMapFeed, clearPublicMapCache, createPublicMapFeedRepository, publicMapCacheEntryCount } from "../../api/PublicMapFeedRepository";
  import { TERRAIN_EXAGGERATION, TERRAIN_SOURCE, TERRAIN_SOURCE_ID } from "../../map/terrain";
  import { CLUSTERING_POPULATION_THRESHOLD, clusterFilteredPopulation, maskPublicMapMatches, representedMappedCount, resizeWorkspaceMap } from './mapWorkspace';

  let {
    active = true,
    records,
    state: mapState,
    mode = "synthetic",
    publicReleaseId,
    publicReleaseIdentity,
    publicReleaseManifestIdentity,
    onMapFeedMeta,
    onCandidatePreviewLabel,
    mapStatus = "idle",
    mapError = "",
    mapTruncated = false,
    mapMatchingIds = null,
    mapMatchesStatus = 'idle',
    mapMatchesError = '',
    searchScope = null,
    mapDiagnostics,
    referenceLoading = false,
    flightTarget = null,
    suppressDiagnostics = false,
    debugEnabled = false,
    searchDiagnostics,
    layoutTuning = { panelWidthPercent: 100 / 3, rowPadding: 16, typeScale: 1 },
    onLayoutTuningChange,
    onLayoutTuningReset,
    onmaptiming,
    onselect,
    onaggregate,
    onreference,
    onbasemap,
    cameraViewRequest = null,
    onCameraPitchChange,
    onMapControlsReady,
    ondebugopenchange,
    onviewport,
    onbounds,
  }: {
    active?: boolean;
    records: readonly LabRecord[];
    state: LabState;
    mode?: "synthetic" | "real-preview" | "candidate-preview" | "public-release";
    publicReleaseId?: string | null;
    publicReleaseIdentity?: string | null;
    publicReleaseManifestIdentity?: import('../../api/PublicReleaseRepository').PublicReleaseIdentity | null;
    onMapFeedMeta?: ((meta: import('../../api/PublicMapFeedRepository').PublicMapFeed['meta'] | null) => void) | undefined;
    onCandidatePreviewLabel?: ((label: string | null) => void) | undefined;
    mapStatus?:
      | "idle"
      | "loading"
      | "ready"
      | "empty"
      | "error"
      | "unauthorized";
    mapError?: string;
    mapTruncated?: boolean;
    mapMatchingIds?: readonly string[] | null;
    mapMatchesStatus?: 'idle' | 'loading' | 'ready' | 'error';
    mapMatchesError?: string;
    searchScope?: null | Readonly<{ kind: 'area'; bounds: ViewportBounds }> | Readonly<{ kind: 'radius'; label: string; latitude: number; longitude: number; radiusKm: number }>;
    mapDiagnostics?: MapDiagnostics | undefined;
    referenceLoading?: boolean;
    flightTarget?: Readonly<{ id: number; longitude: number; latitude: number; zoom: number }> | null;
    suppressDiagnostics?: boolean;
    debugEnabled?: boolean;
    searchDiagnostics?: SearchDiagnostics;
    layoutTuning?: LayoutTuning;
    onLayoutTuningChange?(value: LayoutTuning): void;
    onLayoutTuningReset?(): void;
    onmaptiming?(timing: MapTiming): void;
    onselect(id: string): void;
    onaggregate(memberIds: readonly string[]): void;
    onreference?(key: string, sourceId?: string): void;
    onbasemap(value: Basemap): void;
    cameraViewRequest?: Readonly<{ id: number; enable3d: boolean }> | null;
    onCameraPitchChange?(pitch: number): void;
    onMapControlsReady?(ready: boolean): void;
    ondebugopenchange?(open: boolean): void;
    onviewport(value: Viewport): void;
    onbounds?(bounds: ViewportBounds): void;
  } = $props();
  let host: HTMLDivElement;
  let map: MapLibreMap | undefined;
  let nativeStyleReady = $state(false);
  let resumePending = false;
  let lifecyclePaused = false;
  let nativeStyleGeneration = 0;
  let appliedBasemap = $state<Basemap | undefined>();
  let cameraPitch = $state(0);
  let handledCameraViewRequestId = 0;
  let terrainEnabled = $state(false);
  let terrainError = $state("");
  let terrainPending = $state(false);
  let terrainViewGeneration = 0;
  let terrainViewAbort: AbortController | undefined;
  let terrainRetryRequired = false;
  let basemapSwitching = $state(false);
  let pendingBasemap = $state<Basemap | undefined>();
  let basemapError = $state("");
  let basemapRequest = 0;
  let syncing = false;
  let activeFlight = false;
  let handledFlightId = 0;
  let selectionFocus: { id: string; center: [number, number] } | null = null;
  let pendingSelectionFocus: [number, number] | null = null;
  let settlingSelectionFocus = false;
  let interactionsBound = false;
  let mvtError = $state("");
  let rendererUnavailable = $state(false);
  const mapFeedRepository = createRealPreviewMapFeedRepository();
  const candidateMapFeedRepository = createTestReleaseMapFeedRepository();
  const publicMapFeedRepository = createPublicMapFeedRepository();
  let feedAbort: AbortController | undefined;
  let feedGeneration = 0;
  // A rejected configured-candidate envelope is deterministic for the current
  // release. Keep the error visible instead of having the reactive source
  // effect repeatedly request the same invalid projection.
  let candidateValidationFailed = false;
  let requestedFeedSourceId: string | null | undefined;
  let requestedPublicReleaseId: string | null | undefined;
  let requestedPublicReleaseIdentity: string | null | undefined;
  let nativeFullCollection: JsonMapCollection | undefined;
  let syncedApproximateAreaSource: GeoJSONSource | undefined;
  let syncedApproximateAreaKey: string | null | undefined;
  let syncedApproximateAreaCollection: JsonMapCollection | undefined;
  // Viewport updates replace `state`; only a changed source filter may rebuild
  // the native Supercluster index from the already-loaded map projection.
  let appliedNativeSourceId: string | null | undefined;
  let appliedNativeFilterSignature: string | undefined;
  let appliedMatchingIds: readonly string[] | null | undefined;
  let appliedMatchesStatus: typeof mapMatchesStatus | undefined;
  let appliedNativeClustering: boolean | undefined;
  let visibleNativeCollection: JsonMapCollection | undefined;
  const matchingIdSet = $derived(mapMatchingIds === null ? null : new Set(mapMatchingIds));
  let appliedMvtTileSignature: string | undefined;
  let feedStatus = $state<"loading" | "ready" | "error">("loading");
  // These are milestones, not a guessed byte or worker percentage.
  let startupStage = $state<"initializing" | "fetching" | "indexing" | "rendering" | "ready">("initializing");
  let pendingReference = $state<
    | Readonly<{ key: string; count: number; observedLoading: boolean }>
    | undefined
  >();
  let boundsTimer: ReturnType<typeof setTimeout> | undefined;
  let zoomStartedAt: number | null = null;
  let zoomSettleMs = $state<number | null>(null);
  let nativeFeedRequests = $state(0);
  let nativeSnapshotId = $state("Not loaded");
  let nativeCacheStatus = $state("unavailable");
  let nativeCacheEntries = $state<number | null>(null);
  let nativeDecodedBytes = $state<number | null>(null);
  let cacheClearStatus = $state("");
  let selectedReferenceKey = $state<string | null>(null);
  let nativeFeedMs = $state<number | null>(null);
  let nativeIndexMs = $state<number | null>(null);
  let nativeIndexUpdates = $state(0);
  const indexCacheSession = crypto.randomUUID();
  const initialTileCache = getTileCacheSettings();
  const defaultCacheTuning: CacheTuning = { indexEnabled: true, indexMaxMiB: 64,
    tileEnabled: initialTileCache.enabled, tileMaxMiB: initialTileCache.maxBytes / 1048576,
    tileMaxEntries: initialTileCache.maxEntries, tileTtlHours: initialTileCache.maxTtlMs / 3600000,
    ramTiles: 128, baselineOpacity: 1, tileFadeMs: BASE_RASTER_FADE_MS };
  let cacheTuning = $state<CacheTuning>({ ...defaultCacheTuning });
  let indexCacheDiagnostic = $state<IndexCacheDiagnostic | null>(null);
  let tileCacheDiagnostic = $state(getTileCacheDiagnostics());
  const initialWorldCache = getWorldBaselineSettings();
  let worldTuning = $state<WorldCacheTuning>({ enabled: initialWorldCache.enabled, maxZoom: initialWorldCache.maxZoom, maxMiB: initialWorldCache.maxBytes / 1048576 });
  let worldCacheDiagnostic = $state(getWorldBaselineDiagnostics());
  let indexCacheChannel: BroadcastChannel | undefined;
  let nativeRebuildMs = $state<number | null>(null);
  let nativeUnitCount = $state(0);
  let nativeRepresentedCount = $state(0);
  let nativeApproximateCount = $state(0);
  let nativeRenderedCount = $state<number | null>(null);
  let nativeCameraMoveendMs = $state<number | null>(null);
  let nativeCameraIdleMs = $state<number | null>(null);
  let nativeBasemapPendingAtMoveend = $state(false);
  let nativeOverlayPendingAtMoveend = $state(false);
  let nativeCameraStartedAt: number | null = null;
  let nativeIndexStartedAt: number | null = null;
  let hadAggregateInspection = false;
  let mvtCameraStartedAt: number | null = null;
  let mvtResourceWindowStart = 0;
  let mvtInitialStartedAt = 0;
  let mvtSourceReadyMs = $state<number | null>(null);
  let mvtCameraSettleMs = $state<number | null>(null);
  let mvtSourceReady = $state(false);
  let mvtLoadedTileResources = $state(0);
  let mvtTransferBytes = $state<number | null>(null);
  let mvtRequestDurationMs = $state<number | null>(null);
  let mvtRenderedFeatureCount = $state<number | null>(null);
  // The MVT canvas transaction state is intentionally outside Svelte. MapSurface
  // only connects it to MapLibre's lifecycle events.
  let mvtMotionController: MvtMotionController | undefined;
  let jsonMotionController: JsonClusterMotionController | undefined;
  let nativeMotionController: NativeClusterMotionController | undefined;
  const mapped = $derived(
    records.filter(
      (record) => record.latitude !== null && record.longitude !== null,
    ),
  );
  let featureListOpen = $state(false);
  let diagnosticsOpen = $state(false);
  let mvtAccessibleFeatures = $state<ReadonlyArray<{ key: string; label: string; kind: "coordinate" | "reference" }>>([]);
  let diagnosticsToggle = $state<HTMLButtonElement>();
  let clusterRadius = $state(DEFAULT_CLUSTER_RADIUS);
  let clusterMaxZoom = $state(DEFAULT_CLUSTER_MAX_ZOOM);
  let clusterEnabledOverride = $state<boolean | null>(null);
  let filteredMappedCount = $state(0);
  let referenceRadiusKm = $state<number>(DEFAULT_REFERENCE_RADIUS_KM);
  let referenceOpacity = $state(0.22);
  let visibleApproximateCount = $state(0);
  let coordinateRadius = $state(6.5);
  let pinScale = $state(1);
  let debugDimensions = $state({ width: 0, height: 0, canvasWidth: 0, canvasHeight: 0 });
  let showReferenceLabels = $state(false);
  // Exact locations default to the retained V1 pin family. The toggle remains
  // available for focused renderer diagnostics, but dots are not the normal
  // visitor-facing representation.
  let useV1Pins = $state(true);
  let pinModeError = $state("");
  let clusterZoomDuration = $state(460);
  let clusterMotionDuration = $state(DEFAULT_CLUSTER_MOTION_MS);
  let clusterMotionLimit = $state(DEFAULT_CLUSTER_MOTION_LIMIT);
  let clusterRebuildDebounce = $state(150);
  let clusterSettingsError = $state("");
  let roundedClusterTilesAvailable = $state(true);
  let clusterUpdateTimer: ReturnType<typeof setTimeout> | undefined;
  const accessibleAggregates = $derived.by(() => {
    const groups = new Map<string, LabRecord[]>();
    for (const record of mapped) {
      if (record.precision !== "city" && record.precision !== "coarse")
        continue;
      const key = `${record.country}\u0000${record.locality}\u0000${record.precision}`;
      const members = groups.get(key);
      if (members) members.push(record);
      else groups.set(key, [record]);
    }
    return [...groups.values()].map((members) => ({
      name: members[0]!.locality,
      precision: members[0]!.precision,
      members,
    }));
  });
  // Do not collapse a whole source into an arbitrary first record: every listed item
  // corresponds to one actual visible source-coordinate feature.
  const approximateSourceFeatures = $derived(
    featureListOpen
      ? mapped
          .filter(
            (record) => record.precision === "approximate" && record.sourceId,
          )
          .sort((a, b) =>
            `${a.sourceId}\u0000${a.locality}\u0000${a.id}`.localeCompare(
              `${b.sourceId}\u0000${b.locality}\u0000${b.id}`,
            ),
          )
      : [],
  );
  const hasMapFeatures = $derived(
    mapped.some(
      (record) =>
        record.precision === "approximate" ||
        record.precision === "city" ||
        record.precision === "coarse",
    ),
  );
  const accessibleFeatures = $derived.by(() =>
    featureListOpen
      ? [
          ...approximateSourceFeatures.map((record) => ({
            kind: "coordinate" as const,
            label: `Source coordinate · ${record.sourceId} · ${record.locality}`,
            record,
          })),
          ...accessibleAggregates.map((aggregate) => ({
            kind: "aggregate" as const,
            label: `Approximate ${aggregate.precision} · ${aggregate.name} · ${aggregate.members.length} records`,
            members: aggregate.members,
          })),
        ].slice(0, 80)
      : [],
  );
  const diagnosticsEnabled = $derived(mode !== "synthetic" && debugEnabled);
  const isRealPreview = () => mode === "real-preview" || mode === "candidate-preview";
  const isNativeMap = () => mode !== "synthetic";
  // The private development preview intentionally uses the reviewed, in-memory
  // GeoJSON/Supercluster path. The server-generated MVT implementation remains
  // available for public releases and future experiments, but must not sit in
  // the camera interaction path for this preview.
  const usingMvt = false;
  maplibregl.setWorkerUrl(mapLibreWorkerUrl);

  function style(): any {
    return createBaseStyle(mapState.basemap);
  }
  function setTerrain(enabled: boolean, explicitRetry = false): void {
    const instance = map;
    if (!instance) return;
    if (!enabled) {
      instance.setTerrain(null);
      if (instance.getSource(TERRAIN_SOURCE_ID)) instance.removeSource(TERRAIN_SOURCE_ID);
      terrainEnabled = false;
      return;
    }
    if (terrainRetryRequired && !explicitRetry) return;
    try {
      const activeTerrain = instance.getTerrain();
      if (activeTerrain?.source === TERRAIN_SOURCE_ID && instance.getSource(TERRAIN_SOURCE_ID)) {
        terrainEnabled = true;
        return;
      }
      if (!instance.getSource(TERRAIN_SOURCE_ID)) instance.addSource(TERRAIN_SOURCE_ID, TERRAIN_SOURCE as any);
      instance.setTerrain({ source: TERRAIN_SOURCE_ID, exaggeration: TERRAIN_EXAGGERATION });
      terrainEnabled = true;
      terrainError = "";
      terrainRetryRequired = false;
    } catch {
      if (instance.getTerrain()) instance.setTerrain(null);
      if (instance.getSource(TERRAIN_SOURCE_ID)) instance.removeSource(TERRAIN_SOURCE_ID);
      terrainEnabled = false;
      terrainError = "Terrain could not be loaded. The map is shown flat.";
      terrainRetryRequired = true;
      instance.easeTo({ pitch: 0, duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 300 });
    }
  }
  async function setCameraView(enable3d: boolean): Promise<void> {
    const instance = map;
    if (!instance || !active) return;
    const generation = ++terrainViewGeneration;
    terrainViewAbort?.abort();
    terrainPending = false;
    if (!enable3d && cameraPitch <= 0.5) return;
    terrainError = "";
    if (enable3d) {
      setTerrain(true, true);
      if (!terrainEnabled) return;
      const controller = new AbortController();
      terrainViewAbort = controller;
      terrainPending = !instance.isSourceLoaded(TERRAIN_SOURCE_ID);
      // The first elevation change happens overhead. Tilting before the DEM
      // arrives makes the same location visibly jump up the screen afterward.
      const ready = await waitForTerrainSource(instance, TERRAIN_SOURCE_ID, controller.signal);
      if (generation !== terrainViewGeneration || map !== instance || controller.signal.aborted) return;
      terrainPending = false;
      if (!ready || !terrainEnabled) {
        setTerrain(false);
        terrainRetryRequired = true;
        terrainError = "Terrain tiles are unavailable. The map is shown flat.";
        return;
      }
      if (selectionFocus?.id === mapState.selectedId) {
        pendingSelectionFocus = selectionFocus.center;
        settlePendingSelectionFocus();
      }
    }
    // Keep healthy terrain in overhead mode once activated. Removing it would
    // reset the camera elevation to sea level and change the geographic focus.
    const center = instance.getCenter();
    instance.easeTo({ center: [center.lng, center.lat], zoom: instance.getZoom(), bearing: instance.getBearing(),
      pitch: enable3d ? 45 : 0, duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 450 });
  }
  $effect(() => {
    const request = cameraViewRequest;
    if (!active || !map || !nativeStyleReady || !request || request.id <= handledCameraViewRequestId) return;
    handledCameraViewRequestId = request.id;
    void setCameraView(request.enable3d);
  });
  function updateCameraPitch(pitch: number): void {
    cameraPitch = pitch;
    onCameraPitchChange?.(pitch);
  }
  function settlePendingSelectionFocus(): void {
    const instance = map, center = pendingSelectionFocus;
    if (!active || !instance || !center || instance.isMoving() || settlingSelectionFocus) return;
    settlingSelectionFocus = true;
    try { if (settleTerrainSelection(instance, center)) pendingSelectionFocus = null; }
    finally { settlingSelectionFocus = false; }
  }
  function rasterTiles(basemap: Basemap): string[] {
    return ((createBaseStyle(basemap) as any).sources.base.tiles as string[]);
  }
  function basemapLabel(basemap: Basemap): string {
    return basemap === "satellite" ? "Satellite" : basemap === "muted" ? "Muted Street" : "Street";
  }
  function applyBaseAppearance(instance: MapLibreMap, basemap: Basemap): void {
    const paint = baseRasterPaint(basemap);
    for (const property of ["raster-saturation", "raster-contrast", "raster-brightness-min", "raster-brightness-max"] as const)
      instance.setPaintProperty("base", property, paint[property]);
    instance.setPaintProperty("transport", "raster-opacity", basemap === "satellite" ? 0.72 : 0);
  }
  /** A source can report loaded after an error, so tile failures reject the handoff. */
  function waitForRaster(instance: MapLibreMap, sourceId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      let settled = false;
      const timeout = setTimeout(() => finish(false), 10000);
      const onError = (event: any) => {
        if (event?.sourceId === sourceId) finish(false);
      };
      const onData = (event: any) => {
        if (event?.sourceId === sourceId && instance.isSourceLoaded(sourceId))
          finish(true);
      };
      function finish(ok: boolean) {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        instance.off("error", onError);
        instance.off("sourcedata", onData);
        ok ? resolve() : reject(new Error("Basemap tiles unavailable"));
      }
      instance.on("error", onError);
      instance.on("sourcedata", onData);
      if (instance.isSourceLoaded(sourceId)) finish(true);
    });
  }
  async function applyBasemapTiles(basemap: Basemap) {
    const instance = map;
    if (!active || !instance || basemapSwitching || appliedBasemap === basemap) return;
    // Street and Muted Street share one OSM source. Only paint changes.
    if (basemap !== "satellite" && appliedBasemap !== "satellite") {
      applyBaseAppearance(instance, basemap);
      appliedBasemap = basemap;
      basemapError = "";
      onbasemap(basemap);
      return;
    }
    const request = ++basemapRequest;
    nativeMotionController?.cancel();
    basemapSwitching = true;
    pendingBasemap = basemap;
    basemapError = "";
    const previous = appliedBasemap ?? "vector";
    let baseChanged = false;
    try {
      // The candidate loads beneath transport and every location layer while
      // the current base stays visible. Selection and MVT sources are untouched.
      instance.addSource("candidate-base", {
        type: "raster",
        tiles: rasterTiles(basemap),
        tileSize: 256,
      });
      useCameraZoomLod(instance.getSource("candidate-base") as CameraLodSource);
      instance.addLayer(
        { id: "candidate-base", type: "raster", source: "candidate-base", paint: { 'raster-fade-duration': 0 } },
        "transport",
      );
      await waitForRaster(instance, "candidate-base");
      if (request !== basemapRequest || map !== instance) return;
      const base = instance.getSource("base") as any;
      if (typeof base?.setTiles !== "function") throw new Error("Basemap source cannot switch");
      base.setTiles(rasterTiles(basemap));
      baseChanged = true;
      await waitForRaster(instance, "base");
      if (request !== basemapRequest || map !== instance) return;
      applyBaseAppearance(instance, basemap);
      // Source-loaded precedes the raster's first fade completing. Keep the
      // opaque candidate covering the base until that bounded transition ends.
      if (!terrainEnabled && cacheTuning.tileFadeMs > 0)
        await new Promise<void>(resolve => setTimeout(resolve, cacheTuning.tileFadeMs));
      if (request !== basemapRequest || map !== instance) return;
      appliedBasemap = basemap;
      onbasemap(basemap);
    } catch {
      if (map === instance) {
        if (baseChanged) {
          (instance.getSource("base") as any)?.setTiles?.(rasterTiles(previous));
          try { await waitForRaster(instance, "base"); } catch { /* keep the last selected mode */ }
        }
        onbasemap(previous);
        basemapError = `${basemapLabel(basemap)} imagery is unavailable. ${basemapLabel(previous)} remains selected.`;
      }
    } finally {
      if (map === instance) {
        if (instance.getLayer("candidate-base")) instance.removeLayer("candidate-base");
        if (instance.getSource("candidate-base")) instance.removeSource("candidate-base");
      }
      if (request === basemapRequest) {
        basemapSwitching = false;
        pendingBasemap = undefined;
      }
    }
  }
  function setData() {
    if (usingMvt) return;
    jsonMotionController?.cancel();
    const source = map?.getSource("locations") as GeoJSONSource | undefined;
    if (!source || !map) return;
    const startedAt = performance.now();
    if (mode === "public-release") return;
    const data = createJsonMapCollection(mapped, mode === "candidate-preview" ? "real-preview" : mode);
    setJsonFallbackData(map, data);
    const sourceMaterializeMs = Math.round(performance.now() - startedAt);
    onmaptiming?.({
      sourceMaterializeMs,
      clusterReadyMs: null,
      sourceFeatureCount: data.features.length,
      zoomSettleMs,
    });
    // `idle` waits for MapLibre's worker/source work to settle, so diagnostics make
    // cluster-index latency visible rather than conflating it with request time.
    const instance = map;
    instance.once("idle", () => {
      if (map === instance)
        onmaptiming?.({
          sourceMaterializeMs,
          clusterReadyMs: Math.round(performance.now() - startedAt),
          sourceFeatureCount: data.features.length,
          zoomSettleMs,
        });
    });
  }
  function clusterImage(outerColor: string, innerColor: string) {
    const size = 44,
      canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d")!;
    context.beginPath();
    context.arc(22, 22, 20, 0, Math.PI * 2);
    context.fillStyle = outerColor;
    context.fill();
    context.beginPath();
    context.arc(22, 22, 15, 0, Math.PI * 2);
    context.fillStyle = innerColor;
    context.fill();
    return context.getImageData(0, 0, size, size);
  }
  function loadClusterImages() {
    if (!map) return;
    // Cluster body and count deliberately live in one symbol layer. This prevents the
    // old circle-layer/symbol-layer race that left count text visible for a frame.
    // Cluster colors express size only; category colors stay on facility pins.
    // Blue distinguishes approximate-only groups and outlines mixed precision.
    if (!map.hasImage("cluster-low"))
      map.addImage("cluster-low", clusterImage("#b5e28c99", "#6ecc39b8"));
    if (!map.hasImage("cluster-mid"))
      map.addImage("cluster-mid", clusterImage("#f1d35799", "#f0c20cb8"));
    if (!map.hasImage("cluster-high"))
      map.addImage("cluster-high", clusterImage("#fd9c7399", "#f18017b8"));
    if (!map.hasImage("cluster-very-high"))
      map.addImage("cluster-very-high", clusterImage("#ed8b7599", "#de6d3fb8"));
    if (!map.hasImage("reference-marker"))
      map.addImage("reference-marker", clusterImage("#ff695ce6", "#d8473fe6"));
  }
  function scheduleClusterSettings() {
    nativeMotionController?.cancel();
    if (clusterUpdateTimer) clearTimeout(clusterUpdateTimer);
    clusterUpdateTimer = setTimeout(async () => {
      if (usingMvt && map) {
        try {
          setMvtClusterCutoff(map, mapState.sourceId ?? undefined, clusterMaxZoom);
          appliedMvtTileSignature = `${mapState.sourceId ?? ""}:${clusterMaxZoom}`;
          clusterSettingsError = "";
        } catch {
          clusterSettingsError = "The server-generated tile hierarchy could not be updated.";
        }
        return;
      }
      const source = isNativeMap() ? map?.getSource("locations") as GeoJSONSource | undefined : undefined;
      if (!source) return;
      try {
        const startedAt = performance.now();
        roundedClusterTilesAvailable = setClusterTileRounding(map!, clusterMaxZoom);
        nativeIndexUpdates++;
        await source.setClusterOptions({
          cluster: clusterEnabledOverride ?? filteredMappedCount >= CLUSTERING_POPULATION_THRESHOLD,
          clusterRadius,
          clusterMaxZoom: nativeClusterMaxZoom(clusterMaxZoom),
        });
        appliedNativeClustering = clusterEnabledOverride ?? filteredMappedCount >= CLUSTERING_POPULATION_THRESHOLD;
        nativeRebuildMs = Math.round(performance.now() - startedAt);
        clusterSettingsError = useRoundedClusterTiles(clusterMaxZoom) && !roundedClusterTilesAvailable
          ? `This MapLibre build cannot apply half-zoom tile selection; effective cutoff is zoom ${nativeClusterMaxZoom(clusterMaxZoom) + 1}.`
          : "";
      } catch {
        clusterSettingsError = "Cluster settings could not be applied.";
      }
    }, clusterRebuildDebounce);
  }
  function updateVisualSettings() {
    if (!map || !isNativeMap()) return;
    if (usingMvt) {
      syncMvtReferenceAreas(map);
      const selected = activeApproximateAreaKey();
      const selectedArea = selected ? ['==', ['get', 'feature_key'], selected] : false;
      if (map.getLayer("mvt-approx-reference-area"))
        map.setPaintProperty("mvt-approx-reference-area", "fill-opacity", ['case', selectedArea, Math.min(0.16, referenceOpacity), 0] as any);
      if (map.getLayer("mvt-approx-reference-outline"))
        map.setPaintProperty("mvt-approx-reference-outline", "line-opacity", ['case', selectedArea, 0.92, 0] as any);
      if (map.getLayer("mvt-source-coordinates"))
        map.setPaintProperty("mvt-source-coordinates", "circle-radius", coordinateRadius);
      if (map.getLayer("mvt-reference-kind"))
        map.setLayoutProperty("mvt-reference-kind", "visibility", showReferenceLabels ? "visible" : "none");
      return;
    }
    if (mode === 'public-release') syncSelectedApproximateArea(map);
    applyRealPreviewVisualSettings(map, {
      referenceRadiusKm,
      referenceOpacity,
      coordinateRadius,
      pinScale,
      showReferenceLabels,
      selectedKey: activeApproximateAreaKey(),
    });
    syncSearchScope(map);
  }
  function syncSearchScope(instance: MapLibreMap): void {
    const data = createSearchRadiusArea(searchScope?.kind === 'radius' ? searchScope : null);
    let source = instance.getSource('search-radius') as GeoJSONSource | undefined;
    if (!source) {
      if (!data.features.length) return;
      instance.addSource('search-radius', { type: 'geojson', data });
      instance.addLayer({ id: 'search-radius-fill', type: 'fill', source: 'search-radius', paint: { 'fill-color': '#d8d6cc', 'fill-opacity': 0.08 } });
      instance.addLayer({ id: 'search-radius-outline', type: 'line', source: 'search-radius', paint: { 'line-color': '#eeeae0', 'line-opacity': 0.85, 'line-width': 1.5 } });
    } else source.setData(data);
  }
  function activeApproximateAreaKey(): string | null {
    // MVT aggregate references have opaque 32-hex feature keys and are
    // inspected separately from a record detail. Individual record points
    // must track the current selected detail ID instead of a stale click key.
    if (selectedReferenceKey && /^[a-f0-9]{32}$/i.test(selectedReferenceKey))
      return selectedReferenceKey;
    return mapState.selectedId;
  }
  function syncSelectedApproximateArea(instance: MapLibreMap) {
    const source = instance.getSource('approximate-reference-area') as GeoJSONSource | undefined;
    if (!source) {
      syncedApproximateAreaSource = undefined;
      syncedApproximateAreaKey = undefined;
      syncedApproximateAreaCollection = undefined;
      return;
    }
    const key = activeApproximateAreaKey();
    if (source === syncedApproximateAreaSource && key === syncedApproximateAreaKey
      && visibleNativeCollection === syncedApproximateAreaCollection) return;
    source.setData(createSelectedApproximateReferenceArea(
      visibleNativeCollection?.features ?? [], key, DEFAULT_REFERENCE_RADIUS_KM,
    ) as any);
    syncedApproximateAreaSource = source;
    syncedApproximateAreaKey = key;
    syncedApproximateAreaCollection = visibleNativeCollection;
  }
  function updateVisibleApproximateCount(instance: MapLibreMap): void {
    if (!isNativeMap() || !instance.getLayer("aggregate-outer")) {
      visibleApproximateCount = 0;
      return;
    }
    visibleApproximateCount = instance.queryRenderedFeatures({ layers: ["aggregate-outer"] }).length;
  }
  function setDiagnosticsOpen(open: boolean, restoreFocus = true): void {
    diagnosticsOpen = open;
    if (open) sampleDebugDimensions();
    ondebugopenchange?.(open);
    if (!open && restoreFocus) diagnosticsToggle?.focus();
  }
  function sampleDebugDimensions() {
    if (!host || !map) return;
    const canvas = map.getCanvas();
    debugDimensions = { width: host.clientWidth, height: host.clientHeight, canvasWidth: canvas.width, canvasHeight: canvas.height };
  }
  const debugClusterMode = $derived(clusterEnabledOverride === null ? 'auto' : clusterEnabledOverride ? 'on' : 'off');
  const ms = (value: number | null) => value === null ? 'Not sampled' : `${value} ms`;
  const debugSession = $derived([
    { label: 'Release', value: publicReleaseId ?? (isRealPreview() ? 'Private preview' : 'Not loaded') },
    { label: 'Manifest', value: publicReleaseManifestIdentity?.manifestSha256 ?? 'Unavailable' },
    { label: 'Restriction generation', value: String(publicReleaseManifestIdentity?.suppressionGeneration ?? 'Unavailable') },
    { label: 'List shown / total', value: searchDiagnostics ? `${searchDiagnostics.shown.toLocaleString()} / ${searchDiagnostics.total?.toLocaleString() ?? 'Unavailable'} · ${searchDiagnostics.listStatus}` : 'Unavailable' },
    { label: 'Matching mapped IDs', value: `${searchDiagnostics?.matchesStatus ?? mapMatchesStatus} · ${searchDiagnostics?.matchingMappedCount ?? mapMatchingIds?.length ?? 'No mask'}` },
    { label: 'Spatial scope', value: searchDiagnostics?.scope ?? searchScope?.kind ?? 'None' },
    { label: 'Filtered / loaded mapped', value: `${filteredMappedCount.toLocaleString()} / ${nativeRepresentedCount.toLocaleString()}` },
    { label: 'Clustering', value: `${debugClusterMode} · ${(clusterEnabledOverride ?? filteredMappedCount >= CLUSTERING_POPULATION_THRESHOLD) ? 'on' : 'off'} · threshold ${CLUSTERING_POPULATION_THRESHOLD.toLocaleString()}` },
    { label: 'Map container / canvas', value: `${debugDimensions.width} × ${debugDimensions.height} / ${debugDimensions.canvasWidth} × ${debugDimensions.canvasHeight}` },
    { label: 'Zoom / bearing / pitch', value: `${mapState.viewport.zoom.toFixed(2)} / ${(mapState.viewport.bearing ?? 0).toFixed(1)}° / ${cameraPitch.toFixed(1)}°` },
    { label: 'Basemap / terrain', value: `${mapState.basemap} / ${terrainEnabled ? 'on' : 'off'}` },
  ]);
  const debugRenderer = $derived(usingMvt ? [
    { label: 'Renderer', value: 'Vector tiles' },
    { label: 'Source / camera idle', value: `${mvtSourceReady ? 'ready' : 'waiting'} · ${ms(mvtSourceReadyMs)} / ${ms(mvtCameraSettleMs)}` },
    { label: 'Browser-visible resources', value: `${mvtLoadedTileResources} · ${mvtTransferBytes ?? 'Unavailable'} bytes · ${ms(mvtRequestDurationMs)}` },
    { label: 'Rendered marks', value: String(mvtRenderedFeatureCount ?? 'Not sampled') },
  ] : [
    { label: 'Renderer', value: 'Native GeoJSON / Supercluster' },
    { label: 'Snapshot', value: nativeSnapshotId },
    { label: 'Feed / requests', value: `${feedStatus} / ${nativeFeedRequests}` },
    { label: 'Cache', value: `${nativeCacheStatus} · ${nativeCacheEntries ?? 'Unavailable'} entries` },
    { label: 'Decoded projection', value: nativeDecodedBytes === null ? 'Unavailable' : `${(nativeDecodedBytes / 1048576).toFixed(2)} MB` },
    { label: 'Units / approximate references', value: `${nativeUnitCount.toLocaleString()} / ${nativeApproximateCount.toLocaleString()}` },
    { label: 'Index updates', value: String(nativeIndexUpdates) },
    { label: 'Persistent index', value: cacheTuning.indexEnabled ? indexCacheDiagnostic?.state ?? 'Not sampled' : 'Disabled' },
    { label: 'Cache builds / restores', value: `${indexCacheDiagnostic?.builds ?? 0} / ${indexCacheDiagnostic?.restores ?? 0}` },
    { label: tr('Stored index size', $language), value: indexCacheDiagnostic?.storedBytes == null ? 'Not sampled' : `${(indexCacheDiagnostic.storedBytes / 1048576).toFixed(2)} MiB` },
    ...(indexCacheReasonLabel(indexCacheDiagnostic?.reason) ? [{ label: tr('Index cache reason', $language), value: tr(indexCacheReasonLabel(indexCacheDiagnostic?.reason)!, $language) }] : []),
    { label: 'Tile cache hits / misses', value: `${tileCacheDiagnostic.hits} / ${tileCacheDiagnostic.misses}` },
    { label: 'Tile cache entries / size', value: `${tileCacheDiagnostic.entries} / ${(tileCacheDiagnostic.bytes / 1048576).toFixed(2)} MiB` },
    { label: 'Tile cache evictions / HTTP cache', value: `${tileCacheDiagnostic.evictions} / ${tileCacheDiagnostic.policyDelegations}` },
    { label: tr('World baseline', $language), value: worldCacheDiagnostic.status },
    { label: tr('World cache size', $language), value: `${(worldCacheDiagnostic.bytes / 1048576).toFixed(2)} MiB` },
    { label: tr('World chunks ready', $language), value: `${worldCacheDiagnostic.readyChunks} / ${worldCacheDiagnostic.totalChunks}` },
    { label: tr('World hits / requests', $language), value: `${worldCacheDiagnostic.hits} / ${worldCacheDiagnostic.requests}` },
    { label: 'Rendered marks', value: String(nativeRenderedCount ?? 'Not sampled') },
    { label: 'Feed / source ready / rebuild', value: `${ms(nativeFeedMs)} / ${ms(nativeIndexMs)} / ${ms(nativeRebuildMs)}` },
    { label: 'Camera moveend / idle', value: `${ms(nativeCameraMoveendMs)} / ${ms(nativeCameraIdleMs)}` },
    { label: 'Pending at moveend', value: `Basemap ${nativeBasemapPendingAtMoveend ? 'yes' : 'no'} · overlay ${nativeOverlayPendingAtMoveend ? 'yes' : 'no'}` },
    ...(cacheClearStatus ? [{ label: 'Cache action', value: cacheClearStatus }] : []),
  ]);
  const diagnosticSnapshot = $derived(safeDiagnosticSnapshot({
    mode, release: publicReleaseId ?? null, manifest: publicReleaseManifestIdentity?.manifestSha256 ?? null,
    restrictionGeneration: publicReleaseManifestIdentity?.suppressionGeneration ?? null, search: searchDiagnostics,
    loadedMapped: nativeRepresentedCount, filteredMapped: filteredMappedCount, renderedMarks: nativeRenderedCount,
    feedRequests: nativeFeedRequests, decodedBytes: nativeDecodedBytes, cacheEntries: nativeCacheEntries,
    indexUpdates: nativeIndexUpdates,
    feedMs: nativeFeedMs, indexMs: nativeIndexMs, rebuildMs: nativeRebuildMs,
    cameraMoveendMs: nativeCameraMoveendMs, cameraIdleMs: nativeCameraIdleMs,
    ...debugDimensions, zoom: mapState.viewport.zoom, bearing: mapState.viewport.bearing ?? 0, pitch: cameraPitch,
    clusterMode: debugClusterMode, clusterRadius, clusterMaxZoom, clusterMotionDuration, clusterMotionLimit, pinScale, layout: layoutTuning,
    cache: cacheTuning,
    worldCache: worldTuning, worldCacheMetrics: worldCacheDiagnostic,
    cacheMetrics: { indexState: indexCacheDiagnostic?.state ?? null, builds: indexCacheDiagnostic?.builds ?? 0,
      indexReason: indexCacheDiagnostic?.reason ?? null, indexStoredBytes: indexCacheDiagnostic?.storedBytes ?? null,
      restores: indexCacheDiagnostic?.restores ?? 0, tileEntries: tileCacheDiagnostic.entries, tileBytes: tileCacheDiagnostic.bytes,
      tileHits: tileCacheDiagnostic.hits, tileMisses: tileCacheDiagnostic.misses, tileEvictions: tileCacheDiagnostic.evictions,
      httpDelegations: tileCacheDiagnostic.policyDelegations },
  }));
  function resetTemporarySettings() {
    clusterRadius = DEFAULT_CLUSTER_RADIUS; clusterMaxZoom = DEFAULT_CLUSTER_MAX_ZOOM; clusterEnabledOverride = null;
    referenceRadiusKm = DEFAULT_REFERENCE_RADIUS_KM; referenceOpacity = 0.22; coordinateRadius = 6.5;
    pinScale = 1; showReferenceLabels = false; useV1Pins = true; clusterZoomDuration = 460; clusterRebuildDebounce = 150;
    clusterMotionDuration = DEFAULT_CLUSTER_MOTION_MS; clusterMotionLimit = DEFAULT_CLUSTER_MOTION_LIMIT; nativeMotionController?.cancel();
    onLayoutTuningReset?.(); scheduleClusterSettings(); updateVisualSettings(); void updatePinMode();
  }
  $effect(() => {
    mapState.selectedId;
    if (!mapState.selectedId) { pendingSelectionFocus = null; selectionFocus = null; }
    syncSelectionOverlayWhenReady(map, updateVisualSettings);
  });
  $effect(() => {
    const selectedId = mapState.selectedId;
    if (mode === 'public-release' && selectedReferenceKey !== null && selectedReferenceKey !== selectedId) {
      selectedReferenceKey = null;
      syncSelectionOverlayWhenReady(map, updateVisualSettings);
    }
  });
  // A reference area belongs to the current inspected aggregate only. Keep it
  // through the reference request, then clear it as soon as that inspection is
  // dismissed so a stale red area cannot survive behind an unrelated view.
  $effect(() => {
    if (mapState.aggregateMemberIds !== null) {
      hadAggregateInspection = true;
      return;
    }
    if (hadAggregateInspection) {
      hadAggregateInspection = false;
      if (selectedReferenceKey !== null) {
        selectedReferenceKey = null;
        syncSelectionOverlayWhenReady(map, updateVisualSettings);
      }
    }
  });
  $effect(() => {
    if (suppressDiagnostics && diagnosticsOpen) setDiagnosticsOpen(false, false);
  });
  let pinModeGeneration = 0;
  async function updatePinMode() {
    nativeMotionController?.cancel();
    const instance = map;
    if (!instance) return;
    const generation = ++pinModeGeneration;
    const enabled = useV1Pins;
    try {
      await setRealPreviewPinMode(instance, enabled, `${import.meta.env.BASE_URL}v1-pins/`);
      if (generation === pinModeGeneration && map === instance) pinModeError = "";
    } catch {
      if (generation !== pinModeGeneration || map !== instance) return;
      useV1Pins = false;
      pinModeError = "The V1 pin images could not be loaded.";
      void setRealPreviewPinMode(instance, false, `${import.meta.env.BASE_URL}v1-pins/`);
    }
  }
  function restoreNativeProjection(instance: MapLibreMap, data: JsonMapCollection): void {
    nativeMotionController?.cancel();
    // A verified feed can arrive through resume without passing addLayers.
    // Symbols must be registered before their source reaches worker placement.
    loadClusterImages();
    visibleNativeCollection = data;
    filteredMappedCount = representedMappedCount(data);
    const enabled = clusterFilteredPopulation(data, clusterEnabledOverride);
    if (hasRealPreviewMapLayers(instance)) {
      updateNativeClustering(instance, enabled);
      nativeIndexUpdates++;
      setRealPreviewMapData(instance, withPersistentIndexIdentity(data));
    } else {
      // A style reload may retain a source while losing one of its overlays.
      // Rebuild only this incomplete projection, never for paint-only updates.
      removeLocationLayers(instance);
      nativeIndexUpdates++;
      addRealPreviewMapLayers(instance, withPersistentIndexIdentity(data), { enabled, radius: clusterRadius, maxZoom: clusterMaxZoom });
      appliedNativeClustering = enabled;
    }
    const source = instance.getSource('locations');
    if (source) useCameraZoomLod(source as GeoJSONSource & CameraLodSource);
    updateVisualSettings();
    void updatePinMode();
  }
  function withPersistentIndexIdentity(data: JsonMapCollection): JsonMapCollection {
    if (mode !== 'public-release' || !publicReleaseManifestIdentity || mapState.navigationViewport) return data;
    return { ...data, [INDEX_CACHE_FIELD]: { ...publicReleaseManifestIdentity, profile: 'official',
      session: indexCacheSession, maxMiB: cacheTuning.indexMaxMiB, enabled: cacheTuning.indexEnabled } } as JsonMapCollection;
  }
  function updateCacheTuning(value: CacheTuning) {
    const previous = cacheTuning;
    const bounded = (n: number, low: number, high: number) => Math.max(low, Math.min(high, n));
    cacheTuning = { ...value, indexMaxMiB: bounded(value.indexMaxMiB, 8, 64), tileMaxMiB: bounded(value.tileMaxMiB, 4, 64),
      tileMaxEntries: bounded(value.tileMaxEntries, 32, 1024), tileTtlHours: bounded(value.tileTtlHours, 1, 168),
      ramTiles: bounded(value.ramTiles, 32, 256), baselineOpacity: bounded(value.baselineOpacity, 0, 1),
      tileFadeMs: Number.isFinite(value.tileFadeMs) ? Math.round(bounded(value.tileFadeMs, 0, 400)) : BASE_RASTER_FADE_MS };
    updateTileCacheSettings({ enabled: value.tileEnabled, maxBytes: cacheTuning.tileMaxMiB * 1048576,
      maxEntries: cacheTuning.tileMaxEntries, maxTtlMs: cacheTuning.tileTtlHours * 3600000 });
    indexCacheChannel?.postMessage({ command: 'settings', session: indexCacheSession, enabled: value.indexEnabled, maxMiB: cacheTuning.indexMaxMiB });
    if ((previous.indexEnabled && !value.indexEnabled) || cacheTuning.indexMaxMiB < previous.indexMaxMiB) {
      void trimClusterIndexCache(cacheTuning.indexMaxMiB).catch(() => { cacheClearStatus = 'Index storage unavailable.'; });
    }
    if (map) {
      updateMapTileMemoryCache(map, cacheTuning.ramTiles);
      if (map.getLayer('base')) map.setPaintProperty('base', 'raster-fade-duration', cacheTuning.tileFadeMs);
      if (map.getLayer('world-land')) map.setPaintProperty('world-land', 'fill-opacity', cacheTuning.baselineOpacity);
      applyWorldBaselineOpacity(map, cacheTuning.baselineOpacity);
    }
  }
  function updateWorldTuning(value: WorldCacheTuning) {
    const settings = updateWorldBaselineSettings({ enabled: value.enabled, maxZoom: value.maxZoom, maxBytes: value.maxMiB * 1048576 });
    worldTuning = { enabled: settings.enabled, maxZoom: settings.maxZoom, maxMiB: settings.maxBytes / 1048576 };
  }
  function resetCacheTuning() {
    resetTileCacheSettings(); updateCacheTuning({ ...defaultCacheTuning });
    const settings = resetWorldBaselineSettings();
    worldTuning = { enabled: settings.enabled, maxZoom: settings.maxZoom, maxMiB: settings.maxBytes / 1048576 };
  }
  async function clearWorldCache() {
    try { await clearWorldBaselineCache(); cacheClearStatus = 'World map cache cleared.'; }
    catch { cacheClearStatus = 'World map storage unavailable.'; }
  }
  async function clearBuiltIndex() {
    try { await clearClusterIndexCache(); cacheClearStatus = 'Built index cache cleared.'; }
    catch { cacheClearStatus = 'Index storage unavailable.'; }
  }
  async function clearViewedTiles() {
    try { await clearTileCache(); cacheClearStatus = 'Viewed tile cache cleared.'; }
    catch { cacheClearStatus = 'Tile storage unavailable.'; }
  }
  function updateNativeClustering(instance: MapLibreMap, enabled: boolean): void {
    if (appliedNativeClustering === enabled) return;
    const source = instance.getSource('locations') as GeoJSONSource | undefined;
    if (!source) return;
    appliedNativeClustering = enabled;
    nativeIndexUpdates++;
    void source.setClusterOptions({ cluster: enabled, clusterRadius, clusterMaxZoom: nativeClusterMaxZoom(clusterMaxZoom) })
      .catch(() => { clusterSettingsError = 'Cluster settings could not be applied.'; });
  }
  async function addLayers() {
    if (!map || !active) return;
    loadClusterImages();
    if (mode === "public-release" && !publicReleaseId) return;
    if (mode !== "synthetic") {
      if (mode === "public-release" && nativeFullCollection
        && requestedPublicReleaseId === publicReleaseId
        && requestedPublicReleaseIdentity === publicReleaseIdentity) {
        restoreNativeProjection(map, filteredNativeCollection(nativeFullCollection));
        setRealPreviewCategoryFilter(map, mapMatchingIds === null ? publicCategoryFilterKeys() : []);
        roundedClusterTilesAvailable = setClusterTileRounding(map, clusterMaxZoom);
        updateVisualSettings();
        startupStage = "rendering";
        feedStatus = "ready";
        return;
      }
      await loadNativeFeed();
      return;
    }
    await loadJsonFallbackImages(
      map,
      `${import.meta.env.BASE_URL}v1-pins/`,
    );
    addJsonLocationLayers(map, createJsonMapCollection(mapped, mode));
  }
  async function loadNativeFeed() {
    const instance = map;
    if (!instance || !active) return;
    if (mode === "public-release" && !publicReleaseId) return;
    if (mode === "candidate-preview" && candidateValidationFailed) return;
    if (mode === "public-release" && (requestedPublicReleaseId !== publicReleaseId || requestedPublicReleaseIdentity !== publicReleaseIdentity)) {
      requestedPublicReleaseId = publicReleaseId;
      requestedPublicReleaseIdentity = publicReleaseIdentity;
      requestedFeedSourceId = undefined;
      nativeFullCollection = undefined;
      if (instance.getSource("locations")) { nativeIndexUpdates++; setRealPreviewMapData(instance, { type: "FeatureCollection", features: [] }); }
    }
    const sourceId = null;
    if (requestedFeedSourceId === sourceId &&
        (feedStatus === "loading" || (feedStatus === "ready" && instance.getSource("locations")))) return;
    requestedFeedSourceId = sourceId;
    feedAbort?.abort();
    const controller = new AbortController();
    feedAbort = controller;
    const generation = ++feedGeneration;
    const styleGeneration = nativeStyleGeneration;
    feedStatus = "loading";
    startupStage = "fetching";
    nativeCacheStatus = 'unavailable';
    indexCacheDiagnostic = null;
    nativeFeedRequests++;
    nativeFeedMs = null;
    nativeIndexMs = null;
    nativeIndexStartedAt = null;
    mvtError = "";
    try {
      const requestedAt = performance.now();
      const result = publicReleaseId
        ? await publicMapFeedRepository.load("official", publicReleaseId, controller.signal, publicReleaseManifestIdentity ?? undefined)
        : mode === "candidate-preview"
          ? await candidateMapFeedRepository.load(controller.signal)
          : await mapFeedRepository.load(sourceId, controller.signal);
      if (controller.signal.aborted || map !== instance || generation !== feedGeneration || styleGeneration !== nativeStyleGeneration) return;
      onMapFeedMeta?.("meta" in result ? result.meta : null);
      onCandidatePreviewLabel?.("previewLabel" in result ? result.previewLabel ?? null : null);
      nativeSnapshotId = "snapshotId" in result ? result.snapshotId : result.meta.manifestSha256;
      const cacheDiagnostics = mapFeedCacheDiagnostics(result);
      nativeCacheStatus = cacheDiagnostics.cacheStatus;
      nativeDecodedBytes = cacheDiagnostics.decodedBytes;
      nativeCacheEntries = null;
      void (publicReleaseId ? publicMapCacheEntryCount() : mode === "candidate-preview" ? testReleaseMapCacheEntryCount() : realPreviewMapCacheEntryCount())
        .then(count => { if (!controller.signal.aborted && map === instance && generation === feedGeneration) nativeCacheEntries = count; })
        .catch(() => {});
      nativeFeedMs = Math.round(performance.now() - requestedAt);
      nativeUnitCount = result.collection.features.length;
      nativeRepresentedCount = result.collection.features.reduce((total, feature) => total + Number(feature.properties.weight), 0);
      nativeApproximateCount = result.collection.features.filter((feature) => feature.properties.precision === "approximate").length;
      nativeFullCollection = result.collection;
      nativeIndexStartedAt = performance.now();
      startupStage = "indexing";
      const visible = filteredNativeCollection(result.collection);
      restoreNativeProjection(instance, visible);
      appliedNativeFilterSignature = nativeFilterSignature(mapState.sourceId);
      appliedMatchingIds = mapMatchingIds;
      appliedMatchesStatus = mapMatchesStatus;
      appliedNativeSourceId = mapState.sourceId;
      roundedClusterTilesAvailable = setClusterTileRounding(instance, clusterMaxZoom);
      if (useRoundedClusterTiles(clusterMaxZoom) && !roundedClusterTilesAvailable)
        clusterSettingsError = `This MapLibre build cannot apply half-zoom tile selection; effective cutoff is zoom ${nativeClusterMaxZoom(clusterMaxZoom) + 1}.`;
      updateVisualSettings();
      feedStatus = "ready";
    } catch (error) {
      if (controller.signal.aborted || generation !== feedGeneration) return;
      if (mode === "candidate-preview" && error instanceof RealPreviewMapFeedError) candidateValidationFailed = true;
      feedStatus = "error";
      onMapFeedMeta?.(null);
      mvtError = error instanceof Error ? error.message : "The map feed could not be loaded.";
    }
  }

  $effect(() => {
    if (active && mode === "public-release" && map) {
      setRealPreviewCategoryFilter(map, mapMatchingIds === null ? publicCategoryFilterKeys() : []);
    }
  });
  function publicCategoryFilterKeys(): string[] {
    const keys: Record<string, string> = {
      Poultry: "animal_keeping_and_production", Pig: "animal_keeping_and_production",
      Dairy: "animal_keeping_and_production", Aquaculture: "animal_keeping_and_production",
      Processing: "processing_and_preparation", Laboratory: "research_and_animal_use",
    };
    return [...new Set(mapState.filters.categories.map(value => keys[value] ?? value))];
  }
  function filteredNativeCollection(collection: JsonMapCollection): JsonMapCollection {
    const sourceIds = [...new Set([...(mapState.sourceId ? [mapState.sourceId] : []), ...mapState.filters.sources])];
    if (mode === 'public-release') {
      // The server mask already applies every public list predicate, including
      // filters on observations not represented by the compact feed metadata.
      if (mapMatchingIds !== null || mapMatchesStatus === 'loading' || mapMatchesStatus === 'error') {
        return maskPublicMapMatches(collection, matchingIdSet, mapMatchesStatus);
      }
      const filtered = filterTestReleaseMapCollection(collection, { sourceIds, countryCodes: mapState.filters.countries, categoryKeys: publicCategoryFilterKeys() });
      const precise = { ...filtered, features: filtered.features.filter(feature => !mapState.filters.precisions.length || mapState.filters.precisions.includes(feature.properties.precision as any)) };
      return maskPublicMapMatches(precise, matchingIdSet, mapMatchesStatus);
    }
    if (mode !== 'candidate-preview') return sourceIds.length
      ? { ...collection, features: collection.features.filter(feature => feature.properties.source_id === sourceIds[0]) }
      : collection;
    return filterTestReleaseMapCollection(collection, { sourceIds, countryCodes: mapState.filters.countries, categoryKeys: mapState.filters.categories, activityKeys: mapState.filters.activities });
  }
  function nativeFilterSignature(sourceId: string | null): string {
    return JSON.stringify([sourceId, mapState.filters.countries, mapState.filters.sources, mapState.filters.categories, mapState.filters.activities, mapState.filters.precisions]);
  }
  function applyLocalSourceFilter(sourceId: string | null) {
    if (!active || !map || !nativeFullCollection || !map.getSource("locations")) return;
    const signature = nativeFilterSignature(sourceId);
    if (appliedNativeFilterSignature === signature && appliedMatchingIds === mapMatchingIds && appliedMatchesStatus === mapMatchesStatus) return;
    nativeMotionController?.cancel();
    nativeIndexStartedAt = performance.now();
    startupStage = "indexing";
    const visible = filteredNativeCollection(nativeFullCollection);
    visibleNativeCollection = visible;
    filteredMappedCount = representedMappedCount(visible);
    updateNativeClustering(map, clusterFilteredPopulation(visible, clusterEnabledOverride));
    nativeIndexUpdates++;
    setRealPreviewMapData(map, withPersistentIndexIdentity(visible));
    updateVisualSettings();
    appliedNativeSourceId = sourceId;
    appliedNativeFilterSignature = signature;
    appliedMatchingIds = mapMatchingIds;
    appliedMatchesStatus = mapMatchesStatus;
  }
  function ensureNativeFeedWhenStyleReady(): () => void {
    const instance = map;
    if (!instance) return () => {};
    if (!nativeStyleReady) return () => {};
    if (mode === "public-release") {
      if (!publicReleaseId) {
        if (requestedPublicReleaseId || nativeFullCollection) {
          feedGeneration++;
          feedAbort?.abort();
          feedAbort = undefined;
          requestedPublicReleaseId = null;
          requestedPublicReleaseIdentity = publicReleaseIdentity;
          requestedFeedSourceId = undefined;
          nativeFullCollection = undefined;
          visibleNativeCollection = undefined;
          appliedNativeSourceId = undefined;
          if (instance.getSource("locations")) { nativeIndexUpdates++; setRealPreviewMapData(instance, { type: "FeatureCollection", features: [] }); }
          syncSelectedApproximateArea(instance);
          onMapFeedMeta?.(null);
          feedStatus = "error";
          startupStage = "ready";
          mvtError = "No current public map release is available.";
        }
      } else if (!active) return () => {};
      else if (canReusePublicMapFeed(publicReleaseId, publicReleaseIdentity, requestedPublicReleaseId, requestedPublicReleaseIdentity, !!nativeFullCollection)) {
        applyLocalSourceFilter(mapState.sourceId);
      } else {
        void loadNativeFeed();
      }
    } else if (!active) return () => {};
    else if (nativeFullCollection) applyLocalSourceFilter(mapState.sourceId);
    else void loadNativeFeed();
    return () => {};
  }
  async function clearProjectionCache() {
    await clearClusterIndexCache();
    const removed = publicReleaseId ? (await clearPublicMapCache(), 1) : mode === "candidate-preview" ? await clearTestReleaseMapCache() : await clearRealPreviewMapCache();
    feedGeneration++; feedAbort?.abort(); feedAbort = undefined;
    nativeFullCollection = undefined; visibleNativeCollection = undefined;
    requestedFeedSourceId = undefined; appliedNativeFilterSignature = undefined;
    appliedNativeSourceId = undefined; appliedNativeClustering = undefined;
    appliedMatchingIds = undefined; appliedMatchesStatus = undefined;
    nativeUnitCount = 0; nativeRepresentedCount = 0; filteredMappedCount = 0; nativeRenderedCount = null;
    syncedApproximateAreaSource = undefined; syncedApproximateAreaKey = undefined; syncedApproximateAreaCollection = undefined;
    if (map) removeLocationLayers(map);
    onMapFeedMeta?.(null);
    nativeCacheEntries = 0;
    cacheClearStatus = publicReleaseId ? "Cleared public map projection cache." : removed ? `Cleared ${removed} cached projection ${removed === 1 ? "entry" : "entries"}.` : "Projection cache was already empty.";
    candidateValidationFailed = false;
    if (active) void loadNativeFeed();
  }
  function addMvtLayers() {
    if (!map) return;
    addMvtLocationLayers(map, mapState.sourceId ?? undefined);
    appliedMvtTileSignature = `${mapState.sourceId ?? ""}:${clusterMaxZoom}`;
    updateVisualSettings();
    void updatePinMode();
  }

  function replaceMapProjection() {
    if (!map || !map.isStyleLoaded()) return;
    if (usingMvt) {
      const nextSignature = `${mapState.sourceId ?? ""}:${clusterMaxZoom}`;
      if (map.getSource("preview-mvt") && map.getLayer("mvt-clusters")) {
        // Viewport actions replace the immutable state object too. Preserve the
        // live MVT source/layers for those unrelated updates; a real source or
        // cutoff change updates the tile template in place instead.
        if (appliedMvtTileSignature !== nextSignature) {
          setMvtClusterCutoff(map, mapState.sourceId ?? undefined, clusterMaxZoom);
          appliedMvtTileSignature = nextSignature;
        }
        updateVisualSettings();
        return;
      }
      const now = performance.now();
      mvtError = "";
      mvtSourceReady = false;
      mvtSourceReadyMs = null;
      mvtCameraStartedAt = null;
      mvtInitialStartedAt = now;
      mvtResourceWindowStart = now;
    }
    mvtMotionController?.cancel();
    mvtMotionController?.clearLineage();
    nativeMotionController?.cancel();
    // Source/style changes invalidate both cached tile symbols and lineage. Remove
    // the complete projection before adding the selected path back atomically.
    removeLocationLayers(map);
    if (usingMvt) addMvtLayers();
    else addLayers();
  }
  function prefersReducedMotion() {
    return (
      typeof matchMedia !== "undefined" &&
      matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }
  function summarizeMvtResources(startTime: number, endTime: number) {
    // Browser resource entries include cached responses. They are cumulative
    // since this projection was attached, not a count of network fetches.
    const resources = performance
      .getEntriesByType("resource")
      .filter((entry): entry is PerformanceResourceTiming => {
        if (!(entry instanceof PerformanceResourceTiming)) return false;
        try {
          const url = new URL(entry.name);
          return (
            url.origin === window.location.origin &&
            url.pathname.includes("/dev/real-preview/map/tiles/") &&
            entry.startTime >= startTime &&
            entry.startTime <= endTime
          );
        } catch {
          return false;
        }
      });
    mvtLoadedTileResources = resources.length;

    const reportedSizes = resources
      .map((entry) => entry.transferSize)
      .filter((size) => size > 0);
    mvtTransferBytes = reportedSizes.length
      ? reportedSizes.reduce((sum, size) => sum + size, 0)
      : null;

    const measuredDurations = resources
      .map((entry) => entry.responseEnd - entry.startTime)
      .filter((duration) => Number.isFinite(duration) && duration >= 0);
    mvtRequestDurationMs = measuredDurations.length
      ? Math.round(measuredDurations.reduce((sum, duration) => sum + duration, 0))
      : null;
  }

  function sampleMvtRenderedFeatures(instance: MapLibreMap) {
    // One bounded query after source/camera settle (never per frame). Count only
    // primary geometry layers so reference label layers cannot double-count.
    const layers = [
      "mvt-clusters",
      "mvt-reference-center",
      "mvt-source-coordinates",
    ].filter((layer) => instance.getLayer(layer));
    mvtRenderedFeatureCount = layers.length
      ? instance.queryRenderedFeatures({ layers }).length
      : 0;
  }

  function markMvtSourceReady(instance: MapLibreMap) {
    mvtSourceReady = instance.isSourceLoaded("preview-mvt");
    if (mvtSourceReady) {
      startupStage = "ready";
      if (mvtSourceReadyMs === null)
        mvtSourceReadyMs = Math.round(performance.now() - mvtInitialStartedAt);
      syncMvtReferenceAreas(instance);
      updateMvtAccessibleFeatures(instance);
    }
  }

  function syncMvtReferenceAreas(instance: MapLibreMap) {
    const areaSource = instance.getSource("mvt-reference-areas") as GeoJSONSource | undefined;
    if (!areaSource || !instance.getSource("preview-mvt") || !instance.isSourceLoaded("preview-mvt")) return;
    areaSource.setData(createMvtReferenceAreas(
      instance.querySourceFeatures("preview-mvt", { sourceLayer: "uec_preview" }) as any[],
      referenceRadiusKm,
    ) as any);
  }

  function updateMvtAccessibleFeatures(instance: MapLibreMap) {
    const rendered = instance.queryRenderedFeatures({
      layers: ["mvt-clusters", "mvt-reference-center", "mvt-source-coordinates"],
    }) as any[];
    const unique = new Map<string, { key: string; label: string; kind: "coordinate" | "reference" }>();
    for (const feature of rendered) {
      const properties = feature.properties ?? {};
      const key = properties.feature_key;
      if (typeof key !== "string" || unique.has(key)) continue;
      const represented = Number(properties.count);
      if (properties.kind === "city_reference") {
        unique.set(key, { key, label: `Open approximate city location · ${Number.isFinite(represented) ? represented : 0} represented`, kind: "reference" });
      } else if (properties.kind === "coarse_reference") {
        unique.set(key, { key, label: `Open approximate area reference · ${Number.isFinite(represented) ? represented : 0} represented`, kind: "reference" });
      } else if (properties.kind === "source_coordinate") {
        const record = records.find((candidate) => candidate.id === key);
        const source = record?.sourceId ? ` for ${record.sourceId}` : "";
        const qualifier = properties.precision === "source_provided_unverified"
          ? "source-provided location · precision unverified"
          : properties.precision === "source_numeric_pending_review"
            ? "source coordinate · pending review"
            : "approximate source location";
        unique.set(key, { key, label: `Open ${qualifier}${source}`, kind: "coordinate" });
      }
      if (unique.size >= 80) break;
    }
    mvtAccessibleFeatures = [...unique.values()];
  }

  function updateMvtDiagnostics(instance: MapLibreMap) {
    if (!usingMvt || !instance.isStyleLoaded()) return;
    const now = performance.now();
    markMvtSourceReady(instance);
    if (!mvtSourceReady) return;
    mvtCameraSettleMs =
      mvtCameraStartedAt === null
        ? mvtCameraSettleMs
        : Math.round(now - mvtCameraStartedAt);
    mvtCameraStartedAt = null;
    // The rendered-feature query walks the full viewport. Keep it out of the
    // normal pan/zoom path until a developer actually opens diagnostics.
    if (diagnosticsOpen) {
      summarizeMvtResources(mvtResourceWindowStart, now);
      sampleMvtRenderedFeatures(instance);
    }
  }

  onMount(() => {
    mvtMotionController = new MvtMotionController({
      getMap: () => map,
      reducedMotion: prefersReducedMotion,
    });
    jsonMotionController = new JsonClusterMotionController({
      getMap: () => map,
      reducedMotion: prefersReducedMotion,
    });
    nativeMotionController = new NativeClusterMotionController({
      getMap: () => map, reducedMotion: prefersReducedMotion,
      enabled: () => active && isNativeMap() && !activeFlight && useV1Pins,
      duration: () => clusterMotionDuration, limit: () => clusterMotionLimit,
    });
    if (host.parentElement) {
      // Each projection owns exactly one overlay canvas. The fixture fallback
      // must not mount the real-preview MVT transition system, or vice versa.
      if (usingMvt) mvtMotionController.attach(host.parentElement);
      else if (mode === "synthetic") jsonMotionController.attach(host.parentElement);
      else if (isNativeMap()) nativeMotionController.attach(host.parentElement);
    }
    return () => {
      mvtMotionController?.dispose();
      jsonMotionController?.dispose();
      nativeMotionController?.dispose(); nativeMotionController = undefined;
      mvtMotionController = undefined;
      jsonMotionController = undefined;
    };
  });

  onMount(() => {
    let instance: MapLibreMap | undefined;
    const onZoomStart = (event: any) => {
      zoomStartedAt = performance.now();
      if (usingMvt) {
        if (instance && event?.originalEvent)
          mvtMotionController?.prepareJoin(instance.getZoom());
        return;
      }
      if (mode === "synthetic") jsonMotionController?.onZoomStart(event);
      else if (isNativeMap()) nativeMotionController?.onZoomStart();
    };
    queueMicrotask(() => {
      instance = map;
      instance?.on("zoomstart", onZoomStart);
    });
    return () => instance?.off("zoomstart", onZoomStart);
  });
  function bindInteractions() {
    if (!map) return;
    const focusRecord = (id: string, center: [number, number]) => {
      if (!map || !center.every(Number.isFinite)) return;
      selectionFocus = { id, center };
      pendingSelectionFocus = center;
      map.easeTo({ center, duration: 380, easing: (t) => 1 - Math.pow(1 - t, 3), essential: false });
    };
    const inspectReference = (key: unknown, count: unknown, sourceId?: unknown) => {
      if (typeof key !== "string" || !/^[a-f0-9]{32}$/i.test(key)) return false;
      selectedReferenceKey = key;
      updateVisualSettings();
      const parsedCount = Number(count);
      pendingReference = { key, count: Number.isFinite(parsedCount) ? parsedCount : 0, observedLoading: false };
      onreference?.(key, typeof sourceId === "string" ? sourceId : undefined);
      return true;
    };
    if (usingMvt) {
      const inspectMvtReference = (key: string, count: number) => inspectReference(key, count);
      const selectMvtRecord = (feature: any) => {
        const key = feature?.properties?.feature_key;
        if (typeof key === "string" && /^[a-f0-9]{32}$/i.test(key)) {
          inspectMvtReference(key, Number(feature?.properties?.count ?? feature?.properties?.weight));
          return;
        }
        if (typeof key !== "string" || !/^[0-9a-f-]{36}$/i.test(key)) return;
        selectedReferenceKey = null;
        updateVisualSettings();
        const coordinates = feature?.geometry?.coordinates;
        if (map && Array.isArray(coordinates) && coordinates.length >= 2) {
          const center: [number, number] = [Number(coordinates[0]), Number(coordinates[1])];
          focusRecord(key, center);
        }
        onselect(key);
      };
      map.on("click", "mvt-clusters", (event: any) => {
        if (activeFlight) return;
        const feature = event.features?.[0],
          nextZoom = Number(feature?.properties?.next_zoom),
          parentKey = feature?.properties?.feature_key,
          count = Number(feature?.properties?.count),
          rawCoordinates = feature?.geometry?.coordinates;
        if (
          !feature ||
          !Number.isFinite(nextZoom) ||
          typeof parentKey !== "string" ||
          !Array.isArray(rawCoordinates)
        )
          return;
        const coordinates: [number, number] = [
          Number(rawCoordinates[0]),
          Number(rawCoordinates[1]),
        ];
        if (!coordinates.every(Number.isFinite)) return;
        const targetZoom = Math.max(map!.getZoom() + 1, Math.min(14, nextZoom));
        mvtMotionController?.queueExpansion({
          parentKey,
          longitude: coordinates[0],
          latitude: coordinates[1],
          count: Number.isFinite(count) ? count : 1,
          targetZoom,
        });
        map?.easeTo({
          center: coordinates,
          zoom: targetZoom,
          duration: clusterZoomDuration,
          easing: (t) => 1 - Math.pow(1 - t, 3),
          essential: false,
        });
      });
      map.on("click", "mvt-source-coordinates", (event: any) => {
        if (activeFlight) return;
        selectMvtRecord(event.features?.[0]);
      });
      map.on("click", "mvt-v1-source-pins", (event: any) => {
        if (activeFlight) return;
        selectMvtRecord(event.features?.[0]);
      });
      map.on("click", "mvt-approx-reference-area", (event: any) => {
        if (activeFlight) return;
        const key = event.features?.[0]?.properties?.feature_key;
        if (typeof key !== "string" || !/^[a-f0-9]{32}$/i.test(key)) return;
        inspectMvtReference(key, 0);
      });
      map.on("click", "mvt-reference-center", (event: any) => {
        if (activeFlight) return;
        const feature = event.features?.[0],
          key = feature?.properties?.feature_key,
          count = Number(feature?.properties?.count);
        if (typeof key === "string" && /^[a-f0-9]{32}$/i.test(key)) {
          inspectMvtReference(key, count);
        }
      });
      for (const layer of [
        "mvt-clusters",
        "mvt-source-coordinates",
        "mvt-v1-source-pins",
        "mvt-reference-center",
        "mvt-approx-reference-area",
      ]) {
        map.on("mouseenter", layer, () => {
          if (map) map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layer, () => {
          if (map) map.getCanvas().style.cursor = "";
        });
      }
      return;
    }
    map.on("click", "clusters", (event: any) => {
      if (activeFlight) return;
      const feature = event.features?.[0],
        clusterId = feature?.properties?.cluster_id;
      if (typeof clusterId !== "number") return;
      if (mode === "synthetic") jsonMotionController?.playExpansion(feature, clusterId);
      (map?.getSource("locations") as GeoJSONSource | undefined)
        ?.getClusterExpansionZoom(clusterId)
        .then((zoom) => {
          if (!map) return;
          if (mode === "synthetic") jsonMotionController?.armExpansion(map);
          map.easeTo({
            center: feature.geometry.coordinates,
            zoom,
            duration: clusterZoomDuration,
            easing: (t) => 1 - Math.pow(1 - t, 3),
            essential: false,
          });
        });
    });
    for (const layer of isNativeMap()
      ? ["source-coordinate-points", "v1-source-pins"]
      : ["exact-pins", "approximate-points", "source-coordinate-points"])
      map.on("click", layer, (event: any) => {
        if (activeFlight) return;
        const properties = event.features?.[0]?.properties;
        const id = isRealPreview() ? properties?.key : properties?.id;
        if (typeof id === "string") {
          // Provider-address points represent a reference group even when the
          // source grouped just one candidate at that geometry. Their 32-hex
          // key belongs to the reference-members endpoint, not record detail.
          if (isRealPreview() && inspectReference(id, properties?.weight, properties?.source_id)) return;
          // A source coordinate is an ordinary record selection, never an
          // approximate reference. Clear any prior inspected reference area.
          if (selectedReferenceKey !== null) {
            selectedReferenceKey = null;
            updateVisualSettings();
          }
          const coordinates = event.features?.[0]?.geometry?.coordinates;
          if (map && Array.isArray(coordinates) && coordinates.length >= 2) {
            const center: [number, number] = [Number(coordinates[0]), Number(coordinates[1])];
            focusRecord(id, center);
          }
          onselect(id);
        }
      });
    const handleReferenceClick = (event: any, layer: "aggregate-outer" | "approx-reference-points" | "approx-reference-pins" | "approx-reference-circles" | "approx-reference-cue") => {
      if (activeFlight) return;
      // The visible point owns center clicks for approximate records; keep
      // the reference circle available for inspecting its selected area.
      if (layer === "aggregate-outer" && event.features?.[0]?.properties?.precision === "approximate" && map && event.point && event.features?.[0]?.geometry?.coordinates) {
        const center = map.project(event.features[0].geometry.coordinates);
        if (Math.hypot(event.point.x - center.x, event.point.y - center.y) <= 7) return;
      }
      if (isRealPreview()) {
        const properties = event.features?.[0]?.properties;
        // Approximate source-coordinate halos are visual context around an
        // individual pin, not aggregate-member references.
        if (layer === "aggregate-outer" && properties?.kind === "source-coordinate") return;
        const city = properties?.precision === "city" || properties?.precision === "city_reference_approximate";
        // The center icon overlays the geographic circle at every zoom. Let
        // its own handler own center clicks; the outer circle owns area clicks.
        if (city && layer === "aggregate-outer" && map && event.point && event.features?.[0]?.geometry?.coordinates) {
          const center = map.project(event.features[0].geometry.coordinates);
          if (Math.hypot(event.point.x - center.x, event.point.y - center.y) <= 20 * APPROX_MARKER_SCALE) return;
        }
        const key = properties?.key;
        inspectReference(key, properties?.weight, properties?.source_id);
        return;
      }
      if (mode === "public-release") {
        const properties = event.features?.[0]?.properties;
        const id = properties?.key ?? properties?.id;
        if (typeof id === "string") {
          // Public reference features are still individual released records.
          // Select that record (and its honest reference area) instead of
          // sending its public UUID to the private aggregate-member API.
          selectedReferenceKey = id;
          updateVisualSettings();
          const coordinates = event.features?.[0]?.geometry?.coordinates;
          if (map && Array.isArray(coordinates) && coordinates.length >= 2) {
            const center: [number, number] = [Number(coordinates[0]), Number(coordinates[1])];
            focusRecord(id, center);
          }
          onselect(id);
        }
        return;
      }
      try {
        const ids = JSON.parse(
          event.features?.[0]?.properties?.memberIds ?? "[]",
        );
        if (Array.isArray(ids))
          onaggregate(ids.filter((id): id is string => typeof id === "string"));
      } catch {
        /* fixture metadata is validated before use */
      }
    };
    map.on("click", "aggregate-outer", (event: any) => handleReferenceClick(event, "aggregate-outer"));
    if (isNativeMap()) {
      map.on("click", "approx-reference-pins", (event: any) => handleReferenceClick(event, "approx-reference-pins"));
      map.on("click", "approx-reference-circles", (event: any) => handleReferenceClick(event, "approx-reference-circles"));
      map.on("click", "approx-reference-cue", (event: any) => handleReferenceClick(event, "approx-reference-cue"));
    }
    if (isNativeMap())
      map.on("click", "approx-reference-points", (event: any) => handleReferenceClick(event, "approx-reference-points"));
    for (const layer of isNativeMap()
      ? ["clusters", "source-coordinate-points", "v1-source-pins", "aggregate-outer", "approx-reference-pins", "approx-reference-circles", "approx-reference-points", "approx-reference-cue"]
      : ["clusters", "exact-pins", "approximate-points", "source-coordinate-points", "aggregate-outer"]) {
      map.on("mouseenter", layer, () => {
        if (map) map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layer, () => {
        if (map) map.getCanvas().style.cursor = "";
      });
    }
  }
  function publishBounds() {
    if (!map) return;
    const bounds = map.getBounds();
    const westRaw = bounds.getWest(),
      eastRaw = bounds.getEast();
    if (eastRaw - westRaw >= 360) {
      onbounds?.({
        west: -180,
        south: Math.max(-90, bounds.getSouth()),
        east: 180,
        north: Math.min(90, bounds.getNorth()),
      });
      return;
    }
    const normalize = (longitude: number) =>
      ((((longitude + 180) % 360) + 360) % 360) - 180;
    onbounds?.({
      west: normalize(westRaw),
      south: Math.max(-90, bounds.getSouth()),
      east: normalize(eastRaw),
      north: Math.min(90, bounds.getNorth()),
    });
  }
  onMount(() => {
    appliedBasemap = mapState.basemap;
    const unsubscribeTiles = subscribeTileCacheDiagnostics(value => { tileCacheDiagnostic = value; });
    const unsubscribeWorld = subscribeWorldBaselineDiagnostics(value => { worldCacheDiagnostic = value; });
    if (typeof BroadcastChannel !== 'undefined') {
      indexCacheChannel = new BroadcastChannel(INDEX_CACHE_CHANNEL);
      indexCacheChannel.onmessage = event => {
        const value = event.data as IndexCacheDiagnostic;
        if (value?.session !== indexCacheSession || !['lookup', 'building', 'stored', 'restored', 'unavailable'].includes(value.state)
          || !Number.isSafeInteger(value.builds) || !Number.isSafeInteger(value.restores)) return;
        indexCacheDiagnostic = value;
      };
    }
    mvtInitialStartedAt = performance.now();
    mvtResourceWindowStart = mvtInitialStartedAt;
    let instance: MapLibreMap;
    try {
      instance = new maplibregl.Map({
      container: host,
      style: style(),
      center: [mapState.viewport.centerLon, mapState.viewport.centerLat],
      zoom: mapState.viewport.zoom,
      pitch: mapState.viewport.pitch ?? 0,
      bearing: mapState.viewport.bearing ?? 0,
      attributionControl: {},
      fadeDuration: 0,
      // Retain one extra zoom level of native source tiles so recent pan/zoom
      // positions can reuse MapLibre's buffered tiles without app snapshots.
      maxTileCacheZoomLevels: 6,
      maxTileCacheSize: cacheTuning.ramTiles,
      } as any);
    } catch {
      // Renderer failure must not abort the parent release/search effects.
      // MapLibre rolls back its container when GPU initialization fails.
      rendererUnavailable = true;
      startupStage = 'ready';
      const cleanupFailedInitialization = () => {
        unsubscribeTiles(); unsubscribeWorld();
        indexCacheChannel?.close(); indexCacheChannel = undefined;
        mvtMotionController?.dispose(); mvtMotionController = undefined;
        jsonMotionController?.dispose(); jsonMotionController = undefined;
        nativeMotionController?.dispose(); nativeMotionController = undefined;
        host.replaceChildren();
      };
      cleanupFailedInitialization();
      onMapControlsReady?.(false);
      return cleanupFailedInitialization;
    }
    map = instance;
    let resizeFrame: number | undefined;
    let previousWidth = host.clientWidth;
    let previousHeight = host.clientHeight;
    const resizeObserver = new ResizeObserver(() => {
      if (resizeFrame !== undefined) cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(() => {
        resizeFrame = undefined;
        const width = host.clientWidth, height = host.clientHeight;
        if (!active || !width || !height || (width === previousWidth && height === previousHeight)) return;
        previousWidth = width; previousHeight = height;
        nativeMotionController?.cancel();
        if (resumePending) { instance.resize(); return; }
        resizeWorkspaceMap(instance, selectionFocus?.id === mapState.selectedId ? selectionFocus.center : null, activeFlight);
        if (diagnosticsOpen) sampleDebugDimensions();
        publishBounds();
      });
    });
    resizeObserver.observe(host);
    updateCameraPitch(instance.getPitch());
    const previewWindow = window as Window & {
      __UEC_LOCAL_PREVIEW_MAP__?: MapLibreMap;
    };
    if (import.meta.env.DEV) previewWindow.__UEC_LOCAL_PREVIEW_MAP__ = instance;
    instance
      .getCanvas()
      .setAttribute(
        "aria-label",
        "Record map. Select a cluster, source coordinate, or approximate area reference.",
      );
    instance.on('styledataloading', () => nativeMotionController?.cancel(true));
    for (const event of ['rotatestart', 'pitchstart', 'dragstart'] as const) instance.on(event, () => nativeMotionController?.cancel());
    instance.on("style.load", () => {
      nativeMotionController?.cancel(true);
      for (const sourceId of ["base", "transport", "world-streets", "world-satellite"]) {
        const source = instance.getSource(sourceId);
        if (source) useCameraZoomLod(source as CameraLodSource);
      }
      updateMapTileMemoryCache(instance, cacheTuning.ramTiles);
      if (instance.getLayer('base')) instance.setPaintProperty('base', 'raster-fade-duration', cacheTuning.tileFadeMs);
      if (instance.getLayer('world-land')) instance.setPaintProperty('world-land', 'fill-opacity', cacheTuning.baselineOpacity);
      applyWorldBaselineBasemap(instance, mapState.basemap);
      applyWorldBaselineOpacity(instance, cacheTuning.baselineOpacity);
      nativeStyleGeneration++;
      // These local sprites belong to the style, independently of whether
      // release verification has activated data loading yet.
      loadClusterImages();
      nativeStyleReady = true;
      onMapControlsReady?.(true);
      // Preserve terrain after its first activation, including overhead mode.
      // A cold, never-tilted view still does not request elevation tiles.
      if (active) setTerrain(instance.getPitch() > 0.5 || terrainEnabled);
      void (async () => {
        try {
          if (usingMvt) {
            loadClusterImages();
            addMvtLayers();
          } else {
            await addLayers();
          }
          if (!interactionsBound && map === instance) {
            bindInteractions();
            interactionsBound = true;
          }
          publishBounds();
          instance.resize();
          syncSearchScope(instance);
        } catch (error) {
          if (map === instance) {
            feedStatus = "error";
            startupStage = "ready";
            mvtError = error instanceof Error ? error.message : "The map could not be initialized.";
          }
        }
      })();
    });
    instance.on("error", (event: any) => {
      if (usingMvt && event?.sourceId === "preview-mvt")
        mvtError =
          "Map tiles could not be refreshed. Try panning or selecting a different source.";
      if (event?.sourceId === TERRAIN_SOURCE_ID && terrainEnabled) {
        setTerrain(false);
        terrainError = "Terrain tiles are unavailable. The map is shown flat.";
        terrainRetryRequired = true;
        instance.easeTo({ pitch: 0, duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 300 });
      }
    });
    instance.on("movestart", (event: any) => {
      nativeMotionController?.cancel();
      if (event?.originalEvent) { pendingSelectionFocus = null; selectionFocus = null; }
      if (event?.originalEvent && terrainPending) {
        terrainViewGeneration++; terrainViewAbort?.abort(); terrainPending = false;
      }
      if (usingMvt) mvtCameraStartedAt ??= performance.now();
      if (isNativeMap()) nativeCameraStartedAt ??= performance.now();
      if (mode === "synthetic") {
        jsonMotionController?.cancel();
      }
    });
    instance.on("sourcedata", (event: any) => {
      if (event?.sourceId === TERRAIN_SOURCE_ID) settlePendingSelectionFocus();
      if (isNativeMap() && event?.sourceId === "locations" &&
          nativeIndexStartedAt !== null && instance.isSourceLoaded("locations")) {
        nativeIndexMs = Math.round(performance.now() - nativeIndexStartedAt);
        nativeIndexStartedAt = null;
        startupStage = "rendering";
      }
      if (usingMvt && event?.sourceId === "preview-mvt") {
        markMvtSourceReady(instance);
        mvtMotionController?.playExpansion();
        mvtMotionController?.playJoin();
      }
    });
    instance.on("render", () => {
      nativeMotionController?.onRender();
      if (isNativeMap() && startupStage === "rendering" &&
          instance.isSourceLoaded("locations")) startupStage = "ready";
    });
    instance.on("idle", () => {
      settlePendingSelectionFocus();
      if (isNativeMap()) {
        updateVisibleApproximateCount(instance);
        if (startupStage === "rendering" && instance.isSourceLoaded("locations")) startupStage = "ready";
        if (nativeCameraStartedAt !== null) {
          nativeCameraIdleMs = Math.round(performance.now() - nativeCameraStartedAt);
          nativeCameraStartedAt = null;
        }
        if (diagnosticsOpen && instance.getLayer("clusters"))
          nativeRenderedCount = instance.queryRenderedFeatures({ layers: ["clusters", "aggregate-outer", "approx-reference-pins", "approx-reference-circles", "approx-reference-points", "source-coordinate-points", "v1-source-pins"] }).length;
      }
      if (usingMvt) {
        updateMvtDiagnostics(instance);
        updateMvtAccessibleFeatures(instance);
        mvtMotionController?.playExpansion();
        mvtMotionController?.playJoin();
      }
    });
    instance.on("moveend", () => {
      if (settlingSelectionFocus) return;
      activeFlight = false;
      settlePendingSelectionFocus();
      if (isNativeMap() && nativeCameraStartedAt !== null) {
        nativeCameraMoveendMs = Math.round(performance.now() - nativeCameraStartedAt);
        nativeBasemapPendingAtMoveend = !instance.isSourceLoaded("base");
        nativeOverlayPendingAtMoveend = !instance.isSourceLoaded("locations");
      }
      if (active && !syncing) {
        const center = instance.getCenter();
        onviewport({
          centerLat: Number(center.lat.toFixed(4)),
          centerLon: Number(center.lng.toFixed(4)),
          zoom: instance.getZoom(),
          pitch: Math.round(instance.getPitch()),
          bearing: Number((((instance.getBearing() + 180) % 360 + 360) % 360 - 180).toFixed(1)),
        });
        updateCameraPitch(instance.getPitch());
        zoomSettleMs =
          zoomStartedAt === null
            ? null
            : Math.round(performance.now() - zoomStartedAt);
        zoomStartedAt = null;
        // Wheel and pinch input can yield a run of moveend events. Settling prevents
        // repeated integer-tile snapshots and Supercluster rebuilds between gestures.
        if (boundsTimer) clearTimeout(boundsTimer);
        boundsTimer = setTimeout(() => publishBounds(), 150);
      }
    });
    instance.on("pitch", () => updateCameraPitch(instance.getPitch()));
    instance.on("pitchend", () => { if (active && instance.getPitch() > 0.5) setTerrain(true); });
    return () => {
      unsubscribeTiles(); unsubscribeWorld(); cancelWorldBaselineWarmup(); indexCacheChannel?.close(); indexCacheChannel = undefined;
      setTileCachePersistenceAllowed(true);
      resizeObserver.disconnect();
      terrainViewGeneration++; terrainViewAbort?.abort();
      if (resizeFrame !== undefined) cancelAnimationFrame(resizeFrame);
      basemapRequest++;
      feedAbort?.abort();
      if (boundsTimer) clearTimeout(boundsTimer);
      if (clusterUpdateTimer) clearTimeout(clusterUpdateTimer);
      mvtMotionController?.cancel();
      jsonMotionController?.cancel();
      nativeMotionController?.cancel();
      if (previewWindow.__UEC_LOCAL_PREVIEW_MAP__ === instance)
        delete previewWindow.__UEC_LOCAL_PREVIEW_MAP__;
      instance.remove();
    };
  });
  $effect(() => {
    setTileCachePersistenceAllowed(!active || (mode === 'public-release' && !mapState.navigationViewport));
  });
  $effect(() => {
    const enabled = active && mode === 'public-release' && !mapState.navigationViewport && worldTuning.enabled;
    worldTuning.maxZoom; worldTuning.maxMiB;
    const instance = map;
    if (!enabled || !instance || !nativeStyleReady || startupStage !== 'ready') return;
    if ((navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData) return;
    let cancelled = false;
    let idleHandle: number | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const warm = () => { if (!cancelled && active) void warmWorldBaseline().catch(() => {}); };
    const schedule = () => {
      if (cancelled) return;
      if ('requestIdleCallback' in window) idleHandle = requestIdleCallback(warm, { timeout: 2000 });
      else timer = setTimeout(warm, 200);
    };
    // Unrelated raster/glyph requests must not prevent a cache reset from
    // restarting. Wait for camera movement, then use the browser's idle queue.
    if (!instance.isMoving()) schedule();
    else instance.once('moveend', schedule);
    return () => {
      cancelled = true; instance.off('moveend', schedule);
      if (idleHandle !== undefined) cancelIdleCallback(idleHandle);
      if (timer !== undefined) clearTimeout(timer);
      cancelWorldBaselineWarmup();
    };
  });
  $effect(() => {
    const enabled = active;
    nativeStyleReady;
    if (!map) return;
    const instance = map;
    if (!enabled) {
      lifecyclePaused = true; resumePending = true;
      terrainViewGeneration++; terrainViewAbort?.abort(); terrainPending = false;
      pendingSelectionFocus = null;
      mvtMotionController?.cancel(); jsonMotionController?.cancel(); nativeMotionController?.cancel();
      instance.stop(); activeFlight = false;
      if (boundsTimer) clearTimeout(boundsTimer);
      if (feedStatus === 'loading') { feedGeneration++; feedAbort?.abort(); requestedFeedSourceId = undefined; }
      return;
    }
    if (!lifecyclePaused) return;
    lifecyclePaused = false;
    void tick().then(() => {
      if (!active || map !== instance) return;
      if (nativeStyleReady && (instance.getPitch() > 0.5 || terrainEnabled)) setTerrain(true);
      instance.resize(); instance.triggerRepaint();
      requestAnimationFrame(() => { if (active && map === instance) resumePending = false; });
    });
  });
  $effect(() => {
    const basemap = mapState.basemap;
    if (active && nativeStyleReady && map) applyWorldBaselineBasemap(map, basemap);
    if (active && map && appliedBasemap !== basemap) {
      void applyBasemapTiles(basemap);
    }
  });
  $effect(() => {
    records;
    if (active && mode === "synthetic" && map?.isStyleLoaded() && !usingMvt) setData();
  });
  $effect(() => {
    const source = mapState.sourceId;
    mapState.filters;
    mapMatchingIds;
    mapMatchesStatus;
    const releaseId = publicReleaseId;
    const releaseIdentity = publicReleaseIdentity;
    active;
    if (usingMvt && map?.isStyleLoaded()) {
      source;
      replaceMapProjection();
    } else if (isNativeMap() && map) {
      source; releaseId; releaseIdentity;
      return ensureNativeFeedWhenStyleReady();
    }
  });
  $effect(() => {
    searchScope;
    if (active && map?.isStyleLoaded()) syncSearchScope(map);
  });
  $effect(() => {
    const viewport = mapState.viewport;
    if (!active || !map) return;
    // A search selection deliberately animates away from the previous URL
    // viewport. Do not snap it back while that flight is in progress.
    if (activeFlight) return;
    const center = map.getCenter();
    if (
      Math.abs(center.lat - viewport.centerLat) < 0.001 &&
      Math.abs(center.lng - viewport.centerLon) < 0.001 &&
      map.getZoom() === viewport.zoom &&
      Math.abs(map.getPitch() - (viewport.pitch ?? 0)) < 0.1 &&
      Math.abs(map.getBearing() - (viewport.bearing ?? 0)) < 0.1
    )
      return;
    syncing = true;
    pendingSelectionFocus = null;
    selectionFocus = null;
    map.jumpTo({
      center: [viewport.centerLon, viewport.centerLat],
      zoom: viewport.zoom,
      pitch: viewport.pitch ?? 0,
      bearing: viewport.bearing ?? 0,
    });
    syncing = false;
  });
  $effect(() => {
    const target = flightTarget;
    if (!active || !map || !target || target.id === handledFlightId) return;
    handledFlightId = target.id;
    selectionFocus = mapState.selectedId ? { id: mapState.selectedId, center: [target.longitude, target.latitude] } : null;
    pendingSelectionFocus = [target.longitude, target.latitude];
    activeFlight = true;
    const camera = { center: [target.longitude, target.latitude] as [number, number], zoom: target.zoom };
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      map.jumpTo(camera);
    } else {
      map.flyTo({ ...camera, essential: false, speed: 2.8, curve: 1.2 });
    }
  });
  $effect(() => {
    const loading = referenceLoading,
      pending = pendingReference;
    if (!pending) return;
    if (loading && !pending.observedLoading) {
      pendingReference = { ...pending, observedLoading: true };
      return;
    }
    if (!loading && pending.observedLoading) pendingReference = undefined;
  });
  $effect(() => {
    if (diagnosticsOpen && usingMvt && map) updateMvtDiagnostics(map);
    if (diagnosticsOpen && isNativeMap() && map?.getLayer("clusters"))
      nativeRenderedCount = map.queryRenderedFeatures({ layers: ["clusters", "aggregate-outer", "approx-reference-pins", "approx-reference-circles", "approx-reference-points", "source-coordinate-points", "v1-source-pins"] }).length;
  });
</script>

<svelte:window
  onkeydown={(event) => {
    if (event.key !== "Escape") return;
    if (diagnosticsOpen) setDiagnosticsOpen(false);
  }}
/>
{#if mode !== "synthetic" && feedStatus === "error"}<small class="map-status mvt-status" role="alert"
    >{mvtError}</small
  >{/if}
{#if mode === 'public-release' && mapMatchesStatus === 'error'}<small class="map-status" role="alert">{mapMatchesError || 'Matching map locations could not be loaded.'}</small>{/if}
<section
  class:diagnostics-active={diagnosticsOpen}
  class="map-surface"
  aria-label={tr('Map showing records', $language)}
>
  <div class="map-host" bind:this={host}></div>
  {#if rendererUnavailable}<p class="map-status" role="alert">{tr('Map unavailable in this browser.', $language)}</p>{/if}
  {#if terrainError}<small class="map-status terrain-status" role="alert">{terrainError}</small>{/if}
  {#if terrainPending}<small class="map-status terrain-status" role="status">{tr('Loading terrain…', $language)}</small>{/if}
  {#if basemapSwitching && pendingBasemap}<small
      class="map-status"
      role="status"
      aria-live="polite"
      >Loading {basemapLabel(pendingBasemap)} imagery…</small
    >{:else if basemapError}<small class="map-status" role="alert">{basemapError}</small
    >{:else if pendingReference}<small
      class="map-status reference-status"
      role="status"
      >Loading {pendingReference.count || "represented"} reference records…</small
    >{:else if isNativeMap() && startupStage !== "ready" && feedStatus !== "error"}<div
      class="map-status startup-status"
      role="status" aria-live="polite">
        <span>{mode === 'public-release' ? tr(publicMapLoadingLabel(nativeCacheStatus, indexCacheDiagnostic?.state ?? null), $language) : startupStage === "initializing" ? "Preparing map · step 1 of 4" : startupStage === "fetching" ? "Fetching map projection · step 2 of 4" : startupStage === "indexing" ? "Preparing map marks · step 3 of 4" : "Drawing map marks · step 4 of 4"}</span>
        <div class="startup-track" role="progressbar" aria-label="Map preparation in progress"><i class:fetching={startupStage === "fetching"} class:indexing={startupStage === "indexing"} class:rendering={startupStage === "rendering"}></i></div>
      </div
    >{:else if mode === "real-preview" && mapTruncated && !usingMvt}<small
      class="map-status"
      role="status"
      >Map page limit reached; zoom in to load a smaller area.</small
    >{/if}{#if diagnosticsEnabled && !suppressDiagnostics}<button
      class="diagnostics-toggle"
      bind:this={diagnosticsToggle}
      type="button"
      aria-expanded={diagnosticsOpen}
      aria-controls="map-diagnostics"
      onclick={() => setDiagnosticsOpen(!diagnosticsOpen)}
      >{tr('Debug menu', $language)}</button
    >{#if diagnosticsOpen}<MapDebugPanel
      session={debugSession} renderer={debugRenderer}
      errors={[mapError && 'Map request failed', mapMatchesError && 'Matching pins request failed', basemapError && 'Basemap request failed', terrainError && 'Terrain unavailable', clusterSettingsError, pinModeError, mvtError && 'Tile request failed'].filter(Boolean)}
      clusterMode={debugClusterMode} {clusterRadius} {clusterMaxZoom} clusterDuration={clusterZoomDuration} {clusterMotionDuration} {clusterMotionLimit} rebuildDelay={clusterRebuildDebounce}
      {pinScale} usePins={useV1Pins} {coordinateRadius} privateReferences={isRealPreview() && !usingMvt}
      referenceRadius={referenceRadiusKm} {referenceOpacity} referenceLabels={showReferenceLabels}
      layout={layoutTuning} snapshot={diagnosticSnapshot} onclose={() => setDiagnosticsOpen(false)}
      {cacheTuning} tileFadeUnavailable={terrainEnabled} oncache={updateCacheTuning} onresetcaches={resetCacheTuning} onclearindex={clearBuiltIndex} oncleartiles={clearViewedTiles}
      {worldTuning} onworld={updateWorldTuning} onclearworld={clearWorldCache}
      oncluster={(key, value) => { if (key === 'mode') clusterEnabledOverride = value === 'auto' ? null : value === 'on'; else if (key === 'radius') clusterRadius = Number(value); else clusterMaxZoom = Number(value); scheduleClusterSettings(); }}
      onvisual={(key, value) => { if (key === 'pins') { useV1Pins = Boolean(value); void updatePinMode(); } else { if (key === 'pinScale') pinScale = Number(value); else if (key === 'coordinateRadius') coordinateRadius = Number(value); else if (key === 'referenceRadius') referenceRadiusKm = Number(value); else if (key === 'referenceOpacity') referenceOpacity = Number(value); else showReferenceLabels = Boolean(value); updateVisualSettings(); } }}
      oninteraction={(key, value) => { nativeMotionController?.cancel(); if (key === 'duration') clusterZoomDuration = value; else if (key === 'motionDuration') clusterMotionDuration = value; else if (key === 'motionLimit') clusterMotionLimit = value; else clusterRebuildDebounce = value; }}
      onlayout={value => onLayoutTuningChange?.(value)} onreset={resetTemporarySettings} onclearcache={clearProjectionCache}
    />{/if}{/if}{#if false && mode === "real-preview" && !usingMvt && hasMapFeatures}<button
      class="feature-list-toggle"
      type="button"
      aria-expanded={featureListOpen}
      aria-controls="map-feature-list"
      onclick={() => (featureListOpen = !featureListOpen)}
      >Map features <span
        >{featureListOpen ? accessibleFeatures.length : ""}</span
      ></button
    >{#if featureListOpen}<nav
        id="map-feature-list"
        class="accessible-map-features"
        aria-label="Visible map features"
      >
        <header>
          <strong>Visible map features</strong><button
            type="button"
            aria-label="Close map features"
            onclick={() => (featureListOpen = false)}>×</button
          >
        </header>
        <small>City references are approximate, not facility points.</small
        >{#each accessibleFeatures as feature}<button
            type="button"
            onclick={() =>
              feature.kind === "aggregate"
                ? onaggregate(feature.members.map((member) => member.id))
                : onselect(feature.record.id)}>{feature.label}</button
          >{/each}{#if accessibleAggregates.length + approximateSourceFeatures.length > accessibleFeatures.length}<small
            >Showing the first {accessibleFeatures.length} visible features. Zoom
            in to narrow the list.</small
          >{/if}
      </nav>{/if}{/if}
  {#if false && mode === "real-preview" && usingMvt && mvtAccessibleFeatures.length > 0}<button
      class="feature-list-toggle"
      type="button"
      aria-expanded={featureListOpen}
      aria-controls="map-feature-list"
      onclick={() => (featureListOpen = !featureListOpen)}
      >Map features <span>{featureListOpen ? mvtAccessibleFeatures.length : ""}</span></button
    >{#if featureListOpen}<nav
        id="map-feature-list"
        class="accessible-map-features"
        aria-label="Visible map features"
      >
        <header>
          <strong>Visible map features</strong><button
            type="button"
            aria-label="Close map features"
            onclick={() => (featureListOpen = false)}>×</button
          >
        </header>
        <small>Approximate city and area references are not facility points.</small>
        {#each mvtAccessibleFeatures as feature}<button
            type="button"
            onclick={() => feature.kind === "reference" ? onreference?.(feature.key) : onselect(feature.key)}>{feature.label}</button
          >{/each}
      </nav>{/if}{/if}
</section>

<style>
  .map-surface {
    position: relative;
    overflow: hidden;
  }
  .map-host {
    position: absolute;
    inset: 0;
  }
  .terrain-status { top:6.8rem; left:.65rem; transform:none; }
  .feature-list-toggle,
  .diagnostics-toggle {
    position: absolute;
    z-index: 4;
    right: 0.5rem;
    bottom: 10.5rem;
    min-height: 2rem;
    padding: 0.3rem 0.5rem;
    border: 1px solid #69716a;
    color: #f1efe8;
    background: #171a18e8;
    font: 0.65rem system-ui;
    cursor: pointer;
  }
  .diagnostics-toggle {
    min-height: 44px;
    min-width: 44px;
    right: auto;
    bottom: 0.65rem;
    left: 1rem;
    border-color: var(--line-strong);
    background: var(--panel);
    color: var(--ink);
    font-size: .75rem;
  }
  .feature-list-toggle span {
    margin-left: 0.3rem;
    color: #c6cbc4;
  }
  .accessible-map-features {
    position: absolute;
    z-index: 6;
    right: 0.5rem;
    bottom: 10.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    width: min(22rem, calc(100vw - 1rem));
    max-height: min(48vh, 25rem);
    overflow: auto;
    padding: 0.6rem;
    border: 1px solid #69716a;
    background: #171a18f2;
    color: #f1efe8;
    font: 0.65rem system-ui;
  }
  .accessible-map-features header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .accessible-map-features header button {
    width: 1.6rem;
    text-align: center;
  }
  .accessible-map-features small {
    color: #c6cbc4;
  }
  .accessible-map-features button {
    padding: 0.35rem 0.45rem;
    border: 1px solid #48504b;
    color: inherit;
    background: #202421;
    text-align: left;
    cursor: pointer;
  }
  .map-status {
    position: absolute;
    z-index: 3;
    top: 1rem;
    left: 50%;
    max-width: min(28rem, 80vw);
    padding: 0.35rem 0.55rem;
    border: 1px solid #48504b;
    background: #171a18e8;
    color: #f1efe8;
    font: 0.65rem system-ui;
    transform: translateX(-50%);
  }
  .startup-status { top: auto; bottom: 2.2rem; width: min(19rem, 72vw); display: grid; gap: 0.45rem; }
  .startup-track { height: 0.26rem; overflow: hidden; background: #48504b; }
  .startup-track i { position: relative; display: block; width: 22%; height: 100%; background: #a5b8a6; }
  .startup-track i.fetching { width: 47%; }
  .startup-track i.indexing { width: 72%; }
  .startup-track i.rendering { width: 94%; }
  .startup-track i::after { content: ""; position: absolute; inset: 0; background: #f1efe899; transform: translateX(-100%); animation: startup-sweep 1.15s ease-in-out infinite; }
  @keyframes startup-sweep { to { transform: translateX(100%); } }
  @media (prefers-reduced-motion: reduce) { .startup-track i::after { animation: none; } }
  .map-surface :global(.precision-legend) { bottom: 3.4rem; }
  .map-surface :global(.maplibregl-ctrl-attrib) {
    border: 1px solid #48504b;
    background: #171a18ed;
    color: #d9ded5;
    font: 0.59rem/1.3 system-ui;
  }
  .map-surface :global(.maplibregl-ctrl-attrib a) { color: #c1d4cf; }
  .map-surface :global(.maplibregl-ctrl-attrib-button) { filter: invert(1); }
  @media (max-width: 40rem) {
    .map-surface :global(.precision-legend) { bottom: 9.4rem; width: auto; max-width: min(15rem, calc(100vw - 1.3rem)); }
    .map-surface :global(.precision-legend.expanded) { top: 3.5rem; bottom: auto; width: min(15rem, calc(100vw - 1.3rem)); }
    .map-surface :global(.maplibregl-ctrl-bottom-right) { right: 0.4rem; bottom: 0.4rem; left: auto; }
    .map-surface :global(.maplibregl-ctrl-attrib) { max-width: 100%; padding: 0.16rem 0.35rem; }
    .map-status {
      top: 3.2rem;
    }
    .startup-status { top: auto; bottom: 3.2rem; }
    .feature-list-toggle {
      bottom: 9rem;
    }
    .diagnostics-toggle {
      top: auto;
      right: auto;
      bottom: 5.7rem;
      left: 0.65rem;
    }
    .map-surface.diagnostics-active :global(.precision-legend) {
      display: none;
    }
    .map-surface.diagnostics-active .feature-list-toggle {
      display: none;
    }
  }
</style>
