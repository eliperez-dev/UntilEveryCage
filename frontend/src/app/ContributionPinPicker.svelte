<script lang="ts">
  import { onMount } from 'svelte';
  import * as maplibregl from 'maplibre-gl';
  import type { Map as MapLibreMap, Marker as MapLibreMarker } from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
  import { createBaseStyle } from '../map/baseMapStyle';
  import { normalizeClaimedPoint } from '../map/claimedPoint';

  let { latitude, longitude, onpoint, onclear }: {
    latitude: number | undefined;
    longitude: number | undefined;
    onpoint(latitude: number | undefined, longitude: number | undefined, method: 'manual_pin' | 'text' | undefined): void;
    onclear(): void;
  } = $props();
  let host: HTMLDivElement;
  let map: MapLibreMap | undefined;
  let marker: MapLibreMarker | undefined;
  let selectedPoint: { latitude: number; longitude: number } | undefined;
  let basemapMessage = $state('');

  function pin(lat: number, lng: number, method: 'manual_pin' | 'text') {
    const point = normalizeClaimedPoint(lat, lng);
    if (!point) return;
    selectedPoint = point;
    onpoint(point.latitude, point.longitude, method);
    placeMarker(point.latitude, point.longitude);
  }
  function placeMarker(lat: number, lng: number) {
    const point = normalizeClaimedPoint(lat, lng);
    if (!point || lat < -90 || lat > 90 || lng < -180 || lng > 180) return;
    selectedPoint = point;
    attachMarker();
  }
  function attachMarker() {
    if (!map || !marker || !selectedPoint) return;
    marker.setLngLat([selectedPoint.longitude, selectedPoint.latitude]).addTo(map);
  }
  function numericPoint(lat: number | undefined, lng: number | undefined, method: 'text' | undefined) {
    if (lat === undefined || lng === undefined) { selectedPoint = undefined; marker?.remove(); onpoint(lat, lng, undefined); return; }
    const normalized = normalizeClaimedPoint(lat, lng);
    if (!normalized || lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      selectedPoint = undefined;
      marker?.remove();
      onpoint(lat, lng, undefined);
      return;
    }
    onpoint(normalized.latitude, normalized.longitude, method);
    placeMarker(normalized.latitude, normalized.longitude);
  }
  function clearPoint() {
    selectedPoint = undefined;
    marker?.remove();
    onclear();
  }

  onMount(() => {
    if (!host) return;
    try {
      maplibregl.setWorkerUrl(workerUrl);
      map = new maplibregl.Map({
        container: host,
        style: createBaseStyle('muted', { includeTransport: false }) as maplibregl.StyleSpecification,
        center: [12, 55], zoom: 3.2, maxZoom: 19,
        attributionControl: { compact: true }, cooperativeGestures: true,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
      const el = document.createElement('span'); el.className = 'contribution-pin'; el.setAttribute('aria-hidden', 'true');
      marker = new maplibregl.Marker({ element: el, anchor: 'bottom' });
      map.on('load', () => {
        map?.setMinZoom(1);
        attachMarker();
      });
      map.on('click', event => pin(event.lngLat.lat, event.lngLat.lng, 'manual_pin'));
      map.on('error', () => { basemapMessage = 'Some map tiles are unavailable. You can still enter coordinates below.'; });
      return () => { map?.remove(); map = undefined; marker = undefined; };
    } catch {
      map = undefined;
      marker = undefined;
      basemapMessage = 'The map could not be opened. You can enter coordinates below instead.';
    }
  });

  $effect(() => {
    if (latitude !== undefined && longitude !== undefined) {
      const point = normalizeClaimedPoint(latitude, longitude);
      if (point && latitude >= -90 && latitude <= 90 && longitude >= -180 && longitude <= 180) selectedPoint = point;
      else { selectedPoint = undefined; marker?.remove(); }
    } else selectedPoint = undefined;
    attachMarker();
    if (latitude === undefined || longitude === undefined) marker?.remove();
  });
</script>

<div class="picker-shell">
  <div bind:this={host} class="pin-map" role="application" aria-label="Choose a location on the map. Click to place a suggested point, or enter coordinates below." ></div>
  {#if basemapMessage}<p class="map-error" role="status">{basemapMessage}</p>{/if}
</div>
<div class="coordinate-inputs">
  <label>Latitude<input aria-label="Latitude" type="number" min="-90" max="90" step="any" value={latitude ?? ''} oninput={(event) => { const value = event.currentTarget.value; const next = value === '' ? undefined : Number(value); numericPoint(next, longitude, next !== undefined && longitude !== undefined ? 'text' : undefined); }} /></label>
  <label>Longitude<input aria-label="Longitude" type="number" min="-180" max="180" step="any" value={longitude ?? ''} oninput={(event) => { const value = event.currentTarget.value; const next = value === '' ? undefined : Number(value); numericPoint(latitude, next, latitude !== undefined && next !== undefined ? 'text' : undefined); }} /></label>
</div>
<button class="clear-point" type="button" onclick={clearPoint} disabled={latitude === undefined && longitude === undefined}>Clear selected point</button>

<style>
  .picker-shell{position:relative;height:19rem;border:1px solid #67706a;background:#202726}.pin-map{position:absolute;inset:0}.map-error{position:absolute;top:.65rem;left:.65rem;z-index:2;max-width:20rem;margin:0;padding:.35rem .5rem;background:#171a18eb;color:#f0d6c4;font:.75rem system-ui}.pin-map :global(.maplibregl-ctrl-attrib){background:#171a18eb;color:#eee9df;font:.58rem system-ui}.pin-map :global(.maplibregl-ctrl-attrib a){color:#ded1a9}.pin-map :global(.maplibregl-ctrl-group){border:1px solid #69716a;border-radius:2px;background:#171a18}.pin-map :global(.maplibregl-ctrl-group button){width:2rem;height:2rem;background-color:transparent}.pin-map :global(.maplibregl-ctrl-group button+button){border-top:1px solid #4c554f}.pin-map :global(.maplibregl-ctrl-icon){filter:invert(.9)}:global(.contribution-pin){display:block;width:1.1rem;height:1.1rem;border:2px solid #eee9df;border-radius:50% 50% 50% 0;background:#ad5b47;transform:rotate(-45deg);box-shadow:0 1px 7px #000}.coordinate-inputs{display:grid;grid-template-columns:1fr 1fr;gap:1rem;max-width:34rem}.coordinate-inputs label{display:grid;gap:.35rem;color:#e6e2d8;font-size:.9rem}.coordinate-inputs input{width:100%;min-height:2.6rem;padding:.55rem .65rem;border:1px solid #59615c;border-radius:2px;background:#202523;color:#f4f1e9;font:inherit}.clear-point{justify-self:start;min-height:2.4rem;padding:.4rem .65rem;border:1px solid #59615c;background:#202523;color:#e5ddcf;font:inherit;cursor:pointer}.clear-point:disabled{opacity:.45;cursor:default}@media(max-width:38rem){.picker-shell{height:15rem}.coordinate-inputs{grid-template-columns:1fr}}
</style>
