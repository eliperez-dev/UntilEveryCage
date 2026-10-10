<script lang="ts">
  /**
   * MapSurface is the composition boundary:
   * This component owns MapLibre event wiring. The private preview uses one
   * in-memory native cluster source; camera movement must never reload it.
   * Synthetic fixtures retain their own transition controller.
   */
  import { onMount } from "svelte";
  import * as maplibregl from "maplibre-gl";
  import mapLibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
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
  import PrecisionLegend from "./PrecisionLegend.svelte";
  const SHOW_PRECISION_LEGEND = false;
  import { MvtMotionController } from "./mvtMotionController";
  import { JsonClusterMotionController } from "./jsonClusterMotionController";
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
  } from "./realPreviewMapLayers";
  import { clearRealPreviewMapCache, createRealPreviewMapFeedRepository, realPreviewMapCacheEntryCount } from "../../api/RealPreviewMapFeedRepository";
  import { clearTestReleaseMapCache, createTestReleaseMapFeedRepository, testReleaseMapCacheEntryCount } from "../../api/TestReleaseMapFeedRepository";
  import { canReusePublicMapFeed, clearPublicMapCache, createPublicMapFeedRepository, publicMapCacheEntryCount } from "../../api/PublicMapFeedRepository";

  let {
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
    mapDiagnostics,
    referenceLoading = false,
    flightTarget = null,
    suppressDiagnostics = false,
    debugEnabled = false,
    onmaptiming,
    onselect,
    onaggregate,
    onreference,
    onbasemap,
    ondebugopenchange,
    onviewport,
    onbounds,
  }: {
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
    mapDiagnostics?: MapDiagnostics | undefined;
    referenceLoading?: boolean;
    flightTarget?: Readonly<{ id: number; longitude: number; latitude: number; zoom: number }> | null;
    suppressDiagnostics?: boolean;
    debugEnabled?: boolean;
    onmaptiming?(timing: MapTiming): void;
    onselect(id: string): void;
    onaggregate(memberIds: readonly string[]): void;
    onreference?(key: string, sourceId?: string): void;
    onbasemap(value: Basemap): void;
    ondebugopenchange?(open: boolean): void;
    onviewport(value: Viewport): void;
    onbounds?(bounds: ViewportBounds): void;
  } = $props();
  let host: HTMLDivElement;
  let map: MapLibreMap | undefined;
  let nativeStyleReady = $state(false);
  let appliedBasemap = $state<Basemap | undefined>();
  let basemapSwitching = $state(false);
  let pendingBasemap = $state<Basemap | undefined>();
  let basemapError = $state("");
  let basemapRequest = 0;
  let syncing = false;
  let activeFlight = false;
  let handledFlightId = 0;
  let interactionsBound = false;
  let mvtError = $state("");
  const mapFeedRepository = createRealPreviewMapFeedRepository();
  const candidateMapFeedRepository = createTestReleaseMapFeedRepository();
  const publicMapFeedRepository = createPublicMapFeedRepository();
  let feedAbort: AbortController | undefined;
  let feedGeneration = 0;
  let requestedFeedSourceId: string | null | undefined;
  let requestedPublicReleaseId: string | null | undefined;
  let requestedPublicReleaseIdentity: string | null | undefined;
  let nativeFullCollection: JsonMapCollection | undefined;
  // Viewport updates replace `state`; only a changed source filter may rebuild
  // the native Supercluster index from the already-loaded map projection.
  let appliedNativeSourceId: string | null | undefined;
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
  let clusterEnabled = $state(true);
  let referenceRadiusKm = $state<number>(DEFAULT_REFERENCE_RADIUS_KM);
  let referenceOpacity = $state(0.08);
  let visibleApproximateCount = $state(0);
  let coordinateRadius = $state(6.5);
  let showReferenceLabels = $state(false);
  let useV1Pins = $state(false);
  let pinModeError = $state("");
  let clusterZoomDuration = $state(460);
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
  const diagnosticsEnabled = $derived(import.meta.env.DEV && mode !== "synthetic" && debugEnabled);
  const isRealPreview = () => mode === "real-preview" || mode === "candidate-preview";
  const isNativeMap = () => mode !== "synthetic";
  // The private development preview intentionally uses the reviewed, in-memory
  // GeoJSON/Supercluster path. The server-generated MVT implementation remains
  // available for public releases and future experiments, but must not sit in
  // the camera interaction path for this preview.
  const usingMvt = false;
  const hitRate = $derived.by(() => {
    const total =
      (mapDiagnostics?.cacheHits ?? 0) + (mapDiagnostics?.cacheMisses ?? 0);
    return total ? Math.round((mapDiagnostics!.cacheHits / total) * 100) : 0;
  });
  maplibregl.setWorkerUrl(mapLibreWorkerUrl);

  function style(): any {
    return createBaseStyle(mapState.basemap);
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
      const timeout = setTimeout(() => finish(false), 10000);
      const onError = (event: any) => {
        if (event?.sourceId === sourceId) finish(false);
      };
      const onData = (event: any) => {
        if (event?.sourceId === sourceId && instance.isSourceLoaded(sourceId))
          finish(true);
      };
      function finish(ok: boolean) {
        clearTimeout(timeout);
        instance.off("error", onError);
        instance.off("sourcedata", onData);
        ok ? resolve() : reject(new Error("Basemap tiles unavailable"));
      }
      instance.on("error", onError);
      instance.on("sourcedata", onData);
    });
  }
  async function applyBasemapTiles(basemap: Basemap) {
    const instance = map;
    if (!instance || basemapSwitching || appliedBasemap === basemap) return;
    // Street and Muted Street share one OSM source. Only paint changes.
    if (basemap !== "satellite" && appliedBasemap !== "satellite") {
      applyBaseAppearance(instance, basemap);
      appliedBasemap = basemap;
      basemapError = "";
      onbasemap(basemap);
      return;
    }
    const request = ++basemapRequest;
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
      instance.addLayer(
        { id: "candidate-base", type: "raster", source: "candidate-base" },
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
    if (!map.hasImage("cluster-mixed-low"))
      map.addImage("cluster-mixed-low", clusterImage("#79b9da99", "#6ecc39b8"));
    if (!map.hasImage("cluster-mixed-mid"))
      map.addImage("cluster-mixed-mid", clusterImage("#79b9da99", "#f0c20cb8"));
    if (!map.hasImage("cluster-mixed-high"))
      map.addImage("cluster-mixed-high", clusterImage("#79b9da99", "#f18017b8"));
    if (!map.hasImage("cluster-mixed-very-high"))
      map.addImage("cluster-mixed-very-high", clusterImage("#79b9da99", "#de6d3fb8"));
    if (!map.hasImage("cluster-approx"))
      map.addImage("cluster-approx", clusterImage("#79b9da99", "#79b9dad9"));
  }
  function scheduleClusterSettings() {
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
        await source.setClusterOptions({
          cluster: clusterEnabled,
          clusterRadius,
          clusterMaxZoom: nativeClusterMaxZoom(clusterMaxZoom),
        });
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
      if (map.getLayer("mvt-approx-reference-area"))
        map.setPaintProperty("mvt-approx-reference-area", "fill-opacity", referenceOpacity * 0.4);
      if (map.getLayer("mvt-source-coordinates"))
        map.setPaintProperty("mvt-source-coordinates", "circle-radius", coordinateRadius);
      if (map.getLayer("mvt-reference-kind"))
        map.setLayoutProperty("mvt-reference-kind", "visibility", showReferenceLabels ? "visible" : "none");
      return;
    }
    applyRealPreviewVisualSettings(map, {
      referenceRadiusKm,
      referenceOpacity,
      coordinateRadius,
      showReferenceLabels,
      selectedKey: selectedReferenceKey ?? mapState.selectedId,
    });
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
    ondebugopenchange?.(open);
    if (!open && restoreFocus) diagnosticsToggle?.focus();
  }
  $effect(() => {
    mapState.selectedId;
    if (map?.isStyleLoaded()) updateVisualSettings();
  });
  $effect(() => {
    if (suppressDiagnostics && diagnosticsOpen) setDiagnosticsOpen(false, false);
  });
  async function updatePinMode() {
    const instance = map;
    if (!instance || !isNativeMap()) return;
    try {
      await setRealPreviewPinMode(instance, useV1Pins, `${import.meta.env.BASE_URL}v1-pins/`);
      pinModeError = "";
    } catch {
      useV1Pins = false;
      pinModeError = "The V1 pin images could not be loaded.";
    }
  }
  async function addLayers() {
    if (!map || map.getSource("locations")) return;
    loadClusterImages();
    if (mode === "public-release" && !publicReleaseId) return;
    if (mode !== "synthetic") {
      if (mode === "public-release" && nativeFullCollection
        && requestedPublicReleaseId === publicReleaseId
        && requestedPublicReleaseIdentity === publicReleaseIdentity) {
        addRealPreviewMapLayers(map, filteredNativeCollection(nativeFullCollection, mapState.sourceId), { enabled: clusterEnabled, radius: clusterRadius, maxZoom: clusterMaxZoom });
        setRealPreviewCategoryFilter(map, publicCategoryFilterKeys());
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
    if (!instance) return;
    if (mode === "public-release" && !publicReleaseId) return;
    if (mode === "public-release" && (requestedPublicReleaseId !== publicReleaseId || requestedPublicReleaseIdentity !== publicReleaseIdentity)) {
      requestedPublicReleaseId = publicReleaseId;
      requestedPublicReleaseIdentity = publicReleaseIdentity;
      requestedFeedSourceId = undefined;
      nativeFullCollection = undefined;
      if (instance.getSource("locations")) setRealPreviewMapData(instance, { type: "FeatureCollection", features: [] });
    }
    const sourceId = null;
    if (requestedFeedSourceId === sourceId &&
        (feedStatus === "loading" || (feedStatus === "ready" && instance.getSource("locations")))) return;
    requestedFeedSourceId = sourceId;
    feedAbort?.abort();
    const controller = new AbortController();
    feedAbort = controller;
    const generation = ++feedGeneration;
    feedStatus = "loading";
    startupStage = "fetching";
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
      if (controller.signal.aborted || map !== instance || generation !== feedGeneration) return;
      onMapFeedMeta?.("meta" in result ? result.meta : null);
      onCandidatePreviewLabel?.("previewLabel" in result ? result.previewLabel ?? null : null);
      nativeSnapshotId = "snapshotId" in result ? result.snapshotId : result.meta.manifestSha256;
      nativeCacheStatus = "cacheStatus" in result ? result.cacheStatus : "not cached";
      nativeDecodedBytes = "decodedBytes" in result ? result.decodedBytes ?? null : new TextEncoder().encode(JSON.stringify(result.collection)).byteLength;
      nativeCacheEntries = publicReleaseId ? await publicMapCacheEntryCount() : mode === "candidate-preview" ? await testReleaseMapCacheEntryCount() : await realPreviewMapCacheEntryCount();
      nativeFeedMs = Math.round(performance.now() - requestedAt);
      nativeUnitCount = result.collection.features.length;
      nativeRepresentedCount = result.collection.features.reduce((total, feature) => total + Number(feature.properties.weight), 0);
      nativeApproximateCount = result.collection.features.filter((feature) => feature.properties.precision === "approximate").length;
      nativeFullCollection = result.collection;
      nativeIndexStartedAt = performance.now();
      startupStage = "indexing";
      const visible = filteredNativeCollection(result.collection, mapState.sourceId);
      if (instance.getSource("locations")) setRealPreviewMapData(instance, visible);
      else addRealPreviewMapLayers(instance, visible, { enabled: clusterEnabled, radius: clusterRadius, maxZoom: clusterMaxZoom });
      appliedNativeSourceId = mapState.sourceId;
      roundedClusterTilesAvailable = setClusterTileRounding(instance, clusterMaxZoom);
      if (useRoundedClusterTiles(clusterMaxZoom) && !roundedClusterTilesAvailable)
        clusterSettingsError = `This MapLibre build cannot apply half-zoom tile selection; effective cutoff is zoom ${nativeClusterMaxZoom(clusterMaxZoom) + 1}.`;
      updateVisualSettings();
      if (useV1Pins) void updatePinMode();
      feedStatus = "ready";
    } catch (error) {
      if (controller.signal.aborted || generation !== feedGeneration) return;
      feedStatus = "error";
      onMapFeedMeta?.(null);
      mvtError = error instanceof Error ? error.message : "The map feed could not be loaded.";
    }
  }

  $effect(() => {
    if (mode === "public-release" && map) {
      setRealPreviewCategoryFilter(map, publicCategoryFilterKeys());
    }
  });
  function publicCategoryFilterKeys(): string[] {
    const keys: Record<string, string> = {
      Poultry: "animal_keeping_and_production", Pig: "animal_keeping_and_production",
      Dairy: "animal_keeping_and_production", Aquaculture: "animal_keeping_and_production",
      Processing: "processing_and_preparation", Laboratory: "research_and_animal_use",
    };
    return [...new Set(mapState.filters.categories.map(value => keys[value]).filter((value): value is string => !!value))];
  }
  function filteredNativeCollection(collection: JsonMapCollection, sourceId: string | null): JsonMapCollection {
    return sourceId
      ? { ...collection, features: collection.features.filter((feature) => feature.properties.source_id === sourceId) }
      : collection;
  }
  function applyLocalSourceFilter(sourceId: string | null) {
    if (!map || !nativeFullCollection || !map.getSource("locations")) return;
    if (appliedNativeSourceId === sourceId) return;
    nativeIndexStartedAt = performance.now();
    startupStage = "indexing";
    setRealPreviewMapData(map, filteredNativeCollection(nativeFullCollection, sourceId));
    appliedNativeSourceId = sourceId;
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
          appliedNativeSourceId = undefined;
          if (instance.getSource("locations")) setRealPreviewMapData(instance, { type: "FeatureCollection", features: [] });
          onMapFeedMeta?.(null);
          feedStatus = "error";
          startupStage = "ready";
          mvtError = "No current public map release is available.";
        }
      } else if (canReusePublicMapFeed(publicReleaseId, publicReleaseIdentity, requestedPublicReleaseId, requestedPublicReleaseIdentity, !!nativeFullCollection)) {
        applyLocalSourceFilter(mapState.sourceId);
      } else {
        void loadNativeFeed();
      }
    } else if (nativeFullCollection) applyLocalSourceFilter(mapState.sourceId);
    else void loadNativeFeed();
    return () => {};
  }
  async function clearProjectionCache() {
    const removed = publicReleaseId ? (await clearPublicMapCache(), 1) : mode === "candidate-preview" ? await clearTestReleaseMapCache() : await clearRealPreviewMapCache();
    nativeCacheEntries = 0;
    cacheClearStatus = publicReleaseId ? "Cleared public map projection cache." : removed ? `Cleared ${removed} cached projection ${removed === 1 ? "entry" : "entries"}.` : "Projection cache was already empty.";
  }
  function addMvtLayers() {
    if (!map) return;
    addMvtLocationLayers(map, mapState.sourceId ?? undefined);
    appliedMvtTileSignature = `${mapState.sourceId ?? ""}:${clusterMaxZoom}`;
    updateVisualSettings();
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
      "mvt-reference-outer",
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

  function destinationPoint(longitude: number, latitude: number, bearing: number, distanceKm: number): [number, number] {
    const radiusKm = 6371.0088;
    const angular = distanceKm / radiusKm;
    const lat1 = latitude * Math.PI / 180;
    const lon1 = longitude * Math.PI / 180;
    const bearingRad = bearing * Math.PI / 180;
    const lat2 = Math.asin(Math.sin(lat1) * Math.cos(angular) + Math.cos(lat1) * Math.sin(angular) * Math.cos(bearingRad));
    const lon2 = lon1 + Math.atan2(Math.sin(bearingRad) * Math.sin(angular) * Math.cos(lat1), Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2));
    return [((lon2 * 180 / Math.PI + 540) % 360) - 180, lat2 * 180 / Math.PI];
  }

  function syncMvtReferenceAreas(instance: MapLibreMap) {
    const areaSource = instance.getSource("mvt-reference-areas") as GeoJSONSource | undefined;
    if (!areaSource || !instance.getSource("preview-mvt") || !instance.isSourceLoaded("preview-mvt")) return;
    const unique = new Map<string, any>();
    for (const feature of instance.querySourceFeatures("preview-mvt", { sourceLayer: "uec_preview" }) as any[]) {
      if (feature.properties?.kind !== "city_reference" || feature.geometry?.type !== "Point") continue;
      const key = feature.properties?.feature_key;
      const coordinates = feature.geometry.coordinates;
      if (typeof key !== "string" || !Array.isArray(coordinates) || coordinates.length < 2) continue;
      const longitude = Number(coordinates[0]);
      const latitude = Number(coordinates[1]);
      if (!Number.isFinite(longitude) || !Number.isFinite(latitude) || unique.has(key)) continue;
      const ring: [number, number][] = [];
      for (let bearing = 0; bearing <= 360; bearing += 15)
        ring.push(destinationPoint(longitude, latitude, bearing, referenceRadiusKm));
      unique.set(key, {
        type: "Feature",
        properties: { feature_key: key },
        geometry: { type: "Polygon", coordinates: [ring] },
      });
    }
    areaSource.setData({ type: "FeatureCollection", features: [...unique.values()] } as any);
  }

  function updateMvtAccessibleFeatures(instance: MapLibreMap) {
    const rendered = instance.queryRenderedFeatures({
      layers: ["mvt-clusters", "mvt-reference-outer", "mvt-reference-center", "mvt-source-coordinates"],
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
    if (host.parentElement) {
      // Each projection owns exactly one overlay canvas. The fixture fallback
      // must not mount the real-preview MVT transition system, or vice versa.
      if (usingMvt) mvtMotionController.attach(host.parentElement);
      else if (mode === "synthetic") jsonMotionController.attach(host.parentElement);
    }
    return () => {
      mvtMotionController?.dispose();
      jsonMotionController?.dispose();
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
    };
    queueMicrotask(() => {
      instance = map;
      instance?.on("zoomstart", onZoomStart);
    });
    return () => instance?.off("zoomstart", onZoomStart);
  });
  function bindInteractions() {
    if (!map) return;
    if (usingMvt) {
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
        const key = event.features?.[0]?.properties?.feature_key;
        if (typeof key === "string" && /^[0-9a-f-]{36}$/i.test(key))
          onselect(key);
      });
      map.on("click", "mvt-v1-source-pins", (event: any) => {
        if (activeFlight) return;
        const key = event.features?.[0]?.properties?.feature_key;
        if (typeof key === "string" && /^[0-9a-f-]{36}$/i.test(key)) onselect(key);
      });
      map.on("click", "mvt-reference-outer", (event: any) => {
        if (activeFlight) return;
        const feature = event.features?.[0],
          key = feature?.properties?.feature_key,
          count = Number(feature?.properties?.count);
        if (typeof key === "string" && /^[a-f0-9]{32}$/i.test(key)) {
          pendingReference = {
            key,
            count: Number.isFinite(count) ? count : 0,
            observedLoading: false,
          };
          onreference?.(key);
        }
      });
      map.on("click", "mvt-approx-reference-area", (event: any) => {
        if (activeFlight) return;
        const key = event.features?.[0]?.properties?.feature_key;
        if (typeof key !== "string" || !/^[a-f0-9]{32}$/i.test(key)) return;
        pendingReference = { key, count: 0, observedLoading: false };
        onreference?.(key);
      });
      map.on("click", "mvt-reference-center", (event: any) => {
        if (activeFlight) return;
        const feature = event.features?.[0],
          key = feature?.properties?.feature_key,
          count = Number(feature?.properties?.count);
        if (typeof key === "string" && /^[a-f0-9]{32}$/i.test(key)) {
          pendingReference = {
            key,
            count: Number.isFinite(count) ? count : 0,
            observedLoading: false,
          };
          onreference?.(key);
        }
      });
      for (const layer of [
        "mvt-clusters",
        "mvt-source-coordinates",
        "mvt-v1-source-pins",
        "mvt-reference-outer",
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
      ? ["source-coordinate-points"]
      : ["exact-pins", "approximate-points", "source-coordinate-points"])
      map.on("click", layer, (event: any) => {
        if (activeFlight) return;
        const properties = event.features?.[0]?.properties;
        const id = isRealPreview() ? properties?.key : properties?.id;
        if (typeof id === "string") onselect(id);
      });
    const handleReferenceClick = (event: any, layer: "aggregate-outer" | "approx-reference-points") => {
      if (activeFlight) return;
      if (isRealPreview()) {
        const properties = event.features?.[0]?.properties;
        const city = properties?.precision === "city" || properties?.precision === "city_reference_approximate";
        // The center icon overlays the geographic circle at every zoom. Let
        // its own handler own center clicks; the outer circle owns area clicks.
        if (city && layer === "aggregate-outer" && map && event.point && event.features?.[0]?.geometry?.coordinates) {
          const center = map.project(event.features[0].geometry.coordinates);
          if (Math.hypot(event.point.x - center.x, event.point.y - center.y) <= 20 * APPROX_MARKER_SCALE) return;
        }
        const key = properties?.key;
        if (typeof key === "string") {
          selectedReferenceKey = key;
          updateVisualSettings();
          const count = Number(properties?.weight);
          pendingReference = { key, count: Number.isFinite(count) ? count : 0, observedLoading: false };
          onreference?.(key, typeof properties?.source_id === "string" ? properties.source_id : undefined);
        }
        return;
      }
      if (mode === "public-release") {
        const id = event.features?.[0]?.properties?.id;
        if (typeof id === "string") onselect(id);
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
    if (isNativeMap())
      map.on("click", "approx-reference-points", (event: any) => handleReferenceClick(event, "approx-reference-points"));
    for (const layer of isNativeMap()
      ? ["clusters", "source-coordinate-points", "aggregate-outer", "approx-reference-points"]
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
    mvtInitialStartedAt = performance.now();
    mvtResourceWindowStart = mvtInitialStartedAt;
    const instance = new maplibregl.Map({
      container: host,
      style: style(),
      center: [mapState.viewport.centerLon, mapState.viewport.centerLat],
      zoom: mapState.viewport.zoom,
      attributionControl: {},
      // The private preview owns one in-memory source, so pan and zoom never
      // replace location data. Disabling source fades keeps interaction crisp.
      fadeDuration: 0,
      // Let MapLibre size each source cache from the viewport. The previous
      // fixed 512-tile cap retained far more raster/MVT tiles than needed;
      // minTileCacheSize and prefetchZoomDelta are not MapLibre map options.
    } as any);
    map = instance;
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
    instance.on("style.load", () => {
      nativeStyleReady = true;
      if (usingMvt) {
        loadClusterImages();
        addMvtLayers();
      } else {
        void addLayers();
      }
      if (!interactionsBound) {
        bindInteractions();
        interactionsBound = true;
      }
      publishBounds();
      instance.resize();
    });
    instance.on("error", (event: any) => {
      if (usingMvt && event?.sourceId === "preview-mvt")
        mvtError =
          "Map tiles could not be refreshed. Try panning or selecting a different source.";
    });
    instance.on("movestart", (event: any) => {
      if (usingMvt) mvtCameraStartedAt ??= performance.now();
      if (isNativeMap()) nativeCameraStartedAt ??= performance.now();
      if (mode === "synthetic") {
        jsonMotionController?.cancel();
      }
    });
    instance.on("sourcedata", (event: any) => {
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
      if (isNativeMap() && startupStage === "rendering" &&
          instance.isSourceLoaded("locations")) startupStage = "ready";
    });
    instance.on("idle", () => {
      if (isNativeMap()) {
        updateVisibleApproximateCount(instance);
        if (startupStage === "rendering" && instance.isSourceLoaded("locations")) startupStage = "ready";
        if (nativeCameraStartedAt !== null) {
          nativeCameraIdleMs = Math.round(performance.now() - nativeCameraStartedAt);
          nativeCameraStartedAt = null;
        }
        if (diagnosticsOpen && instance.getLayer("clusters"))
          nativeRenderedCount = instance.queryRenderedFeatures({ layers: ["clusters", "aggregate-outer", "approx-reference-points", "source-coordinate-points", "v1-source-pins"] }).length;
      }
      if (usingMvt) {
        updateMvtDiagnostics(instance);
        updateMvtAccessibleFeatures(instance);
        mvtMotionController?.playExpansion();
        mvtMotionController?.playJoin();
      }
    });
    instance.on("moveend", () => {
      activeFlight = false;
      if (isNativeMap() && nativeCameraStartedAt !== null) {
        nativeCameraMoveendMs = Math.round(performance.now() - nativeCameraStartedAt);
        nativeBasemapPendingAtMoveend = !instance.isSourceLoaded("base");
        nativeOverlayPendingAtMoveend = !instance.isSourceLoaded("locations");
      }
      if (!syncing) {
        const center = instance.getCenter();
        onviewport({
          centerLat: Number(center.lat.toFixed(4)),
          centerLon: Number(center.lng.toFixed(4)),
          zoom: instance.getZoom(),
        });
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
    return () => {
      basemapRequest++;
      feedAbort?.abort();
      if (boundsTimer) clearTimeout(boundsTimer);
      if (clusterUpdateTimer) clearTimeout(clusterUpdateTimer);
      mvtMotionController?.cancel();
      jsonMotionController?.cancel();
      if (previewWindow.__UEC_LOCAL_PREVIEW_MAP__ === instance)
        delete previewWindow.__UEC_LOCAL_PREVIEW_MAP__;
      instance.remove();
    };
  });
  $effect(() => {
    const basemap = mapState.basemap;
    if (map && appliedBasemap !== basemap) {
      void applyBasemapTiles(basemap);
    }
  });
  $effect(() => {
    records;
    if (mode === "synthetic" && map?.isStyleLoaded() && !usingMvt) setData();
  });
  $effect(() => {
    const source = mapState.sourceId;
    const releaseId = publicReleaseId;
    const releaseIdentity = publicReleaseIdentity;
    if (usingMvt && map?.isStyleLoaded()) {
      source;
      replaceMapProjection();
    } else if (isNativeMap() && map) {
      source; releaseId; releaseIdentity;
      return ensureNativeFeedWhenStyleReady();
    }
  });
  $effect(() => {
    const viewport = mapState.viewport;
    if (!map) return;
    // A search selection deliberately animates away from the previous URL
    // viewport. Do not snap it back while that flight is in progress.
    if (activeFlight) return;
    const center = map.getCenter();
    if (
      Math.abs(center.lat - viewport.centerLat) < 0.001 &&
      Math.abs(center.lng - viewport.centerLon) < 0.001 &&
      map.getZoom() === viewport.zoom
    )
      return;
    syncing = true;
    map.jumpTo({
      center: [viewport.centerLon, viewport.centerLat],
      zoom: viewport.zoom,
    });
    syncing = false;
  });
  $effect(() => {
    const target = flightTarget;
    if (!map || !target || target.id === handledFlightId) return;
    handledFlightId = target.id;
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
      nativeRenderedCount = map.queryRenderedFeatures({ layers: ["clusters", "aggregate-outer", "approx-reference-points", "source-coordinate-points", "v1-source-pins"] }).length;
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
<section
  class:diagnostics-active={diagnosticsOpen}
  class="map-surface"
  aria-label="Map showing records"
>
  <div class="map-host" bind:this={host}></div>
  {#if isNativeMap() && visibleApproximateCount > 0}<small class="approximation-cue"
      ><i aria-hidden="true"></i>Approximate references · source precision varies</small
  >{/if}{#if basemapSwitching && pendingBasemap}<small
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
        <span>{startupStage === "initializing" ? "Preparing map · step 1 of 4" : startupStage === "fetching" ? "Fetching map projection · step 2 of 4" : startupStage === "indexing" ? "Building cluster index · step 3 of 4" : "Drawing map marks · step 4 of 4"}</span>
        <div class="startup-track" role="progressbar" aria-label="Map preparation in progress"><i class:fetching={startupStage === "fetching"} class:indexing={startupStage === "indexing"} class:rendering={startupStage === "rendering"}></i></div>
      </div
    >{:else if mode === "real-preview" && mapTruncated && !usingMvt}<small
      class="map-status"
      role="status"
      >Map page limit reached; zoom in to load a smaller area.</small
    >{/if}{#if diagnosticsEnabled && mapDiagnostics && !suppressDiagnostics}<button
      class="diagnostics-toggle"
      bind:this={diagnosticsToggle}
      type="button"
      aria-expanded={diagnosticsOpen}
      aria-controls="map-diagnostics"
      onclick={() => setDiagnosticsOpen(!diagnosticsOpen)}
      >Debug menu</button
    >{#if diagnosticsOpen}<aside
        id="map-diagnostics"
        class="map-diagnostics"
        aria-label="Debug menu"
      >
        <header>
          <strong>Debug menu</strong><button
            type="button"
            aria-label="Close debug menu"
            onclick={() => setDiagnosticsOpen(false)}>×</button
          >
        </header>
        <dl>
          {#if usingMvt}
            <div>
              <dt>Projection</dt>
              <dd>Server-generated vector tiles</dd>
            </div>
            <div>
              <dt>Source ready</dt>
              <dd>
                {mvtError
                  ? "Error"
                  : mvtSourceReady
                    ? `Ready${mvtSourceReadyMs === null ? "" : ` · ${mvtSourceReadyMs} ms`}`
                    : "Waiting for tiles"}
              </dd>
            </div>
            <div>
              <dt>Camera → idle</dt>
              <dd>
                {mvtCameraSettleMs === null ? "Not sampled" : `${mvtCameraSettleMs} ms`}
              </dd>
            </div>
            <div>
              <dt>Browser-visible MVT resources</dt>
              <dd>
                {mvtLoadedTileResources === 0
                  ? "No entries · worker requests may be hidden"
                  : `${mvtLoadedTileResources} entries since filter`}
                · {mvtTransferBytes === null ? "transfer size unavailable" : `${mvtTransferBytes.toLocaleString()} reported transfer bytes`}
                · {mvtRequestDurationMs === null ? "timing unavailable" : `${mvtRequestDurationMs} summed request-ms`}
              </dd>
            </div>
            <div>
              <dt>Rendered features</dt>
              <dd>
                {mvtRenderedFeatureCount === null
                  ? "Not sampled yet"
                  : `${mvtRenderedFeatureCount.toLocaleString()} on-screen`}
              </dd>
            </div>
            <div>
              <dt>Server cache</dt>
              <dd>Not exposed by API</dd>
            </div>
            <div>
              <dt>Source filter</dt>
              <dd>{mapDiagnostics.sourceId ?? "All sources"}</dd>
            </div>
          {:else}
            <div><dt>Snapshot</dt><dd title={nativeSnapshotId}>{nativeSnapshotId === "Not loaded" ? "Not loaded" : nativeSnapshotId.slice(0, 12)}</dd></div>
            <div>
              <dt>Projection / zoom</dt>
              <dd>Native MapLibre · {mapState.viewport.zoom.toFixed(1)}</dd>
            </div>
            <div>
              <dt>Map feed</dt>
              <dd>{feedStatus} · cache {nativeCacheStatus} · {nativeFeedRequests} request{nativeFeedRequests === 1 ? "" : "s"} · {nativeFeedMs === null ? "Not sampled" : `${nativeFeedMs} ms`}</dd>
            </div>
            <div><dt>Projection size</dt><dd>{nativeDecodedBytes === null ? "Unavailable" : `${(nativeDecodedBytes / 1_048_576).toFixed(2)} MB decoded`} · compressed transfer unavailable</dd></div>
            <div><dt>Projection cache</dt><dd>{nativeCacheEntries === null ? "Unavailable" : `${nativeCacheEntries} ${nativeCacheEntries === 1 ? "entry" : "entries"}`}</dd></div>
            <div>
              <dt>Loaded map units</dt>
              <dd>{nativeUnitCount.toLocaleString()} · {nativeRepresentedCount.toLocaleString()} represented</dd>
            </div>
            <div><dt>Approximate references</dt><dd>{nativeApproximateCount.toLocaleString()}</dd></div>
            <div>
              <dt>Cluster index ready</dt>
              <dd>{nativeIndexMs === null ? "waiting" : `${nativeIndexMs} ms`}</dd>
            </div>
            <div>
              <dt>Rendered marks</dt>
              <dd>{nativeRenderedCount === null ? "open menu and move map" : nativeRenderedCount.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Source filter</dt>
              <dd>{mapState.sourceId ?? "All sources"}</dd>
            </div>
            <div class="debug-action"><dt>Local cache</dt><dd><button type="button" onclick={clearProjectionCache}>Clear map projection cache</button>{#if cacheClearStatus}<small role="status">{cacheClearStatus}</small>{/if}</dd></div>
          {/if}
        </dl>
        {#if mode === "real-preview" && usingMvt}
          <fieldset class="cluster-settings">
            <legend>Clustering</legend>
            <label for="cluster-max-zoom">Cluster cutoff <output>at zoom {clusterMaxZoom.toFixed(1)}</output></label>
            <input id="cluster-max-zoom" type="range" min="4" max="14" step="0.5" value={clusterMaxZoom}
              oninput={(event) => { clusterMaxZoom = Number(event.currentTarget.value); scheduleClusterSettings(); }} />
            <small>The cached MVT hierarchy changes at this camera zoom; fractional cutoffs use rounded tile selection.</small>
            {#if clusterSettingsError}<small role="alert">{clusterSettingsError}</small>{/if}
          </fieldset>
          <fieldset class="cluster-settings">
            <legend>Map visualization</legend>
            <label for="reference-radius">Approx radius <output>{referenceRadiusKm.toFixed(2)} km</output></label>
            <input id="reference-radius" type="range" min="0.25" max="5" step="0.25" value={referenceRadiusKm}
              oninput={(event) => { referenceRadiusKm = Number(event.currentTarget.value); updateVisualSettings(); }} />
            <label for="reference-opacity">Approx opacity <output>{Math.round(referenceOpacity * 100)}%</output></label>
            <input id="reference-opacity" type="range" min="0.02" max="0.35" step="0.01" value={referenceOpacity}
              oninput={(event) => { referenceOpacity = Number(event.currentTarget.value); updateVisualSettings(); }} />
            <label for="coordinate-radius">Coordinate size <output>{coordinateRadius} px</output></label>
            <input id="coordinate-radius" type="range" min="3" max="12" step="0.5" value={coordinateRadius}
              oninput={(event) => { coordinateRadius = Number(event.currentTarget.value); updateVisualSettings(); }} />
            <label class="cluster-checkbox" for="reference-labels"><input id="reference-labels" type="checkbox" checked={showReferenceLabels}
              onchange={(event) => { showReferenceLabels = event.currentTarget.checked; updateVisualSettings(); }} /> Show Approx labels</label>
            <label class="cluster-checkbox" for="v1-pin-mode"><input id="v1-pin-mode" type="checkbox" checked={useV1Pins}
              onchange={(event) => { useV1Pins = event.currentTarget.checked; void updatePinMode(); }} /> Use V1 facility pin PNG + shadow</label>
            {#if pinModeError}<small role="alert">{pinModeError}</small>{/if}
            <small>The blue area is an approximate display aid, not a measured accuracy boundary.</small>
          </fieldset>
          <fieldset class="cluster-settings">
            <legend>Interaction & performance</legend>
            <label for="cluster-zoom-duration">Cluster-click zoom <output>{clusterZoomDuration} ms</output></label>
            <input id="cluster-zoom-duration" type="range" min="0" max="700" step="20" value={clusterZoomDuration}
              oninput={(event) => clusterZoomDuration = Number(event.currentTarget.value)} />
            <small>Cluster membership and expansion levels come from the server-generated cached tile hierarchy; camera zoom remains fractional between tile levels.</small>
          </fieldset>
        {/if}
        {#if isNativeMap() && !usingMvt}
          <fieldset class="cluster-settings">
            <legend>Clustering</legend>
            <label class="cluster-checkbox" for="cluster-enabled"><input id="cluster-enabled" type="checkbox" checked={clusterEnabled}
              onchange={(event) => { clusterEnabled = event.currentTarget.checked; scheduleClusterSettings(); }} /> Enable clustering</label>
            <label for="cluster-radius">Cluster radius <output>{clusterRadius} px</output></label>
            <input id="cluster-radius" type="range" min="15" max="100" step="5" value={clusterRadius}
              oninput={(event) => { clusterRadius = Number(event.currentTarget.value); scheduleClusterSettings(); }} />
            <label for="cluster-max-zoom">Cluster cutoff <output>at zoom {useRoundedClusterTiles(clusterMaxZoom) && !roundedClusterTilesAvailable ? (nativeClusterMaxZoom(clusterMaxZoom) + 1).toFixed(1) : clusterMaxZoom.toFixed(1)}</output></label>
            <input id="cluster-max-zoom" type="range" min="4" max="14" step="0.5" value={clusterMaxZoom}
              oninput={(event) => { clusterMaxZoom = Number(event.currentTarget.value); scheduleClusterSettings(); }} />
            <small>Coordinate records separate at the selected camera zoom; city and area references remain aggregates. Half-zoom cutoffs use MapLibre’s rounded GeoJSON tile selection.</small>
            {#if !clusterEnabled}<small>All map units are visible. World-scale rendering may be slow.</small>{/if}
            {#if clusterSettingsError}<small role="alert">{clusterSettingsError}</small>{/if}
          </fieldset>
          <fieldset class="cluster-settings">
            <legend>Map visualization</legend>
            <label for="reference-radius">Approx radius <output>{referenceRadiusKm.toFixed(2)} km</output></label>
            <input id="reference-radius" type="range" min="0.25" max="5" step="0.25" value={referenceRadiusKm}
              oninput={(event) => { referenceRadiusKm = Number(event.currentTarget.value); updateVisualSettings(); }} />
            <label for="reference-opacity">Approx opacity <output>{Math.round(referenceOpacity * 100)}%</output></label>
            <input id="reference-opacity" type="range" min="0.02" max="0.35" step="0.01" value={referenceOpacity}
              oninput={(event) => { referenceOpacity = Number(event.currentTarget.value); updateVisualSettings(); }} />
            <label for="coordinate-radius">Coordinate size <output>{coordinateRadius} px</output></label>
            <input id="coordinate-radius" type="range" min="3" max="12" step="0.5" value={coordinateRadius}
              oninput={(event) => { coordinateRadius = Number(event.currentTarget.value); updateVisualSettings(); }} />
            <label class="cluster-checkbox" for="reference-labels"><input id="reference-labels" type="checkbox" checked={showReferenceLabels}
              onchange={(event) => { showReferenceLabels = event.currentTarget.checked; updateVisualSettings(); }} /> Show Approx labels</label>
            <label class="cluster-checkbox" for="v1-pin-mode"><input id="v1-pin-mode" type="checkbox" checked={useV1Pins}
              onchange={(event) => { useV1Pins = event.currentTarget.checked; void updatePinMode(); }} /> Use V1 facility pin PNG + shadow</label>
            {#if pinModeError}<small role="alert">{pinModeError}</small>{/if}
            <small>The blue radius is a display aid, not a measured accuracy boundary.</small>
          </fieldset>
          <fieldset class="cluster-settings">
            <legend>Interaction & performance</legend>
            <label for="cluster-zoom-duration">Cluster-click zoom <output>{clusterZoomDuration} ms</output></label>
            <input id="cluster-zoom-duration" type="range" min="0" max="700" step="20" value={clusterZoomDuration}
              oninput={(event) => clusterZoomDuration = Number(event.currentTarget.value)} />
            <label for="cluster-rebuild-debounce">Slider rebuild delay <output>{clusterRebuildDebounce} ms</output></label>
            <input id="cluster-rebuild-debounce" type="range" min="0" max="500" step="25" value={clusterRebuildDebounce}
              oninput={(event) => clusterRebuildDebounce = Number(event.currentTarget.value)} />
            <small>These affect cluster clicks and debug edits only; they do not speed up ordinary pan or zoom.</small>
          </fieldset>
        {/if}
      </aside>{/if}{/if}{#if false && mode === "real-preview" && !usingMvt && hasMapFeatures}<button
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
  {#if SHOW_PRECISION_LEGEND}<PrecisionLegend {mode} />{/if}
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
    right: auto;
    bottom: 0.65rem;
    left: 1rem;
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
  .accessible-map-features header,
  .map-diagnostics header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .accessible-map-features header button,
  .map-diagnostics header button {
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
  .map-diagnostics {
    position: absolute;
    z-index: 6;
    bottom: 3.2rem;
    left: 0.5rem;
    width: min(23rem, calc(100vw - 1rem));
    max-height: min(72vh, 42rem);
    overflow: auto;
    padding: 0.6rem;
    border: 1px solid #69716a;
    background: #171a18f2;
    color: #f1efe8;
    font: 0.64rem system-ui;
  }
  .map-diagnostics dl {
    display: grid;
    gap: 0.3rem;
    margin: 0.55rem 0 0;
  }
  .map-diagnostics dl div {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    padding-top: 0.3rem;
    border-top: 1px solid #343a36;
  }
  .map-diagnostics dt {
    color: #aab0aa;
  }
  .map-diagnostics dd {
    margin: 0;
    text-align: right;
  }
  .cluster-settings {
    display: grid;
    gap: 0.4rem;
    margin: 0.7rem 0 0;
    padding: 0.6rem 0 0;
    border: 0;
    border-top: 1px solid #343a36;
  }
  .cluster-settings legend {
    padding: 0;
    color: #f1efe8;
    font-weight: 600;
  }
  .cluster-settings label {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .cluster-settings output,
  .cluster-settings small {
    color: #aab0aa;
  }
  .cluster-settings input {
    width: 100%;
    accent-color: #d68b53;
  }
  .cluster-settings .cluster-checkbox {
    justify-content: flex-start;
    align-items: center;
  }
  .cluster-settings .cluster-checkbox input {
    width: auto;
    margin: 0;
  }
  .approximation-cue {
    position: absolute;
    z-index: 3;
    top: 0.75rem;
    right: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.38rem;
    padding: 0.3rem 0.45rem;
    border: 1px solid #53656c;
    background: #171a18e8;
    color: #c4dbe4;
    font: 0.59rem system-ui;
    letter-spacing: 0.02em;
    pointer-events: none;
  }
  .approximation-cue i {
    width: 0.55rem;
    height: 0.55rem;
    border: 1px solid #79b9da;
    border-radius: 50%;
    background: #79b9da14;
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
    .approximation-cue { top: 4rem; right: 0.65rem; max-width: 9.8rem; }
    .map-surface :global(.precision-legend) { bottom: 9.4rem; width: auto; max-width: min(15rem, calc(100vw - 1.3rem)); }
    .map-surface :global(.precision-legend.expanded) { top: 3.5rem; bottom: auto; width: min(15rem, calc(100vw - 1.3rem)); }
    .map-surface :global(.maplibregl-ctrl-bottom-right) { right: 0.4rem; bottom: 2.9rem; left: 0.4rem; }
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
    .map-diagnostics {
      top: auto;
      right: 0.5rem;
      bottom: 8.4rem;
      left: 0.5rem;
      width: auto;
      max-height: 58vh;
      overflow: auto;
      padding: 0.85rem;
      font-size: 0.78rem;
    }
    .map-diagnostics header strong {
      font-size: 0.85rem;
    }
    .map-diagnostics dl {
      gap: 0.5rem;
    }
    .map-diagnostics dl div {
      padding-top: 0.45rem;
    }
    .map-diagnostics dd {
      max-width: 58%;
      overflow-wrap: anywhere;
    }
    .map-surface.diagnostics-active :global(.precision-legend) {
      display: none;
    }
    .map-surface.diagnostics-active .feature-list-toggle {
      display: none;
    }
  }
</style>
