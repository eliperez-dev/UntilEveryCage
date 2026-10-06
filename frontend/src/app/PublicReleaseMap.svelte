<script lang="ts">
  import { onMount } from 'svelte';
  import * as maplibregl from 'maplibre-gl';
  import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import { PublicReleaseRepository, type PublicReleaseIdentity } from '../api/PublicReleaseRepository';
  import { createPublicMapFeedRepository, type PublicMapFeed } from '../api/PublicMapFeedRepository';
  import { LocalLocationRepository } from '../api/LocalLocationRepository';
  import type { Location } from '../domain/location';
  import { TAXONOMY_PRIMARY_KEYS, type TaxonomyPrimaryKey } from '../domain/taxonomy';
  import { CATEGORY_PRESENTATIONS } from '../features/locations/categoryPresentation';
  import { createBaseStyle } from '../map/baseMapStyle';
  import { addRealPreviewMapLayers, setRealPreviewMapData, setRealPreviewCategoryFilter } from '../design-lab/components/realPreviewMapLayers';

  let container: HTMLDivElement;
  let map: maplibregl.Map | null = null;
  let activeRelease: PublicReleaseIdentity | null = null;
  let selectedCategories = $state<readonly TaxonomyPrimaryKey[]>([]);
  let activeManifest = $state<PublicMapFeed['meta'] | null>(null);
  let status = $state('Checking the current map release…');
  let error = $state('');
  let disposed = false;
  let requestEpoch = 0;
  let requestController: AbortController | null = null;
  let listController: AbortController | null = null;
  let detailController: AbortController | null = null;
  let searchQuery = $state('');
  let basemap = $state<'vector' | 'muted' | 'satellite'>('vector');
  let searchResults = $state<readonly Location[]>([]);
  let searchStatus = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
  let selectedLocation = $state<Location | null>(null);
  let detailStatus = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
  let detailMessage = $state('');
  let timer: ReturnType<typeof setInterval> | null = null;
  const manifestRepository = new PublicReleaseRepository();
  const mapFeedRepository = createPublicMapFeedRepository();
  const locationRepository = new LocalLocationRepository();
  let activeInteractionCleanup: (() => void) | null = null;
  let activeCollection: PublicMapFeed['collection'] | null = null;
  const categoryGlyph = (key: TaxonomyPrimaryKey): string => ({
    animal_keeping_and_production: '●', slaughter: '◆', processing_and_preparation: '■',
    research_and_animal_use: '⬢', other_regulated_premises: '▲', unclassified: '○',
  })[key];
  const visibleSearchResults = $derived(searchResults.filter(location =>
    selectedCategories.length === 0 || selectedCategories.some(key => location.taxonomy?.primaryCategories.includes(key) ?? key === 'unclassified'),
  ));

  function toggleCategory(key: TaxonomyPrimaryKey, checked: boolean): void {
    selectedCategories = checked
      ? [...new Set([...selectedCategories, key])]
      : selectedCategories.filter(value => value !== key);
    if (map) setRealPreviewCategoryFilter(map, selectedCategories);
  }

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
    if (map?.getSource('locations')) setRealPreviewMapData(map, { type: 'FeatureCollection', features: [] });
    activeRelease = null;
    activeManifest = null;
    activeCollection = null;
    clearSelection();
  }

  function installInteractions(): void {
    if (!map) return;
    activeInteractionCleanup?.();
    const onClusterClick = (event: maplibregl.MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      if (!feature) return;
      const clusterId = feature?.properties?.cluster_id;
      if (typeof clusterId !== 'number') return;
      (map?.getSource('locations') as maplibregl.GeoJSONSource | undefined)?.getClusterExpansionZoom(clusterId).then(zoom => {
        if (map && feature.geometry.type === 'Point') map.easeTo({ center: feature.geometry.coordinates as [number, number], zoom, duration: 460, essential: false });
      });
    };
    const onRecordClick = (event: maplibregl.MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.id;
      if (typeof id === 'string') void openLocation(id);
    };
    const onEnter = () => { if (map) map.getCanvas().style.cursor = 'pointer'; };
    const onLeave = () => { if (map) map.getCanvas().style.cursor = ''; };
    map.on('click', 'clusters', onClusterClick);
    for (const layer of ['source-coordinate-points', 'approx-reference-points']) map.on('click', layer, onRecordClick);
    for (const layer of ['clusters', 'source-coordinate-points', 'approx-reference-points']) {
      if (!map.getLayer(layer)) continue;
      map.on('mouseenter', layer, onEnter);
      map.on('mouseleave', layer, onLeave);
    }
    activeInteractionCleanup = () => {
      map?.off('click', 'clusters', onClusterClick);
      for (const layer of ['source-coordinate-points', 'approx-reference-points']) map?.off('click', layer, onRecordClick);
      for (const layer of ['clusters', 'source-coordinate-points', 'approx-reference-points']) {
        map?.off('mouseenter', layer, onEnter);
        map?.off('mouseleave', layer, onLeave);
      }
      if (map) map.getCanvas().style.cursor = '';
    };
  }

  async function installRelease(release: PublicReleaseIdentity, signal: AbortSignal): Promise<void> {
    if (!map) return;
    const unchanged = activeRelease?.releaseId === release.releaseId
      && activeRelease.manifestSha256 === release.manifestSha256
      && activeRelease.suppressionGeneration === release.suppressionGeneration;
    if (unchanged) {
      if (!map.getSource('locations') && activeCollection) addRealPreviewMapLayers(map, activeCollection);
      if (activeCollection) {
        setRealPreviewCategoryFilter(map, selectedCategories);
        installInteractions();
      }
      return;
    }
    clearRelease();
    const feed = await mapFeedRepository.load('official', release.releaseId, signal);
    if (signal.aborted || !map || feed.meta.manifestSha256 !== release.manifestSha256
      || feed.meta.suppressionGeneration !== release.suppressionGeneration) throw new Error('The public map changed while it was loading.');
    activeRelease = release;
    activeManifest = feed.meta;
    activeCollection = feed.collection;
    if (map.getSource('locations')) setRealPreviewMapData(map, feed.collection);
    else addRealPreviewMapLayers(map, feed.collection);
    setRealPreviewCategoryFilter(map, selectedCategories);
    installInteractions();
  }

  async function revalidate(): Promise<void> {
    if (disposed) return;
    requestController?.abort();
    requestController = new AbortController();
    const epoch = ++requestEpoch;
    try {
      const manifest = await manifestRepository.current('official', requestController.signal);
      if (disposed || epoch !== requestEpoch) return;
      if (!manifest) {
        clearRelease();
        status = 'No public map release is available yet.';
        error = '';
        return;
      }
      await installRelease(manifest, requestController.signal);
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

  function changeBasemap(next: 'vector' | 'muted' | 'satellite'): void {
    if (!map || basemap === next) return;
    basemap = next;
    map.setStyle(createBaseStyle(next) as maplibregl.StyleSpecification);
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
        void revalidate();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    timer = setInterval(() => { if (!document.hidden) void revalidate(); }, 60_000);
    return () => {
      disposed = true;
      activeInteractionCleanup?.();
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
  <h1 class="sr-only">Map</h1>
  <div class="map" class:gated={!activeManifest} bind:this={container}></div>
  <nav class="basemap-controls" aria-label="Basemap">{#each [['vector','Map'],['muted','Muted'],['satellite','Satellite']] as [value,label]}<button type="button" aria-pressed={basemap === value} onclick={() => changeBasemap(value as 'vector' | 'muted' | 'satellite')}>{label}</button>{/each}</nav>
  {#if status}<p class="map-state" role="status">{status}</p>{/if}
  {#if error}<div class="map-state" role="alert"><p>{error}</p><button type="button" onclick={() => void revalidate()}>Retry</button></div>{/if}
  {#if activeManifest}
    <aside class="release-summary" aria-label="Public release coverage"><strong>{activeManifest.releaseLabel}</strong><span>{activeManifest.publicRecordCount.toLocaleString()} eligible records</span><span>{activeManifest.featureCount.toLocaleString()} mapped · {activeManifest.unmappedCount.toLocaleString()} unmapped</span></aside>
    <aside class="map-panel" aria-label="Search this release">
      <form onsubmit={searchLocations}>
        <label for="release-map-search">Search public locations</label>
        <div class="search-row"><input id="release-map-search" bind:value={searchQuery} autocomplete="off" /><button type="submit">Search</button></div>
      </form>
      <fieldset class="category-filters">
        <legend>Activity category</legend>
        {#each TAXONOMY_PRIMARY_KEYS as key (key)}
          <label><input type="checkbox" checked={selectedCategories.includes(key)} onchange={(event) => toggleCategory(key, event.currentTarget.checked)} /><span class="category-glyph" style={`color:${CATEGORY_PRESENTATIONS[key].color}`}>{categoryGlyph(key)}</span>{CATEGORY_PRESENTATIONS[key].label}</label>
        {/each}
        <small>Categories apply to individual record symbols. Approximate areas and clusters remain neutral location context and retain all-activity counts.</small>
      </fieldset>
      {#if searchStatus === 'loading'}<p role="status">Searching this release…</p>
      {:else if searchStatus === 'error'}<p role="alert">Search is unavailable for this release.</p>
      {:else if searchStatus === 'ready'}
        <p class="result-context">Official profile · release {activeManifest.releaseId}</p>
        {#if visibleSearchResults.length === 0}<p>No matching public locations were found.</p>
        {:else}<ul>{#each visibleSearchResults as location (location.id)}<li><button class="result" type="button" onclick={() => void openLocation(location.id)}><span>{location.name}</span><small>{location.taxonomy?.leafActivities.map(item => item.label).join(' · ') || CATEGORY_PRESENTATIONS[location.taxonomy?.displayCategory ?? 'unclassified'].label} · {location.region}</small></button></li>{/each}</ul>{/if}
      {/if}
      {#if detailStatus === 'loading'}<p role="status">Loading release record…</p>
      {:else if detailStatus === 'error'}<p role="alert">{detailMessage}</p>
      {:else if selectedLocation}
        <article class="location-detail" aria-label="Public location detail">
          <h2>{selectedLocation.name}</h2>
          <p>{CATEGORY_PRESENTATIONS[selectedLocation.taxonomy?.displayCategory ?? 'unclassified'].label} · {selectedLocation.region}</p>
          {#if selectedLocation.taxonomy?.leafActivities.length}
            <section class="taxonomy-detail" aria-label="Activities and classification provenance">
              <h3>Activities</h3>
              <ul>{#each selectedLocation.taxonomy.leafActivities as activity (activity.key)}<li>{activity.label}</li>{/each}</ul>
              {#each selectedLocation.taxonomy.assignments as assignment, index (`${assignment.primaryKey}:${assignment.leafKey ?? ''}:${index}`)}
                <p class="taxonomy-provenance">{assignment.sourceLabel ?? assignment.sourceCode ?? selectedLocation.source} · {assignment.method} · {assignment.status} · {assignment.taxonomyVersion}</p>
              {/each}
            </section>
          {/if}
          <p>{selectedLocation.evidence?.displayPrecision === 'city' ? 'Approximate city-level location; this is not a facility point.' : selectedLocation.evidence?.displayPrecision === 'source_reported' ? 'Source-reported location; the source precision is not independently established as an exact facility point.' : selectedLocation.evidence?.displayPrecision === 'approximate' ? 'Approximate location; this is not an exact facility point.' : selectedLocation.evidence?.displayPrecision === 'exact' ? 'Exact location shown from an approved source coordinate.' : 'No eligible map position.'}</p>
          {#if selectedLocation.evidence?.sourceUrl}<a href={selectedLocation.evidence.sourceUrl} target="_blank" rel="noreferrer">View source</a>{/if}
          <small>Official profile · release {activeManifest.releaseId}</small>
        </article>
      {/if}
    </aside>
  {/if}
</section>

<style>
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
  .release-map { position: relative; min-height: calc(100dvh - 5rem); background: #dce5e0; }
  .map { position: absolute; inset: 0; }
  .basemap-controls{position:absolute;z-index:2;left:1rem;bottom:1rem;display:flex;gap:.2rem;padding:.2rem;background:#171a18ef;box-shadow:0 4px 18px #0004}.basemap-controls button{min-height:2rem;padding:.35rem .55rem;border:1px solid transparent;background:transparent;color:#d4d9d0;font:.75rem system-ui;cursor:pointer}.basemap-controls button[aria-pressed=true]{border-color:#a4b5a1;color:#fff;background:#303a32}.basemap-controls button:focus-visible{outline:2px solid #eee7d6;outline-offset:2px}
  .release-summary{position:absolute;z-index:2;bottom:1rem;left:50%;display:flex;flex-wrap:wrap;justify-content:center;gap:.35rem .8rem;max-width:calc(100vw - 2rem);padding:.35rem .65rem;border:1px solid #48504b;background:#171a18ef;color:#d9ded5;font:.64rem/1.3 system-ui;transform:translateX(-50%);text-align:center}.release-summary strong{color:#f1efe8}
  .map.gated { visibility: hidden; }
  .map-state { position: absolute; top: 1rem; left: 50%; transform: translateX(-50%); max-width: min(90vw, 28rem); margin: 0; padding: .8rem 1rem; background: #171a18; color: #f1efe8; text-align: center; font: .85rem system-ui, sans-serif; box-shadow: 0 4px 18px #0003; }
  .map-state p { margin: 0 0 .5rem; }
  .map-state button { border: 1px solid #aaa; background: transparent; color: inherit; padding: .35rem .75rem; cursor: pointer; }
  .map-panel { position: absolute; z-index: 2; top: 1rem; right: 1rem; width: min(22rem, calc(100vw - 2rem)); max-height: calc(100% - 2rem); overflow: auto; padding: 1rem; box-sizing: border-box; background: #171a18; color: #f1efe8; box-shadow: 0 4px 18px #0004; font: .9rem system-ui, sans-serif; }
  .map-panel label,.map-panel h2 { display: block; margin: 0 0 .65rem; font-size: 1rem; font-weight: 600; }
  .search-row { display: flex; gap: .4rem; }
  .search-row input { min-width: 0; flex: 1; padding: .45rem; }
  .search-row button { padding: .45rem .7rem; }
  .category-filters { display: grid; gap: .35rem; margin: .8rem 0; padding: .65rem; border: 1px solid #414843; }
  .category-filters legend { padding: 0 .25rem; color: #bec5bb; }
  .category-filters label { display: flex; align-items: center; gap: .5rem; min-height: 1.6rem; cursor: pointer; }
  .category-filters input { accent-color: #d8c99b; }
  .category-glyph { display: inline-grid; place-items: center; width: 1.1rem; font-size: 1.1rem; line-height: 1; }
  .category-filters small { margin-top: .25rem; color: #bec5bb; }
  .map-panel ul { list-style: none; padding: 0; margin: .5rem 0; }
  .map-panel li + li { border-top: 1px solid #414843; }
  .result { display: grid; gap: .25rem; width: 100%; padding: .55rem 0; border: 0; text-align: left; background: transparent; color: inherit; cursor: pointer; }
  .result small,.result-context,.location-detail small { color: #bec5bb; font-size: .75rem; }
  .location-detail { margin-top: .8rem; padding-top: .8rem; border-top: 1px solid #414843; }
  .location-detail a { color: #d8c99b; }
  .taxonomy-detail { margin-top: .8rem; border-top: 1px solid #414843; padding-top: .5rem; }
  .taxonomy-detail h3 { margin: 0 0 .35rem; font-size: .85rem; }
  .taxonomy-detail ul { margin: .25rem 0; padding-left: 1.2rem; }
  .taxonomy-provenance { color: #bec5bb; font-size: .74rem; margin: .3rem 0; }
</style>
