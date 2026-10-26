<script lang="ts">
  import 'maplibre-gl/dist/maplibre-gl.css';
  import type { Map as MapLibreMap } from 'maplibre-gl';
  import workerUrl from '../map/persistentMapWorker.ts?worker&url';
  import { CATEGORY_PRIMARY_BY_SOURCE_KEY } from '../features/locations/categoryPresentation';
  import { locationPreviewMode, locationPreviewPinFile, locationPreviewZoom } from '../features/locations/locationPreview';

  let { latitude, longitude, precision, category }: { latitude: number; longitude: number; precision: string; category: string } = $props();
  let host = $state<HTMLDivElement>();
  let error = $state(false);
  let pinLoaded = $state(false);
  let exact = $derived(locationPreviewMode(precision) === 'satellite');

  $effect(() => {
    const container = host;
    const lat = latitude;
    const lon = longitude;
    const precisionValue = precision;
    const categoryValue = category;
    if (!container || !Number.isFinite(lat) || !Number.isFinite(lon)) return;

    let disposed = false;
    let map: MapLibreMap | undefined;
    error = false;
    pinLoaded = false;
    void (async () => {
      try {
        const [maplibregl, styles] = await Promise.all([import('maplibre-gl'), import('../map/baseMapStyle')]);
        if (disposed) return;
        maplibregl.setWorkerUrl(workerUrl);
        const instance = new maplibregl.Map({
          container,
          style: styles.createBaseStyle(locationPreviewMode(precisionValue) === 'satellite' ? 'satellite' : 'vector', { includeTransport: false }) as never,
          center: [lon, lat],
          zoom: locationPreviewZoom(precisionValue),
          attributionControl: { compact: true },
          interactive: false,
        });
        map = instance;
        instance.on('error', event => {
          if (/worker failed to load/i.test(event.error.message)) {
            pinLoaded = false;
            error = true;
          }
        });
        instance.once('style.load', () => {
          if (disposed) return;
          instance.addSource('record-location', {
            type: 'geojson',
            data: { type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] }, properties: {} },
          });
          void instance.loadImage(`${import.meta.env.BASE_URL}v1-pins/${locationPreviewPinFile(categoryValue, CATEGORY_PRIMARY_BY_SOURCE_KEY)}`).then(({ data }) => {
            if (disposed) return;
            instance.addImage('record-location-pin', data);
            instance.addLayer({
              id: 'record-location-pin', type: 'symbol', source: 'record-location',
              layout: { 'icon-image': 'record-location-pin', 'icon-anchor': 'bottom', 'icon-size': 0.45 },
            });
            if (!disposed && !error && instance.getLayer('record-location-pin')) pinLoaded = true;
          }).catch(() => { if (!disposed) error = true; });
        });
      } catch {
        if (!disposed) error = true;
      }
    })();
    return () => { disposed = true; map?.remove(); };
  });
</script>

<section class="location-preview" aria-label={exact ? 'Satellite location preview' : 'Approximate road map preview'}>
  <div class="map" bind:this={host} data-pin-loaded={pinLoaded}></div>
  {#if error}<p class="map-error" role="status">Location map unavailable.</p>{/if}
  {#if !exact}<p class="approx">Approximate location</p>{/if}
</section>

<style>
  .location-preview{position:relative;height:13rem;margin:1rem 0;border:1px solid #414843;background:#202421}.map{width:100%;height:100%}.approx,.map-error{position:absolute;left:.5rem;top:.5rem;margin:0;padding:.25rem .45rem;background:#171a18;color:#f1efe8;font:.75rem system-ui,sans-serif}.map-error{top:auto;bottom:.5rem}
</style>
