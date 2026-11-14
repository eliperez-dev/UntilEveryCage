<script lang="ts">
  import type { Basemap } from '../contract';
  import { language, tr } from '../../app/language';

  let { ready, basemap, pitch, onbasemap, onviewtoggle }: {
    ready: boolean;
    basemap: Basemap;
    pitch: number;
    onbasemap(value: Basemap): void;
    onviewtoggle(): void;
  } = $props();
</script>

<nav class="map-navigation" aria-label={tr('Map navigation', $language)}>
  <div class="navigation-stack">
    <div class="style-options" role="group" aria-label={tr('Map style', $language)}>
      <button class="style-toggle" type="button" role="switch" disabled={!ready} aria-checked={basemap === 'satellite'} aria-label={`${tr('Map style', $language)}: ${tr(basemap === 'satellite' ? 'Satellite' : 'Street', $language)}`} title={`${tr(basemap === 'satellite' ? 'Satellite' : 'Street', $language)} → ${tr(basemap === 'satellite' ? 'Street' : 'Satellite', $language)}`} onclick={() => onbasemap(basemap === 'satellite' ? 'vector' : 'satellite')}><span>{tr(basemap === 'satellite' ? 'Satellite' : 'Street', $language)}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8h15l-4-4M20 16H5l4 4"/></svg></button>
    </div>
    <button class="dimension-button" type="button" disabled={!ready} aria-label={tr(pitch > .5 ? 'Switch to 2D' : 'Switch to 3D', $language)} title={tr('Right-drag to tilt and rotate', $language)} aria-describedby="map-camera-help" aria-pressed={pitch > .5} onclick={onviewtoggle}>{pitch > .5 ? '3D' : '2D'}</button>
  </div>
  <span id="map-camera-help" class="sr-only">{tr('Right-drag to tilt and rotate', $language)}. {tr('On touchscreens, use two fingers to tilt.', $language)}</span>
</nav>

<style>
  .map-navigation, .navigation-stack, .style-options { display: flex; align-items: center; }
  button { display: flex; align-items: center; justify-content: center; flex: none; min-width: 44px; min-height: 44px; padding: .65rem; border: 0; border-left: 1px solid var(--line); color: inherit; background: transparent; font: inherit; font-size: .75rem; cursor: pointer; }
  button:hover:not(:disabled), button[aria-pressed=true] { background: var(--panel-selected); }
  button:disabled { opacity: .4; cursor: default; }
  button:focus-visible { outline: 2px solid var(--ink); outline-offset: -3px; }
  .style-toggle { gap: .6rem; width: 7rem; }
  .style-toggle svg { width: .85rem; flex: none; fill: none; stroke: currentColor; stroke-width: 1.5; }
  .dimension-button { font-weight: 500; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
</style>
