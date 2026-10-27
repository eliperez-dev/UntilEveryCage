<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { Basemap, Viewport } from '../contract';
  import { language, tr } from '../../app/language';
  let { viewport, ready, basemap, pitch, compactHidden = false, areaEnabled = false, areaActive = false, onbasemap, onviewtoggle, onarea, onlocate }: {
    viewport: Viewport; ready: boolean; basemap: Basemap; pitch: number; compactHidden?: boolean; areaEnabled?: boolean; areaActive?: boolean;
    onbasemap(value: Basemap): void; onviewtoggle(): void; onarea(): void; onlocate(value: Viewport): void;
  } = $props();
  let locating = $state(false);
  let locationError = $state('');
  let requestGeneration = 0;
  onDestroy(() => { requestGeneration++; });
  function locate() {
    if (locating) return;
    locationError = '';
    if (!navigator.geolocation) { locationError = 'Your location is unavailable.'; return; }
    locating = true;
    const generation = ++requestGeneration;
    try { navigator.geolocation.getCurrentPosition(position => {
      if (generation !== requestGeneration) return;
      locating = false;
      onlocate({ ...viewport, centerLat: position.coords.latitude, centerLon: position.coords.longitude, zoom: 12 });
    }, error => {
      if (generation !== requestGeneration) return;
      locating = false;
      locationError = error.code === 1 ? 'Location permission was denied.' : error.code === 3 ? 'Location request timed out.' : 'Your location is unavailable.';
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 }); }
    catch { locating = false; locationError = 'Your location is unavailable.'; }
  }
</script>
<nav class="map-navigation" class:compact-hidden={compactHidden} aria-label={tr('Map navigation', $language)}>
  <div class="navigation-stack">
    <div class="style-options" role="group" aria-label={tr('Map style', $language)}>
      <button class="desktop-style" type="button" disabled={!ready} aria-pressed={basemap !== 'satellite'} onclick={() => onbasemap('vector')}>{tr('Street', $language)}</button>
      <button class="desktop-style" type="button" disabled={!ready} aria-pressed={basemap === 'satellite'} onclick={() => onbasemap('satellite')}>{tr('Satellite', $language)}</button>
      <button class="mobile-style" type="button" disabled={!ready} aria-label={`${tr('Map style', $language)}: ${tr(basemap === 'satellite' ? 'Satellite' : 'Street', $language)}`} onclick={() => onbasemap(basemap === 'satellite' ? 'vector' : 'satellite')}>{tr(basemap === 'satellite' ? 'Satellite' : 'Street', $language)}<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8h15l-4-4M20 16H5l4 4"/></svg></button>
    </div>
    <button class="dimension-button" type="button" disabled={!ready} aria-label={tr(pitch > .5 ? 'Switch to 2D' : 'Switch to 3D', $language)} title={tr('Right-drag to tilt and rotate', $language)} aria-describedby="map-camera-help" aria-pressed={pitch > .5} onclick={onviewtoggle}>{pitch > .5 ? '3D' : '2D'}</button>
    <button type="button" disabled={!ready || locating} aria-label={tr(locating ? 'Finding your location…' : 'Your location', $language)} title={tr('Your location', $language)} aria-busy={locating} onclick={locate}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/></svg></button>
    <button type="button" class:active={areaActive} disabled={!ready || (!areaEnabled && !areaActive)} aria-label={areaActive ? `${tr('Remove filter', $language)}: ${tr('Searching this area', $language)}` : tr('Search this area', $language)} title={tr(areaActive ? 'Clear area search' : 'Search this area', $language)} onclick={onarea}><svg viewBox="0 0 24 24" aria-hidden="true">{#if areaActive}<path d="m7 7 10 10M17 7 7 17"/>{:else}<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><circle cx="11" cy="11" r="4"/><path d="m14 14 4 4"/>{/if}</svg></button>
  </div>
  <span id="map-camera-help" class="sr-only">{tr('Right-drag to tilt and rotate', $language)}. {tr('On touchscreens, use two fingers to tilt.', $language)}</span>
  {#if areaActive}<div class="area-indicator"><span>{tr('Searching this area', $language)}</span><button type="button" aria-label={tr('Clear area search', $language)} onclick={onarea}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17"/></svg></button></div>{/if}
  {#if locating || locationError}<p class="location-status" role={locationError ? 'alert' : 'status'}>{tr(locationError || 'Finding your location…', $language)}{#if locationError}<button type="button" aria-label={tr('Close', $language)} onclick={() => locationError = ''}>×</button>{/if}</p>{/if}
</nav>
<style>
  .map-navigation { position:relative;display:flex;align-items:center;flex:none;color:var(--ink); }
  .map-navigation.compact-hidden { visibility:hidden;pointer-events:none; }
  .navigation-stack { display:flex;align-items:center; }
  button { position:relative;display:flex;align-items:center;justify-content:center;flex:none;min-width:44px;min-height:44px;height:44px;padding:.65rem;border:0;color:inherit;background:transparent;font:inherit;font-size:.75rem;cursor:pointer; }
  .navigation-stack > button,.style-options { border-left:1px solid var(--line); }
  button:hover:not(:disabled),button.active,button[aria-pressed=true] { background:var(--panel-selected); }
  button:disabled { opacity:.4;cursor:default; }
  button:focus-visible { z-index:1;outline:2px solid var(--ink);outline-offset:-3px; }
  svg { width:1.1rem;height:1.1rem;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round; }
  .style-options { display:flex; }
  .desktop-style { min-width:4.5rem;padding-inline:.7rem; }
  .mobile-style { display:none; }
  .dimension-button { font-weight:500; }
  .sr-only { position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap; }
  .area-indicator { position:absolute;z-index:3;right:0;top:calc(100% + .5rem);display:flex;align-items:center;max-width:min(24rem,calc(100vw - 2rem));border:1px solid var(--line);background:var(--panel);box-shadow:0 2px 8px #0002; }
  .area-indicator span { padding:.55rem .2rem .55rem .8rem;font-size:.75rem;line-height:1.3; }
  .location-status { position:absolute;z-index:4;right:0;top:calc(100% + .5rem);display:flex;align-items:center;gap:.5rem;width:max-content;max-width:min(19rem,calc(100vw - 2rem));margin:0;padding:.35rem .6rem;border:1px solid var(--line);background:var(--panel);font-size:.75rem;line-height:1.4; }
  .location-status button { width:44px; }
  @media(max-width:40rem) {
    .style-options { border-left:0; }
    .desktop-style { display:none; }
    .mobile-style { display:flex;gap:.45rem;max-width:9rem;padding-inline:.75rem; }
    .mobile-style svg { width:.85rem; }
    .area-indicator { right:50%;transform:translateX(50%);width:max-content;max-width:calc(100vw - 2rem); }
  }
</style>
