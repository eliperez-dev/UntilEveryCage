<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { Basemap } from '../contract';
  import { language, tr } from '../../app/language';
  import { requestDeviceLocation } from '../../features/search/nearbySearch';
  let { ready, basemap, pitch, compactHidden = false, areaEnabled = false, areaActive = false, searchMode = 'box', radiusMiles = 50, onbasemap, onviewtoggle, onarea, onlocate, onsettings }: {
    ready: boolean; basemap: Basemap; pitch: number; compactHidden?: boolean; areaEnabled?: boolean; areaActive?: boolean; searchMode?:'box'|'radius'; radiusMiles?:number;
    onbasemap(value: Basemap): void; onviewtoggle(): void; onarea(): void; onlocate(value: {latitude:number;longitude:number}): void; onsettings(value:{mode:'box'|'radius';radiusMiles:number}):void;
  } = $props();
  let locating = $state(false);
  let locationError = $state('');
  let locationRequest: AbortController | null = null;
  let settingsOpen = $state(false);
  let navNode: HTMLElement;
  let settingsButton: HTMLButtonElement;
  function closeSettings(event: KeyboardEvent) { if(event.key === 'Escape' && settingsOpen) { event.preventDefault(); event.stopPropagation(); settingsOpen = false; settingsButton?.focus(); } }
  onDestroy(() => { locationRequest?.abort(); });
  async function locate() {
    if (locating) return;
    locationError = '';
    locating = true;
    const request = new AbortController();
    locationRequest = request;
    try { const coordinates = await requestDeviceLocation(request.signal); if (!request.signal.aborted) onlocate(coordinates); }
    catch (error) { if (!request.signal.aborted) locationError = error instanceof Error ? error.message : 'Your location is unavailable.'; }
    finally { if (locationRequest === request && !request.signal.aborted) { locating = false; locationRequest = null; } }
  }
</script>
<svelte:window onkeydown={closeSettings} onpointerdown={(event) => { if(settingsOpen && event.target instanceof Node && !navNode?.contains(event.target)) settingsOpen = false; }} />
<nav bind:this={navNode} class="map-navigation" class:compact-hidden={compactHidden} aria-label={tr('Map navigation', $language)}>
  <div class="navigation-stack">
    <div class="style-options" role="group" aria-label={tr('Map style', $language)}>
      <button class="style-toggle" type="button" role="switch" disabled={!ready} aria-checked={basemap === 'satellite'} aria-label={`${tr('Map style', $language)}: ${tr(basemap === 'satellite' ? 'Satellite' : 'Street', $language)}`} title={`${tr(basemap === 'satellite' ? 'Satellite' : 'Street', $language)} → ${tr(basemap === 'satellite' ? 'Street' : 'Satellite', $language)}`} onclick={() => onbasemap(basemap === 'satellite' ? 'vector' : 'satellite')}><span>{tr(basemap === 'satellite' ? 'Satellite' : 'Street', $language)}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8h15l-4-4M20 16H5l4 4"/></svg></button>
    </div>
    <button class="dimension-button" type="button" disabled={!ready} aria-label={tr(pitch > .5 ? 'Switch to 2D' : 'Switch to 3D', $language)} title={tr('Right-drag to tilt and rotate', $language)} aria-describedby="map-camera-help" aria-pressed={pitch > .5} onclick={onviewtoggle}>{pitch > .5 ? '3D' : '2D'}</button>
    <button type="button" disabled={!ready || locating} aria-label={tr(locating ? 'Finding your location…' : 'Your location', $language)} title={tr('Your location', $language)} aria-busy={locating} onclick={locate}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/></svg></button>
    <button type="button" class:active={areaActive} disabled={!ready || !areaEnabled} aria-label={tr('Search this area', $language)} title={tr('Search this area', $language)} onclick={onarea}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><circle cx="11" cy="11" r="4"/><path d="m14 14 4 4"/></svg></button>
    <button bind:this={settingsButton} type="button" disabled={!ready || !areaEnabled} aria-label={tr('Search settings', $language)} title={tr('Search settings', $language)} aria-expanded={settingsOpen} aria-controls="map-search-settings" onclick={() => settingsOpen = !settingsOpen}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h7m5 0h4M4 17h3m5 0h8M11 4v6M7 14v6"/></svg></button>
  </div>
  {#if settingsOpen}<section id="map-search-settings" class="search-settings" aria-label={tr('Search settings', $language)}><h2>{tr('Search settings', $language)}</h2><fieldset><legend class="sr-only">{tr('Search area', $language)}</legend><label><input type="radio" name="map-search-mode" checked={searchMode === 'box'} onchange={() => onsettings({mode:'box',radiusMiles})} />{tr('Visible map', $language)}</label><label><input type="radio" name="map-search-mode" checked={searchMode === 'radius'} onchange={() => onsettings({mode:'radius',radiusMiles})} />{tr('Radius', $language)}</label></fieldset>{#if searchMode === 'radius'}<label class="radius-setting" for="map-search-radius"><span>{tr('Radius', $language)}</span><output>{tr('{count} miles', $language).replace('{count}',new Intl.NumberFormat($language).format(radiusMiles))}</output></label><input id="map-search-radius" type="range" min="5" max="250" step="5" value={radiusMiles} aria-label={tr('Search radius', $language)} aria-valuetext={tr('{count} miles', $language).replace('{count}',new Intl.NumberFormat($language).format(radiusMiles))} oninput={(event) => onsettings({mode:'radius',radiusMiles:Number(event.currentTarget.value)})} />{/if}</section>{/if}
  <span id="map-camera-help" class="sr-only">{tr('Right-drag to tilt and rotate', $language)}. {tr('On touchscreens, use two fingers to tilt.', $language)}</span>
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
  .style-toggle { gap:.6rem;width:7rem;max-width:9rem;padding-inline:.75rem;background:var(--panel); }
  .style-toggle span { overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
  .style-toggle svg { width:.85rem;flex:none; }
  .dimension-button { font-weight:500; }
  .sr-only { position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap; }
  .location-status { position:absolute;z-index:4;right:0;top:calc(100% + .5rem);display:flex;align-items:center;gap:.5rem;width:max-content;max-width:min(19rem,calc(100vw - 2rem));margin:0;padding:.35rem .6rem;border:1px solid var(--line);background:var(--panel);font-size:.75rem;line-height:1.4; }
  .location-status button { width:44px; }
  .search-settings { position:absolute;z-index:7;top:calc(100% + .5rem);right:0;width:260px;max-width:calc(100vw - 2rem);padding:1rem;border:1px solid var(--line);background:var(--panel);box-shadow:0 8px 24px #0003; }
  .search-settings h2 { margin:0 0 .6rem;font:500 .875rem/1.3 system-ui; }
  .search-settings fieldset { display:flex;gap:.75rem;border:0;padding:0;margin:0 0 .35rem; }
  .search-settings label { display:flex;align-items:center;gap:.45rem;min-height:44px;font-size:.8125rem; }
  .search-settings input { accent-color:var(--ink); }
  .search-settings .radius-setting { justify-content:space-between; }
  .search-settings output { font-variant-numeric:tabular-nums;color:var(--muted); }
  .search-settings input[type=range] { width:100%;min-height:44px;margin:0; }
  .search-settings input:focus-visible { outline:2px solid var(--ink);outline-offset:3px; }
  @media(max-width:40rem) {
    .style-options { border-left:0; }
    .style-toggle { width:6rem; }
  }
</style>
