<script lang="ts">
  import { onMount } from 'svelte';
  import * as maplibregl from 'maplibre-gl';
  import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import { ReleaseMapManifestRepository, type ReleaseMapManifest } from '../api/ReleaseMapManifestRepository';
  import { LocalLocationRepository } from '../api/LocalLocationRepository';
  import type { Location } from '../domain/location';
  import { createBaseStyle } from '../design-lab/components/mapSurfaceLayers';
  import { addReleaseMapLayers, removeReleaseMapLayers } from '../design-lab/components/releaseMapLayers';

  let container: HTMLDivElement;
  let map: maplibregl.Map | null = null;
  let activeNamespace: string | null = null;
  let activeManifest = $state<ReleaseMapManifest | null>(null);
  let status = $state('Checking the current map release…');
  let error = $state('');
  let disposed = false;
  let requestEpoch = 0;
  let requestController: AbortController | null = null;
  let listController: AbortController | null = null;
  let detailController: AbortController | null = null;
  let searchQuery = $state('');
  let searchResults = $state<readonly Location[]>([]);
  let searchStatus = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
  let selectedLocation = $state<Location | null>(null);
  let detailStatus = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
  let detailMessage = $state('');
  let timer: ReturnType<typeof setInterval> | null = null;
  const manifestRepository = new ReleaseMapManifestRepository();
  const locationRepository = new LocalLocationRepository();
  let activeInteractionCleanup: (() => void) | null = null;

  function clearSelection(): void {
    listController?.abort();
    detailController?.abort();
    searchResults = [];
    searchStatus = 'idle';
    selectedLocation = null;
    detailStatus = 'idle';
    detailMessage = '';
  }

  async function searchLocations(event?: SubmitEvent): Promise<void> {
    event?.preventDefault();
    const manifest = activeManifest;
    if (!manifest) return;
    listController?.abort();
    const controller = new AbortController();
    listController = controller;
    searchResults = [];
    searchStatus = 'loading';
    try {
      const result = await locationRepository.list('official', { q: searchQuery.trim(), limit: 50 }, controller.signal, manifest.releaseId);
      if (controller.signal.aborted || activeManifest?.releaseId !== manifest.releaseId || activeManifest?.profile !== manifest.profile) return;
      searchResults = result.locations;
      searchStatus = 'ready';
    } catch {
      if (controller.signal.aborted) return;
      searchResults = [];
      searchStatus = 'error';
    }
  }

  async function openLocation(id: string): Promise<void> {
    const manifest = activeManifest;
    if (!manifest || !/^[a-f0-9-]{36}$/i.test(id)) return;
    detailController?.abort();
    const controller = new AbortController();
    detailController = controller;
    selectedLocation = null;
    detailMessage = '';
    detailStatus = 'loading';
    try {
      const result = await locationRepository.detail(id, 'official', controller.signal, manifest.releaseId);
      if (controller.signal.aborted || activeManifest?.releaseId !== manifest.releaseId || result.releaseId !== manifest.releaseId) return;
      selectedLocation = result.location;
      detailStatus = 'ready';
    } catch {
      if (controller.signal.aborted) return;
      selectedLocation = null;
      detailMessage = 'This record is unavailable in the current release.';
      detailStatus = 'error';
    }
  }

  // A prior source must never remain visible when the release gate cannot be
  // revalidated. The browser may retain immutable tiles, but not display them.
  function clearRelease(): void {
    activeInteractionCleanup?.();
    activeInteractionCleanup = null;
    if (map && activeNamespace) removeReleaseMapLayers(map, activeNamespace);
    activeNamespace = null;
    activeManifest = null;
    clearSelection();
  }

  function installRelease(manifest: ReleaseMapManifest): void {
    if (!map) return;
    const namespace = `${manifest.releaseId.replace(/[^a-zA-Z0-9_-]/g, '-')}-${String(manifest.suppressionGeneration).replace(/[^a-zA-Z0-9_-]/g, '-')}`;
    const unchanged = activeManifest?.releaseId === manifest.releaseId
      && activeManifest?.suppressionGeneration === manifest.suppressionGeneration
      && activeManifest?.tileUrlTemplate === manifest.tileUrlTemplate;
    if (unchanged) return;

    // Switching is deliberately fail-closed. We do not mix old and new release
    // features while MapLibre requests the next immutable tile set.
    clearRelease();
    addReleaseMapLayers(map, namespace, {
      tileTemplate: manifest.tileUrlTemplate,
      minZoom: manifest.minZoom,
      maxZoom: manifest.maxZoom,
    });
    activeNamespace = namespace;
    activeManifest = manifest;
    const clusterLayer = `release-${namespace}-cluster-circle`;
    const exactLayer = `release-${namespace}-exact-pin`;
    const onClusterClick = (event: maplibregl.MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      const rawCoordinates = feature?.geometry;
      const nextZoom = Number(feature?.properties?.next_zoom);
      if (!feature || feature.properties?.kind !== 'cluster' || !Number.isFinite(nextZoom)
        || !rawCoordinates || rawCoordinates.type !== 'Point') return;
      const coordinates = rawCoordinates.coordinates as [number, number];
      if (!coordinates.every(Number.isFinite)) return;
      map?.easeTo({
        center: coordinates,
        zoom: Math.max((map?.getZoom() ?? 0) + 1, Math.min(manifest.maxZoom, nextZoom)),
        duration: 460,
        easing: (t) => 1 - Math.pow(1 - t, 3),
        essential: false,
      });
    };
    const onExactClick = (event: maplibregl.MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      const id = feature?.properties?.record_id;
      if (feature?.properties?.kind === 'exact' && typeof id === 'string') void openLocation(id);
    };
    map.on('click', clusterLayer, onClusterClick);
    map.on('click', exactLayer, onExactClick);
    for (const layer of [clusterLayer, exactLayer]) {
      map.on('mouseenter', layer, () => { if (map) map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', layer, () => { if (map) map.getCanvas().style.cursor = ''; });
    }
    activeInteractionCleanup = () => {
      map?.off('click', clusterLayer, onClusterClick);
      map?.off('click', exactLayer, onExactClick);
    };
  }

  async function revalidate(): Promise<void> {
    if (disposed) return;
    requestController?.abort();
    requestController = new AbortController();
    const epoch = ++requestEpoch;
    try {
      const manifest = await manifestRepository.load('official', requestController.signal);
      if (disposed || epoch !== requestEpoch) return;
      if (!manifest) {
        clearRelease();
        status = 'No public map release is available yet.';
        error = '';
        return;
      }
      installRelease(manifest);
      status = '';
      error = '';
    } catch {
      if (!disposed && epoch === requestEpoch) {
        clearRelease();
        status = '';
        error = 'The current map release could not be verified. Please try again.';
      }
    }
  }

  onMount(() => {
    maplibregl.setWorkerUrl(maplibreWorkerUrl);
    map = new maplibregl.Map({
      container,
      style: createBaseStyle('vector') as maplibregl.StyleSpecification,
      center: [0, 18],
      zoom: 1.5,
      attributionControl: false,
    });
    if (import.meta.env.DEV) (window as Window & { __UEC_PUBLIC_RELEASE_MAP__?: maplibregl.Map }).__UEC_PUBLIC_RELEASE_MAP__ = map;
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
    map.on('style.load', () => { void revalidate(); });
    const onVisible = () => {
      if (!document.hidden) {
        clearRelease();
        status = 'Checking the current map release…';
        void revalidate();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    timer = setInterval(() => { if (!document.hidden) void revalidate(); }, 60_000);
    return () => {
      disposed = true;
      requestController?.abort();
      listController?.abort();
      detailController?.abort();
      document.removeEventListener('visibilitychange', onVisible);
      if (timer) clearInterval(timer);
      if (import.meta.env.DEV) delete (window as Window & { __UEC_PUBLIC_RELEASE_MAP__?: maplibregl.Map }).__UEC_PUBLIC_RELEASE_MAP__;
      map?.remove();
      map = null;
    };
  });

</script>

<section class="release-map" aria-label="Map of public facilities">
  <div class="map" class:gated={!activeManifest} bind:this={container}></div>
  {#if status}<p class="map-state" role="status">{status}</p>{/if}
  {#if error}<div class="map-state" role="alert"><p>{error}</p><button type="button" onclick={() => void revalidate()}>Retry</button></div>{/if}
  {#if activeManifest}
    <aside class="map-panel" aria-label="Search this release">
      <form onsubmit={searchLocations}>
        <label for="release-map-search">Search public locations</label>
        <div class="search-row"><input id="release-map-search" bind:value={searchQuery} autocomplete="off" /><button type="submit">Search</button></div>
      </form>
      {#if searchStatus === 'loading'}<p role="status">Searching this release…</p>
      {:else if searchStatus === 'error'}<p role="alert">Search is unavailable for this release.</p>
      {:else if searchStatus === 'ready'}
        <p class="result-context">Official profile · release {activeManifest.releaseId}</p>
        {#if searchResults.length === 0}<p>No matching public locations were found.</p>
        {:else}<ul>{#each searchResults as location (location.id)}<li><button class="result" type="button" onclick={() => void openLocation(location.id)}><span>{location.name}</span><small>{location.category} · {location.region}</small></button></li>{/each}</ul>{/if}
      {/if}
      {#if detailStatus === 'loading'}<p role="status">Loading release record…</p>
      {:else if detailStatus === 'error'}<p role="alert">{detailMessage}</p>
      {:else if selectedLocation}
        <article class="location-detail" aria-label="Public location detail">
          <h2>{selectedLocation.name}</h2>
          <p>{selectedLocation.category} · {selectedLocation.region}</p>
          <p>{selectedLocation.evidence?.displayPrecision === 'city' ? 'Approximate city-level location; this is not a facility point.' : selectedLocation.evidence?.displayPrecision === 'exact' ? 'Exact location shown from an approved source coordinate.' : 'No eligible map position.'}</p>
          {#if selectedLocation.evidence?.sourceUrl}<a href={selectedLocation.evidence.sourceUrl} target="_blank" rel="noreferrer">View source</a>{/if}
          <small>Official profile · release {activeManifest.releaseId}</small>
        </article>
      {/if}
    </aside>
  {/if}
</section>

<style>
  .release-map { position: relative; min-height: calc(100dvh - 5rem); background: #dce5e0; }
  .map { position: absolute; inset: 0; }
  .map.gated { visibility: hidden; }
  .map-state { position: absolute; top: 1rem; left: 50%; transform: translateX(-50%); max-width: min(90vw, 28rem); margin: 0; padding: .8rem 1rem; background: #171a18; color: #f1efe8; text-align: center; font: .85rem system-ui, sans-serif; box-shadow: 0 4px 18px #0003; }
  .map-state p { margin: 0 0 .5rem; }
  .map-state button { border: 1px solid #aaa; background: transparent; color: inherit; padding: .35rem .75rem; cursor: pointer; }
  .map-panel { position: absolute; z-index: 2; top: 1rem; right: 1rem; width: min(22rem, calc(100vw - 2rem)); max-height: calc(100% - 2rem); overflow: auto; padding: 1rem; box-sizing: border-box; background: #171a18; color: #f1efe8; box-shadow: 0 4px 18px #0004; font: .9rem system-ui, sans-serif; }
  .map-panel label,.map-panel h2 { display: block; margin: 0 0 .65rem; font-size: 1rem; font-weight: 600; }
  .search-row { display: flex; gap: .4rem; }
  .search-row input { min-width: 0; flex: 1; padding: .45rem; }
  .search-row button { padding: .45rem .7rem; }
  .map-panel ul { list-style: none; padding: 0; margin: .5rem 0; }
  .map-panel li + li { border-top: 1px solid #414843; }
  .result { display: grid; gap: .25rem; width: 100%; padding: .55rem 0; border: 0; text-align: left; background: transparent; color: inherit; cursor: pointer; }
  .result small,.result-context,.location-detail small { color: #bec5bb; font-size: .75rem; }
  .location-detail { margin-top: .8rem; padding-top: .8rem; border-top: 1px solid #414843; }
  .location-detail a { color: #d8c99b; }
</style>
