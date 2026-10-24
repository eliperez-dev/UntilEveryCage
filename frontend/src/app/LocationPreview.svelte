<script lang="ts">
  import { onMount } from 'svelte';
  import { locationPreviewMode, locationPreviewZoom } from '../features/locations/locationPreview';
  let { latitude, longitude, precision, category }: { latitude: number; longitude: number; precision: string; category: string } = $props();
  let host = $state<HTMLDivElement>();
  let error = $state(false);
  let exact = $derived(locationPreviewMode(precision) === 'satellite');
  onMount(() => {
    let disposed = false;
  let map: any;
    void Promise.all([import('maplibre-gl'), import('../map/baseMapStyle')]).then(([lib, styles]) => {
      if (disposed) return;
      const Map = lib.Map;
      if (!host) return;
      map = new Map({ container: host, style: styles.createBaseStyle(exact ? 'satellite' : 'vector', { includeTransport: false }) as never,
        center: [longitude, latitude], zoom: locationPreviewZoom(precision), attributionControl: { compact: true }, interactive: false });
      map.on('error', () => { if (!disposed) error = true; });
      map.on('load', () => {
        if (disposed || !map) return;
        map.addSource('record-location', { type: 'geojson', data: { type: 'Feature', geometry: { type: 'Point', coordinates: [longitude, latitude] }, properties: {} } });
        const normalized = category.toLocaleLowerCase();
        const pin = normalized.includes('slaughter') ? 'red' : normalized.includes('research') ? 'violet' : normalized.includes('processing') ? 'grey' : normalized.includes('exhibitor') ? 'green' : normalized.includes('dealer') ? 'orange' : 'yellow';
        map.loadImage(`/v1-pins/marker-icon-2x-${pin}.png`, (loadError: Error | null, image?: HTMLImageElement | ImageBitmap) => {
          if (disposed || !map) return;
          if (loadError || !image) { error = true; return; }
          map.addImage('record-location-pin', image);
          map.addLayer({ id: 'record-location-pin', type: 'symbol', source: 'record-location', layout: { 'icon-image': 'record-location-pin', 'icon-anchor': 'bottom', 'icon-size': 0.45 } });
        });
      });
    }).catch(() => { if (!disposed) error = true; });
    return () => { disposed = true; map?.remove(); };
  });
</script>
<section class="location-preview" aria-label={exact ? 'Satellite location preview' : 'Approximate road map preview'}>
  {#if !error}<div class="map" bind:this={host}></div>{:else}<p role="status">Location map unavailable.</p>{/if}
  {#if !exact}<p class="approx">Approximate location</p>{/if}
</section>
<style>
  .location-preview{position:relative;height:13rem;margin:1rem 0;border:1px solid #414843;background:#202421}.map{width:100%;height:100%}.approx{position:absolute;left:.5rem;top:.5rem;margin:0;padding:.25rem .45rem;background:#171a18;color:#f1efe8;font:.75rem system-ui,sans-serif}.location-preview p[role=status]{padding:1rem;color:#c6d0c5}
</style>
