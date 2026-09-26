<script lang="ts">
  /**
   * MapSurface is the composition boundary:
   * - mapSurfaceLayers owns the base style, server tile URL, and layer contracts;
   * - mvtLineage owns pure parent/child transaction decisions;
   * - this component owns Svelte state, MapLibre event wiring, and the canvas DOM.
   *
   * JSON clustering remains a supported fixture/fallback path. The real preview
   * uses the server-owned MVT hierarchy, whose continuity and lineage state must
   * be invalidated whenever source filtering or a basemap style changes.
   */
  import { onMount } from "svelte";
  import * as maplibregl from "maplibre-gl";
  import mapLibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
  import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
  import "maplibre-gl/dist/maplibre-gl.css";
  import type {
    LabRecord,
    LabState,
    MapDiagnostics,
    MapTiming,
    Viewport,
    ViewportBounds,
  } from "../contract";
  import PrecisionLegend from "./PrecisionLegend.svelte";
  import { MvtMotionController } from "./mvtMotionController";
  import { JsonClusterMotionController } from "./jsonClusterMotionController";
  import {
    addJsonLocationLayers,
    createJsonMapCollection,
    loadJsonFallbackImages,
    setJsonFallbackData,
  } from "./jsonMapFallback";
  import {
    addMvtLocationLayers,
    createBaseStyle,
    removeLocationLayers,
  } from "./mapSurfaceLayers";

  let {
    records,
    state: mapState,
    mode = "synthetic",
    mapStatus = "idle",
    mapError = "",
    mapTruncated = false,
    mapDiagnostics,
    useMvtMap = false,
    referenceLoading = false,
    onmaptiming,
    onselect,
    onaggregate,
    onreference,
    onbasemap,
    onviewport,
    onbounds,
  }: {
    records: readonly LabRecord[];
    state: LabState;
    mode?: "synthetic" | "real-preview";
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
    useMvtMap?: boolean;
    referenceLoading?: boolean;
    onmaptiming?(timing: MapTiming): void;
    onselect(id: string): void;
    onaggregate(memberIds: readonly string[]): void;
    onreference?(key: string): void;
    onbasemap(value: "vector" | "satellite"): void;
    onviewport(value: Viewport): void;
    onbounds?(bounds: ViewportBounds): void;
  } = $props();
  let host: HTMLDivElement;
  let map: MapLibreMap | undefined;
  let appliedBasemap: "vector" | "satellite" | undefined;
  let syncing = false;
  let interactionsBound = false;
  let mvtError = $state("");
  let pendingReference = $state<
    | Readonly<{ key: string; count: number; observedLoading: boolean }>
    | undefined
  >();
  let boundsTimer: ReturnType<typeof setTimeout> | undefined;
  let zoomStartedAt: number | null = null;
  let zoomSettleMs: number | null = null;
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
  const diagnosticsEnabled = $derived(
    import.meta.env.DEV && mode === "real-preview",
  );
  const usingMvt = $derived(mode === "real-preview" && useMvtMap);
  const hitRate = $derived.by(() => {
    const total =
      (mapDiagnostics?.cacheHits ?? 0) + (mapDiagnostics?.cacheMisses ?? 0);
    return total ? Math.round((mapDiagnostics!.cacheHits / total) * 100) : 0;
  });
  maplibregl.setWorkerUrl(mapLibreWorkerUrl);

  function style(): any {
    return createBaseStyle(mapState.basemap);
  }
  /**
   * Street/satellite is a raster swap, not a new map style. Keeping the style
   * avoids tearing down the MVT source and every location layer just to change
   * the backdrop beneath them.
   */
  function applyBasemapTiles(basemap: "vector" | "satellite") {
    if (!map) return;
    const nextStyle = createBaseStyle(basemap) as any;
    const baseTiles = nextStyle.sources?.base?.tiles;
    const base = map.getSource("base") as any;
    if (Array.isArray(baseTiles) && typeof base?.setTiles === "function")
      base.setTiles(baseTiles);

    if (!map.getLayer("transport")) {
      map.addLayer({
        id: "transport",
        type: "raster",
        source: "transport",
        paint: { "raster-opacity": 0 },
      } as any);
    }
    map.setPaintProperty(
      "transport",
      "raster-opacity",
      basemap === "satellite" ? 0.72 : 0,
    );
  }
  function setData() {
    if (usingMvt) return;
    jsonMotionController?.cancel();
    const source = map?.getSource("locations") as GeoJSONSource | undefined;
    if (!source || !map) return;
    const startedAt = performance.now();
    const data = createJsonMapCollection(mapped, mode);
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
    if (!map.hasImage("cluster-low"))
      map.addImage("cluster-low", clusterImage("#b5e28c99", "#6ecc39b8"));
    if (!map.hasImage("cluster-mid"))
      map.addImage("cluster-mid", clusterImage("#f1d35799", "#f0c20cb8"));
    if (!map.hasImage("cluster-high"))
      map.addImage("cluster-high", clusterImage("#fd9c7399", "#f18017b8"));
  }
  async function addLayers() {
    if (!map || map.getSource("locations")) return;
    loadClusterImages();
    await loadJsonFallbackImages(
      map,
      `${import.meta.env.BASE_URL}v1-pins/`,
    );
    addJsonLocationLayers(map, createJsonMapCollection(mapped, mode));
  }
  function addMvtLayers() {
    if (!map) return;
    addMvtLocationLayers(map, mapState.sourceId ?? undefined);
  }

  function replaceMapProjection() {
    if (!map || !map.isStyleLoaded()) return;
    if (usingMvt) {
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
    if (mvtSourceReady && mvtSourceReadyMs === null)
      mvtSourceReadyMs = Math.round(performance.now() - mvtInitialStartedAt);
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
      else jsonMotionController.attach(host.parentElement);
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
      jsonMotionController?.onZoomStart(event);
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
          duration: 460,
          easing: (t) => 1 - Math.pow(1 - t, 3),
          essential: false,
        });
      });
      map.on("click", "mvt-source-coordinates", (event: any) => {
        const key = event.features?.[0]?.properties?.feature_key;
        if (typeof key === "string" && /^[0-9a-f-]{36}$/i.test(key))
          onselect(key);
      });
      map.on("click", "mvt-reference-outer", (event: any) => {
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
        "mvt-reference-outer",
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
      const feature = event.features?.[0],
        clusterId = feature?.properties?.cluster_id;
      if (typeof clusterId !== "number") return;
      jsonMotionController?.playExpansion(feature, clusterId);
      (map?.getSource("locations") as GeoJSONSource | undefined)
        ?.getClusterExpansionZoom(clusterId)
        .then((zoom) => {
          if (!map) return;
          jsonMotionController?.armExpansion(map);
          map.easeTo({
            center: feature.geometry.coordinates,
            zoom,
            duration: 460,
            easing: (t) => 1 - Math.pow(1 - t, 3),
            essential: false,
          });
        });
    });
    for (const layer of [
      "exact-pins",
      "approximate-points",
      "source-coordinate-points",
    ])
      map.on("click", layer, (event: any) => {
        const id = event.features?.[0]?.properties?.id;
        if (typeof id === "string") onselect(id);
      });
    map.on("click", "aggregate-outer", (event: any) => {
      try {
        const ids = JSON.parse(
          event.features?.[0]?.properties?.memberIds ?? "[]",
        );
        if (Array.isArray(ids))
          onaggregate(ids.filter((id): id is string => typeof id === "string"));
      } catch {
        /* fixture metadata is validated before use */
      }
    });
    for (const layer of [
      "clusters",
      "exact-pins",
      "approximate-points",
      "source-coordinate-points",
      "aggregate-outer",
    ]) {
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
      // Cluster continuity owns replacement visibility. Native tile fading
      // would make an otherwise atomic replacement look like a pop-in.
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
    instance.addControl(
      new maplibregl.NavigationControl({ showZoom: true, showCompass: true }),
      "top-left",
    );
    instance.on("style.load", () => {
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
      if (!usingMvt) {
        jsonMotionController?.cancel();
      }
    });
    instance.on("sourcedata", (event: any) => {
      if (usingMvt && event?.sourceId === "preview-mvt") {
        markMvtSourceReady(instance);
        mvtMotionController?.playExpansion();
        mvtMotionController?.playJoin();
      }
    });
    instance.on("idle", () => {
      if (usingMvt) {
        updateMvtDiagnostics(instance);
        mvtMotionController?.playExpansion();
        mvtMotionController?.playJoin();
      }
    });
    instance.on("moveend", () => {
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
      if (boundsTimer) clearTimeout(boundsTimer);
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
      appliedBasemap = basemap;
      applyBasemapTiles(basemap);
    }
  });
  $effect(() => {
    records;
    if (map?.isStyleLoaded() && !usingMvt) setData();
  });
  $effect(() => {
    const source = mapState.sourceId;
    if (usingMvt && map?.isStyleLoaded()) {
      source;
      replaceMapProjection();
    }
  });
  $effect(() => {
    const viewport = mapState.viewport;
    if (!map) return;
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
  });
  // Pre-effect runs before the style effect below, so a basemap swap cannot retain
  // a transient cluster frame from the previous style generation.
  $effect.pre(() => {
    mapState.basemap;
    jsonMotionController?.cancel();
    mvtMotionController?.cancel();
    mvtMotionController?.clearLineage();
  });
</script>

<svelte:window
  onkeydown={(event) => {
    if (event.key === "Escape") diagnosticsOpen = false;
  }}
/>
{#if usingMvt && mvtError}<small class="map-status mvt-status" role="alert"
    >{mvtError}</small
  >{/if}
<section
  class:diagnostics-active={diagnosticsOpen}
  class="map-surface"
  aria-label="Map showing records"
>
  <div class="map-host" bind:this={host}></div>
  <small class="review-disclosure"
    >{mode === "real-preview"
      ? "Private real V2 preview · not approved or published"
      : "Synthetic development data"}</small
  >{#if pendingReference}<small
      class="map-status reference-status"
      role="status"
      >Loading {pendingReference.count || "represented"} reference records…</small
    >{:else if mode === "real-preview" && mapStatus === "loading" && !usingMvt}<small
      class="map-status"
      role="status">Loading map records…</small
    >{:else if mode === "real-preview" && (mapStatus === "error" || mapStatus === "unauthorized")}<small
      class="map-status"
      role="alert">{mapError}</small
    >{:else if mode === "real-preview" && mapTruncated && !usingMvt}<small
      class="map-status"
      role="status"
      >Map page limit reached; zoom in to load a smaller area.</small
    >{/if}{#if diagnosticsEnabled && mapDiagnostics}<button
      class="diagnostics-toggle"
      type="button"
      aria-expanded={diagnosticsOpen}
      aria-controls="map-diagnostics"
      onclick={() => (diagnosticsOpen = !diagnosticsOpen)}
      >Map diagnostics</button
    >{#if diagnosticsOpen}<aside
        id="map-diagnostics"
        class="map-diagnostics"
        aria-label="Map diagnostics"
      >
        <header>
          <strong>Map diagnostics</strong><button
            type="button"
            aria-label="Close map diagnostics"
            onclick={() => (diagnosticsOpen = false)}>×</button
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
                {mvtCameraSettleMs === null ? "—" : `${mvtCameraSettleMs} ms`}
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
            <div>
              <dt>Zoom / tiles</dt>
              <dd>
                {mapDiagnostics.zoom.toFixed(1)} · {mapDiagnostics.readyTiles}/{mapDiagnostics.currentTiles}
              </dd>
            </div>
            <div>
              <dt>Zoom settle</dt>
              <dd>
                {mapDiagnostics.zoomSettleMs === null
                  ? "—"
                  : `${mapDiagnostics.zoomSettleMs} ms`}
              </dd>
            </div>
            <div>
              <dt>Cache</dt>
              <dd>
                {`${mapDiagnostics.cacheEntries}/${mapDiagnostics.cacheCapacity} · ${mapDiagnostics.cacheHits} hit / ${mapDiagnostics.cacheMisses} miss · ${hitRate}%`}
              </dd>
            </div>
            <div>
              <dt>Network / source</dt>
              <dd>
                {mapDiagnostics.lastFetchMs === null
                  ? "—"
                  : `${mapDiagnostics.lastFetchMs} ms`} · {mapDiagnostics.sourceMaterializeMs === null
                  ? "—"
                  : `${mapDiagnostics.sourceMaterializeMs} ms`}
              </dd>
            </div>
            <div>
              <dt>Cluster ready</dt>
              <dd>
                {mapDiagnostics.clusterReadyMs === null
                  ? "waiting"
                  : `${mapDiagnostics.clusterReadyMs} ms`}
              </dd>
            </div>
            <div>
              <dt>Rendered</dt>
              <dd>{`${mapDiagnostics.renderedRecords} records`}</dd>
            </div>
            <div>
              <dt>Source / coverage</dt>
              <dd>
                {mapDiagnostics.sourceId ?? "all"} · {mapDiagnostics.truncated
                  ? "bounded"
                  : "complete"}
              </dd>
            </div>
          {/if}
        </dl>
      </aside>{/if}{/if}{#if mode === "real-preview" && !usingMvt && hasMapFeatures}<button
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
  <div class="basemap-control" role="group" aria-label="Basemap">
    <button
      type="button"
      aria-pressed={mapState.basemap === "vector"}
      onclick={() => onbasemap("vector")}>Street</button
    ><button
      type="button"
      aria-pressed={mapState.basemap === "satellite"}
      onclick={() => onbasemap("satellite")}>Satellite</button
    >
  </div>
  <PrecisionLegend {mode} />
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
    bottom: 2rem;
    min-height: 2rem;
    padding: 0.3rem 0.5rem;
    border: 1px solid #69716a;
    color: #f1efe8;
    background: #171a18e8;
    font: 0.65rem system-ui;
    cursor: pointer;
  }
  .diagnostics-toggle {
    top: 3.6rem;
    right: 0.5rem;
    bottom: auto;
  }
  .feature-list-toggle span {
    margin-left: 0.3rem;
    color: #c6cbc4;
  }
  .accessible-map-features {
    position: absolute;
    z-index: 6;
    right: 0.5rem;
    bottom: 2rem;
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
    top: 3.6rem;
    right: 0.5rem;
    width: min(23rem, calc(100vw - 1rem));
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
  .basemap-control {
    position: absolute;
    z-index: 2;
    top: 1rem;
    right: 1rem;
    display: flex;
  }
  .basemap-control button {
    min-height: 2rem;
    padding: 0.3rem 0.5rem;
    border: 1px solid #69716a;
    color: #f1efe8;
    background: #171a18;
    font: 0.65rem system-ui;
    cursor: pointer;
  }
  .basemap-control button + button {
    border-left: 0;
  }
  .basemap-control button[aria-pressed="true"] {
    color: #171a18;
    background: #e8ebe4;
  }
  .review-disclosure {
    position: absolute;
    z-index: 2;
    right: 0.5rem;
    bottom: 0.35rem;
    color: #4a504a;
    background: #f1efe8cc;
    padding: 0.08rem 0.25rem;
    font: 0.52rem system-ui;
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
  @media (max-width: 40rem) {
    .basemap-control {
      top: 0.65rem;
      right: 0.65rem;
    }
    .map-status {
      top: 3.2rem;
    }
    .feature-list-toggle {
      bottom: 2.4rem;
    }
    .diagnostics-toggle {
      top: 3.2rem;
      right: 0.65rem;
      bottom: auto;
    }
    .map-diagnostics {
      top: auto;
      right: 0.5rem;
      bottom: 0.5rem;
      left: 0.5rem;
      width: auto;
      max-height: 48vh;
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
