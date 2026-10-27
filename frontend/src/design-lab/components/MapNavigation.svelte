<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { Basemap, Viewport } from '../contract';
  import { language, tr } from '../../app/language';
  let { viewport, ready, basemap, pitch, overlayExpanded = false, compactHidden = false, areaEnabled = false, areaActive = false, onbasemap, onviewtoggle, onarea, onlocate }: {
    viewport: Viewport; ready: boolean; basemap: Basemap; pitch: number; overlayExpanded?: boolean; compactHidden?: boolean; areaEnabled?: boolean; areaActive?: boolean;
    onbasemap(value: Basemap): void; onviewtoggle(): void; onarea(): void; onlocate(value: Viewport): void;
  } = $props();
  let expanded = $state(false);
  let viewButton: HTMLButtonElement;
  let locating = $state(false);
  let locationError = $state('');
  let requestGeneration = 0;
  $effect(() => { if (compactHidden) expanded = false; });
  onDestroy(() => { requestGeneration++; });
  function chooseView(value: Basemap) { onbasemap(value); expanded = false; viewButton?.focus(); }
  function keydown(event: KeyboardEvent) { if (event.key === 'Escape' && expanded) { event.preventDefault(); event.stopImmediatePropagation(); expanded = false; viewButton?.focus(); } }
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
<svelte:window onkeydown={keydown} />
<nav class="map-navigation" class:compact-hidden={compactHidden} aria-label={tr('Map navigation', $language)}>
  <div class="navigation-stack">
    <button bind:this={viewButton} class="view-button" type="button" disabled={!ready} aria-label={tr('View', $language)} title={tr('Map view', $language)} aria-expanded={expanded} aria-controls="map-navigation-view" onclick={() => expanded = !expanded}>{tr('View', $language)}<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
    <button class="dimension-button" type="button" disabled={!ready} aria-label={tr(pitch > .5 ? 'Switch to 2D' : 'Switch to 3D', $language)} title={tr(pitch > .5 ? 'Switch to 2D' : 'Switch to 3D', $language)} aria-pressed={pitch > .5} onclick={onviewtoggle}>{pitch > .5 ? '3D' : '2D'}</button>
    <button type="button" disabled={!ready || locating} aria-label={tr(locating ? 'Finding your location…' : 'Your location', $language)} title={tr('Your location', $language)} aria-busy={locating} onclick={locate}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/></svg></button>
    <button type="button" class:active={areaActive} disabled={!ready || !areaEnabled} aria-label={tr('Search this area', $language)} title={tr('Search this area', $language)} onclick={onarea}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><circle cx="11" cy="11" r="4"/><path d="m14 14 4 4"/></svg></button>
  </div>
  {#if expanded}<div id="map-navigation-view" class="view-menu" class:below={overlayExpanded} role="group" aria-label={tr('Map view', $language)}>
    <button type="button" aria-pressed={basemap !== 'satellite'} onclick={() => chooseView('vector')}>{tr('Street', $language)}</button><button type="button" aria-pressed={basemap === 'satellite'} onclick={() => chooseView('satellite')}>{tr('Satellite', $language)}</button>
  </div>{/if}
  {#if locating || locationError}<p class="location-status" role={locationError ? 'alert' : 'status'}>{tr(locationError || 'Finding your location…', $language)}{#if locationError}<button type="button" aria-label={tr('Close', $language)} onclick={() => locationError = ''}>×</button>{/if}</p>{/if}
</nav>
<style>
  .map-navigation { position:absolute;z-index:7;right:.75rem;bottom:2rem;display:flex;align-items:flex-end;gap:.4rem;color:var(--ink); }
  .map-navigation.compact-hidden { display:none; }
  .navigation-stack,.view-menu { border:1px solid var(--line);background:var(--panel);box-shadow:0 2px 8px #0002; }
  .navigation-stack { display:flex;flex-direction:column; }
  button { position:relative;display:grid;place-items:center;width:2.75rem;height:2.75rem;padding:.7rem;border:0;color:inherit;background:transparent;font:inherit;cursor:pointer; }
  .navigation-stack > button + button { border-top:1px solid var(--line); }
  button:hover:not(:disabled),button.active,button[aria-pressed=true] { background:var(--panel-selected); }
  button:disabled { opacity:.4;cursor:default; }
  button:focus-visible { z-index:1;outline:2px solid var(--ink);outline-offset:-3px; }
  svg { width:1.15rem;height:1.15rem;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round; }
  .view-button { width:auto;min-width:44px;padding:.3rem .5rem;gap:0;font-size:.6875rem; }
  .view-button svg { width:.75rem;height:.75rem; }
  .dimension-button { font-size:.75rem;font-weight:500; }
  .view-menu { position:absolute;right:calc(100% + .4rem);bottom:0;display:flex;padding:.25rem; }
  .view-menu button { width:auto;min-width:80px;padding:.4rem .7rem;font-size:.8125rem; }
  .location-status { position:absolute;right:3.2rem;bottom:0;display:flex;align-items:center;gap:.5rem;width:max-content;max-width:min(16rem,60vw);margin:0;padding:.65rem .75rem;border:1px solid var(--line);background:var(--panel);font-size:.75rem;line-height:1.4; }
  .location-status button { flex:none;width:44px;height:44px;padding:.25rem; }
  @media(max-width:40rem) {
    .map-navigation { bottom:calc(var(--mobile-sheet-height,56px) + 5.5rem);right:.5rem; }
    .navigation-stack { display:grid;grid-template-columns:60px 44px; }
    .navigation-stack > button { width:100%; }
    .navigation-stack > button + button { border-top:0; }
    .navigation-stack > button:nth-child(even) { border-left:1px solid var(--line); }
    .navigation-stack > button:nth-child(n+3) { border-top:1px solid var(--line); }
    .view-button { display:flex;gap:.25rem;min-width:60px;font-size:.75rem; }
    .view-menu { right:0;bottom:calc(100% + .3rem); }
    .view-menu.below { bottom:auto;top:calc(100% + .3rem); }
    .location-status { right:0;bottom:calc(100% + .4rem);max-width:min(18rem,85vw); }
  }
</style>
