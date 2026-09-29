<script lang="ts">
  import { onMount } from 'svelte';
  import * as maplibregl from 'maplibre-gl';
  import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import { ReleaseMapManifestRepository, type ReleaseMapManifest } from '../api/ReleaseMapManifestRepository';
  import { createBaseStyle } from '../design-lab/components/mapSurfaceLayers';
  import { addReleaseMapLayers, removeReleaseMapLayers } from '../design-lab/components/releaseMapLayers';

  let container: HTMLDivElement;
  let map: maplibregl.Map | null = null;
  let activeNamespace: string | null = null;
  let activeManifest: ReleaseMapManifest | null = null;
  let status = 'Checking the current map release…';
  let error = '';
  let disposed = false;
  let requestEpoch = 0;
  let requestController: AbortController | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  const manifestRepository = new ReleaseMapManifestRepository();

  // A prior source must never remain visible when the release gate cannot be
  // revalidated. The browser may retain immutable tiles, but not display them.
  function clearRelease(): void {
    if (map && activeNamespace) removeReleaseMapLayers(map, activeNamespace);
    activeNamespace = null;
    activeManifest = null;
  }

  function installRelease(manifest: ReleaseMapManifest): void {
    if (!map) return;
    const namespace = `release-${manifest.releaseId.replace(/[^a-zA-Z0-9_-]/g, '-')}-${String(manifest.suppressionGeneration).replace(/[^a-zA-Z0-9_-]/g, '-')}`;
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
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
    map.on('load', () => { void revalidate(); });
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
      document.removeEventListener('visibilitychange', onVisible);
      if (timer) clearInterval(timer);
      map?.remove();
      map = null;
    };
  });
</script>

<section class="release-map" aria-label="Map of public facilities">
  <div class="map" class:gated={!activeManifest} bind:this={container}></div>
  {#if status}<p class="map-state" role="status">{status}</p>{/if}
  {#if error}<div class="map-state" role="alert"><p>{error}</p><button type="button" onclick={() => void revalidate()}>Retry</button></div>{/if}
</section>

<style>
  .release-map { position: relative; min-height: calc(100dvh - 5rem); background: #dce5e0; }
  .map { position: absolute; inset: 0; }
  .map.gated { visibility: hidden; }
  .map-state { position: absolute; top: 1rem; left: 50%; transform: translateX(-50%); max-width: min(90vw, 28rem); margin: 0; padding: .8rem 1rem; background: #171a18; color: #f1efe8; text-align: center; font: .85rem system-ui, sans-serif; box-shadow: 0 4px 18px #0003; }
  .map-state p { margin: 0 0 .5rem; }
  .map-state button { border: 1px solid #aaa; background: transparent; color: inherit; padding: .35rem .75rem; cursor: pointer; }
</style>
