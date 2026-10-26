<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { Viewport } from '../contract';
  import { language, tr } from '../../app/language';

  let { viewport, ready, areaEnabled = false, areaActive = false, onviewport, onarea, onlocate }: {
    viewport: Viewport;
    ready: boolean;
    areaEnabled?: boolean;
    areaActive?: boolean;
    onviewport(value: Viewport): void;
    onarea(): void;
    onlocate(value: Viewport): void;
  } = $props();
  let expanded = $state(false);
  let locating = $state(false);
  let locationError = $state('');
  let requestGeneration = 0;
  onDestroy(() => { requestGeneration++; });

  function move(patch: Partial<Viewport>) {
    const bearing = patch.bearing === undefined ? undefined : ((patch.bearing + 180) % 360 + 360) % 360 - 180;
    onviewport({ ...viewport, ...patch, ...(bearing === undefined ? {} : { bearing }) });
  }
  function pan(x: number, y: number) {
    // A quarter of the current world span gives useful steps at every zoom.
    const span = 90 / 2 ** viewport.zoom;
    const angle = (viewport.bearing ?? 0) * Math.PI / 180;
    const east = x * Math.cos(angle) + y * Math.sin(angle);
    const north = -x * Math.sin(angle) + y * Math.cos(angle);
    move({
      centerLon: ((viewport.centerLon + east * span + 180) % 360 + 360) % 360 - 180,
      centerLat: Math.max(-85, Math.min(85, viewport.centerLat + north * span * Math.cos(viewport.centerLat * Math.PI / 180))),
    });
  }
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
    catch {
      locating = false;
      locationError = 'Your location is unavailable.';
    }
  }
</script>

  <nav class="map-navigation" aria-label={tr('Map navigation', $language)}>
  <div class="navigation-stack">
    <button class="compass" type="button" disabled={!ready} aria-label={tr('Reset north', $language)} title={tr('Reset north', $language)} onclick={() => move({ bearing: 0 })}>
      <svg viewBox="0 0 24 24" aria-hidden="true" style:transform={`rotate(${-(viewport.bearing ?? 0)}deg)`}><path class="north" d="m12 3 5 16-5-3-5 3Z"/><path d="M12 3v13"/></svg><span>N</span>
    </button>
    <button type="button" disabled={!ready || viewport.zoom >= 18} aria-label={tr('Zoom in', $language)} title={tr('Zoom in', $language)} onclick={() => move({ zoom: Math.min(18, viewport.zoom + 1) })}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M12 5v14"/></svg></button>
    <button type="button" disabled={!ready || viewport.zoom <= 1} aria-label={tr('Zoom out', $language)} title={tr('Zoom out', $language)} onclick={() => move({ zoom: Math.max(1, viewport.zoom - 1) })}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg></button>
    <button type="button" disabled={!ready || locating} aria-label={tr(locating ? 'Finding your location…' : 'Your location', $language)} title={tr('Your location', $language)} aria-busy={locating} onclick={locate}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/></svg></button>
    <button type="button" class:active={areaActive} disabled={!ready || !areaEnabled} aria-label={tr('Search this area', $language)} title={tr('Search this area', $language)} onclick={onarea}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><circle cx="11" cy="11" r="4"/><path d="m14 14 4 4"/></svg></button>
    <button type="button" aria-expanded={expanded} aria-controls="map-navigation-extra" aria-label={tr('More map controls', $language)} title={tr('More map controls', $language)} onclick={() => expanded = !expanded}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></svg></button>
  </div>
  {#if expanded}<div id="map-navigation-extra" class="navigation-extra">
    <div class="rotation">
      <button type="button" disabled={!ready} aria-label={tr('Rotate left', $language)} title={tr('Rotate left', $language)} onclick={() => move({ bearing: (viewport.bearing ?? 0) - 30 })}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10a8 8 0 1 1 1 8M4 4v6h6"/></svg></button>
      <button type="button" disabled={!ready} aria-label={tr('Rotate right', $language)} title={tr('Rotate right', $language)} onclick={() => move({ bearing: (viewport.bearing ?? 0) + 30 })}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 10a8 8 0 1 0-1 8m1-14v6h-6"/></svg></button>
    </div>
    <div class="pan-controls">
      <button class="up" type="button" disabled={!ready} aria-label={tr('Pan up', $language)} title={tr('Pan up', $language)} onclick={() => pan(0, 1)}>↑</button>
      <button class="left" type="button" disabled={!ready} aria-label={tr('Pan left', $language)} title={tr('Pan left', $language)} onclick={() => pan(-1, 0)}>←</button>
      <button class="right" type="button" disabled={!ready} aria-label={tr('Pan right', $language)} title={tr('Pan right', $language)} onclick={() => pan(1, 0)}>→</button>
      <button class="down" type="button" disabled={!ready} aria-label={tr('Pan down', $language)} title={tr('Pan down', $language)} onclick={() => pan(0, -1)}>↓</button>
    </div>
  </div>{/if}
  {#if locating || locationError}<p class="location-status" role={locationError ? 'alert' : 'status'}>{tr(locationError || 'Finding your location…', $language)}{#if locationError}<button type="button" aria-label={tr('Close', $language)} onclick={() => locationError = ''}>×</button>{/if}</p>{/if}
</nav>

<style>
  .map-navigation { position: absolute; z-index: 4; right: .75rem; bottom: 2rem; display: flex; align-items: flex-end; gap: .4rem; color: var(--ink); }
  .navigation-stack, .navigation-extra { border: 1px solid var(--line); background: var(--panel); box-shadow: 0 2px 8px #0002; }
  .navigation-stack { display: flex; flex-direction: column; }
  button { position: relative; display: grid; place-items: center; width: 2.75rem; height: 2.75rem; padding: .7rem; border: 0; color: inherit; background: transparent; font: inherit; cursor: pointer; }
  .navigation-stack > button + button { border-top: 1px solid var(--line); }
  button:hover:not(:disabled), button.active { background: var(--panel-selected); }
  button:disabled { opacity: .4; cursor: default; }
  button:focus-visible { z-index: 1; outline: 2px solid var(--ink); outline-offset: -3px; }
  svg { width: 1.15rem; height: 1.15rem; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
  .compass { padding-top: .9rem; }
  .compass svg { width: 1.3rem; height: 1.3rem; }
  .compass .north { fill: var(--ink); }
  .compass span { position: absolute; top: .18rem; font-size: .5rem; font-weight: 600; }
  .navigation-extra { position: absolute; right: calc(100% + .4rem); bottom: 0; padding: .25rem; }
  .rotation { display: flex; justify-content: center; border-bottom: 1px solid var(--line); }
  .pan-controls { display: grid; grid-template-columns: repeat(3, 2.75rem); grid-template-rows: repeat(3, 2.75rem); }
  .pan-controls button { font-size: 1.2rem; padding: .4rem; }
  .up { grid-area: 1 / 2; } .left { grid-area: 2 / 1; } .right { grid-area: 2 / 3; } .down { grid-area: 3 / 2; }
  .location-status { position: absolute; right: 3.2rem; bottom: 0; display: flex; align-items: center; gap: .5rem; width: max-content; max-width: min(16rem, 60vw); margin: 0; padding: .65rem .75rem; border: 1px solid var(--line); background: var(--panel); font-size: .75rem; line-height: 1.4; }
  .location-status button { flex: none; width: 2rem; height: 2rem; padding: .25rem; }
  @media (max-width: 40rem) { .map-navigation { bottom: 1.5rem; right: .5rem; } .navigation-stack { flex-direction: row; } .navigation-stack > button + button { border-top: 0; border-left: 1px solid var(--line); } .navigation-extra { right: 0; bottom: calc(100% + .4rem); } .location-status { right: 0; bottom: calc(100% + .4rem); max-width: min(18rem, 85vw); } }
</style>
