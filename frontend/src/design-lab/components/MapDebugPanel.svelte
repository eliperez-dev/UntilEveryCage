<script lang="ts">
  import { onMount } from 'svelte';
  import { language, tr } from '../../app/language';
  import type { CacheTuning, DebugMetric, LayoutTuning, WorldCacheTuning } from './mapDebug';
  let { session, renderer, errors = [], clusterMode, clusterRadius, clusterMaxZoom, clusterDuration, clusterMotionDuration, clusterMotionLimit, clusterMotionIdleDelay, rebuildDelay,
    pinScale, usePins, coordinateRadius, privateReferences = false, referenceRadius, referenceOpacity, referenceLabels,
    layout, snapshot, onclose, oncluster, onvisual, oninteraction, onlayout, onreset, onclearcache,
    cacheTuning, tileFadeUnavailable = false, oncache, onresetcaches, onclearindex, oncleartiles, worldTuning, onworld, onclearworld
  }: {
    session: readonly DebugMetric[]; renderer: readonly DebugMetric[]; errors?: readonly string[];
    clusterMode: 'auto' | 'on' | 'off'; clusterRadius: number; clusterMaxZoom: number; clusterDuration: number; clusterMotionDuration: number; clusterMotionLimit: number; clusterMotionIdleDelay: number; rebuildDelay: number;
    pinScale: number; usePins: boolean; coordinateRadius: number; privateReferences?: boolean;
    referenceRadius: number; referenceOpacity: number; referenceLabels: boolean;
    layout: LayoutTuning; snapshot: unknown; onclose(): void;
    oncluster(key: 'mode' | 'radius' | 'cutoff', value: string | number): void;
    onvisual(key: 'pinScale' | 'pins' | 'coordinateRadius' | 'referenceRadius' | 'referenceOpacity' | 'referenceLabels', value: number | boolean): void;
    oninteraction(key: 'duration' | 'debounce' | 'motionDuration' | 'motionLimit' | 'motionIdleDelay', value: number): void;
    onlayout(value: LayoutTuning): void; onreset(): void; onclearcache(): void;
    cacheTuning: CacheTuning;
    tileFadeUnavailable?: boolean;
    oncache(value: CacheTuning): void;
    onresetcaches(): void;
    onclearindex(): void;
    oncleartiles(): void;
    worldTuning: WorldCacheTuning;
    onworld(value: WorldCacheTuning): void;
    onclearworld(): void;
  } = $props();
  let copyStatus = $state('');
  let mobileLayout = $state(false);
  onMount(() => {
    const media = matchMedia('(max-width:40rem)');
    const update = () => { mobileLayout = media.matches; };
    update(); media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  });
  async function copy() {
    try { await navigator.clipboard.writeText(JSON.stringify(snapshot, null, 2)); copyStatus = tr('Copied', $language); }
    catch { copyStatus = tr('Copy failed', $language); }
  }
</script>

<aside id="map-diagnostics" class="map-diagnostics" aria-label={tr('Debug menu', $language)}>
  <header><strong>{tr('Debug menu', $language)}</strong><button type="button" aria-label={tr('Close debug menu', $language)} onclick={onclose}>×</button></header>
  <div class="debug-actions"><button type="button" onclick={copy}>{tr('Copy diagnostics', $language)}</button><button type="button" onclick={onreset}>{tr('Reset temporary settings', $language)}</button></div>
  {#if copyStatus}<small role="status">{copyStatus}</small>{/if}
  {#if errors.length}<ul class="errors" aria-label="Map errors">{#each errors as error}<li>{error}</li>{/each}</ul>{/if}
  <details open><summary>{tr('Session & search', $language)}</summary><dl>{#each session as metric}<div><dt>{metric.label}</dt><dd>{metric.value}</dd></div>{/each}</dl></details>
  <details><summary>{tr('Renderer & timing', $language)}</summary><dl>{#each renderer as metric}<div><dt>{metric.label}</dt><dd>{metric.value}</dd></div>{/each}</dl><button class="cache" type="button" onclick={onclearcache}>Clear projection cache</button></details>
  <details class="cache-controls">
    <summary>{tr('Cache controls', $language)}</summary>
    <fieldset>
      <legend>{tr('Built index', $language)}</legend>
      <label class="checkbox" for="debug-index-enabled"><input id="debug-index-enabled" type="checkbox" checked={cacheTuning.indexEnabled} onchange={e => oncache({ ...cacheTuning, indexEnabled: e.currentTarget.checked })} />{tr('Persist built index', $language)}</label>
      <label for="debug-index-budget">{tr('Index budget', $language)}<output>{cacheTuning.indexMaxMiB} MiB</output></label>
      <input id="debug-index-budget" type="range" min="8" max="64" step="1" disabled={!cacheTuning.indexEnabled} value={cacheTuning.indexMaxMiB} oninput={e => oncache({ ...cacheTuning, indexMaxMiB: Number(e.currentTarget.value) })} />
      <button type="button" onclick={onclearindex}>{tr('Clear built index', $language)}</button>
    </fieldset>
    <fieldset>
      <legend>{tr('Tile cache', $language)}</legend>
      <label class="checkbox" for="debug-tiles-enabled"><input id="debug-tiles-enabled" type="checkbox" checked={cacheTuning.tileEnabled} onchange={e => oncache({ ...cacheTuning, tileEnabled: e.currentTarget.checked })} />{tr('Cache map tiles', $language)}</label>
      <label for="debug-tile-budget">{tr('Tile budget', $language)}<output>{cacheTuning.tileMaxMiB} MiB</output></label>
      <input id="debug-tile-budget" type="range" min="4" max="64" step="1" disabled={!cacheTuning.tileEnabled} value={cacheTuning.tileMaxMiB} oninput={e => oncache({ ...cacheTuning, tileMaxMiB: Number(e.currentTarget.value) })} />
      <label for="debug-tile-entries">{tr('Tile entries', $language)}<output>{cacheTuning.tileMaxEntries}</output></label>
      <input id="debug-tile-entries" type="range" min="32" max="1024" step="16" disabled={!cacheTuning.tileEnabled} value={cacheTuning.tileMaxEntries} oninput={e => oncache({ ...cacheTuning, tileMaxEntries: Number(e.currentTarget.value) })} />
      <label for="debug-tile-ttl" title={tr('Provider expiry takes precedence.', $language)}>{tr('Tile lifetime', $language)}<output>{cacheTuning.tileTtlHours} h</output></label>
      <input id="debug-tile-ttl" type="range" min="1" max="168" step="1" disabled={!cacheTuning.tileEnabled} value={cacheTuning.tileTtlHours} aria-describedby="debug-tile-expiry-help" oninput={e => oncache({ ...cacheTuning, tileTtlHours: Number(e.currentTarget.value) })} />
      <small class="sr-only" id="debug-tile-expiry-help">{tr('Provider expiry takes precedence.', $language)}</small>
      <button type="button" onclick={oncleartiles}>{tr('Clear map tiles', $language)}</button>
    </fieldset>
    <fieldset>
      <legend>{tr('World baseline', $language)}</legend>
      <label class="checkbox" for="debug-world-enabled"><input id="debug-world-enabled" type="checkbox" checked={worldTuning.enabled} onchange={e => onworld({ ...worldTuning, enabled: e.currentTarget.checked })} />{tr('Preload world map', $language)}</label>
      <label for="debug-world-zoom">{tr('World detail', $language)}<output>{worldTuning.maxZoom}</output></label>
      <input id="debug-world-zoom" type="range" min="0" max="5" step="1" disabled={!worldTuning.enabled} value={worldTuning.maxZoom} oninput={e => onworld({ ...worldTuning, maxZoom: Number(e.currentTarget.value) })} />
      <label for="debug-world-budget">{tr('World budget', $language)}<output>{worldTuning.maxMiB} MiB</output></label>
      <input id="debug-world-budget" type="range" min="8" max="40" step="1" disabled={!worldTuning.enabled} value={worldTuning.maxMiB} oninput={e => onworld({ ...worldTuning, maxMiB: Number(e.currentTarget.value) })} />
      <button type="button" onclick={onclearworld}>{tr('Clear world map cache', $language)}</button>
    </fieldset>
    <fieldset>
      <legend>{tr('Map memory', $language)}</legend>
      <label for="debug-ram-tiles">{tr('RAM tiles', $language)}<output>{cacheTuning.ramTiles}</output></label>
      <input id="debug-ram-tiles" type="range" min="32" max="256" step="8" value={cacheTuning.ramTiles} oninput={e => oncache({ ...cacheTuning, ramTiles: Number(e.currentTarget.value) })} />
      <label for="debug-tile-fade">{tr('2D tile fade', $language)}<output>{tileFadeUnavailable ? tr('Unavailable with terrain', $language) : `${cacheTuning.tileFadeMs} ms`}</output></label>
      <input id="debug-tile-fade" type="range" min="0" max="400" step="20" disabled={tileFadeUnavailable} value={cacheTuning.tileFadeMs} oninput={e => oncache({ ...cacheTuning, tileFadeMs: Number(e.currentTarget.value) })} />
      <label for="debug-baseline-opacity">{tr('World preview opacity', $language)}<output>{Math.round(cacheTuning.baselineOpacity * 100)}%</output></label>
      <input id="debug-baseline-opacity" type="range" min="0" max="1" step="0.05" value={cacheTuning.baselineOpacity} oninput={e => oncache({ ...cacheTuning, baselineOpacity: Number(e.currentTarget.value) })} />
    </fieldset>
    <button class="cache" type="button" onclick={onresetcaches}>{tr('Reset cache controls', $language)}</button>
  </details>
  <details><summary>{tr('Map tuning', $language)}</summary>
    <fieldset><legend>Clustering</legend>
      <label for="cluster-mode">Mode<select id="cluster-mode" value={clusterMode} onchange={e => oncluster('mode', e.currentTarget.value)}><option value="auto">{tr('Automatic', $language)}</option><option value="on">{tr('On', $language)}</option><option value="off">{tr('Off', $language)}</option></select></label>
      <label for="cluster-radius">Radius<output>{clusterRadius} px</output></label><input id="cluster-radius" type="range" min="15" max="100" step="5" value={clusterRadius} oninput={e => oncluster('radius', Number(e.currentTarget.value))} />
      <label for="cluster-max-zoom">Cutoff<output>{clusterMaxZoom.toFixed(1)} zoom</output></label><input id="cluster-max-zoom" type="range" min="4" max="14" step="0.5" value={clusterMaxZoom} oninput={e => oncluster('cutoff', Number(e.currentTarget.value))} />
    </fieldset>
    <fieldset><legend>Marks</legend>
      <label class="checkbox" for="v1-pin-mode"><input id="v1-pin-mode" type="checkbox" checked={usePins} onchange={e => onvisual('pins', e.currentTarget.checked)} />Facility pins</label>
      {#if usePins}<label for="pin-scale">{tr('Facility pin size', $language)}<output>{Math.round(pinScale * 100)}%</output></label><input id="pin-scale" type="range" min="0.6" max="1.6" step="0.05" value={pinScale} oninput={e => onvisual('pinScale', Number(e.currentTarget.value))} />
      {:else}<label for="coordinate-radius">Point size<output>{coordinateRadius} px</output></label><input id="coordinate-radius" type="range" min="3" max="12" step="0.5" value={coordinateRadius} oninput={e => onvisual('coordinateRadius', Number(e.currentTarget.value))} />{/if}
      {#if privateReferences}<label for="reference-radius">Display radius<output>{referenceRadius.toFixed(2)} km</output></label><input id="reference-radius" type="range" min="0.25" max="5" step="0.25" value={referenceRadius} oninput={e => onvisual('referenceRadius', Number(e.currentTarget.value))} />
      <label for="reference-opacity">Area opacity<output>{Math.round(referenceOpacity * 100)}%</output></label><input id="reference-opacity" type="range" min="0.02" max="0.35" step="0.01" value={referenceOpacity} oninput={e => onvisual('referenceOpacity', Number(e.currentTarget.value))} />
      <label class="checkbox" for="reference-labels"><input id="reference-labels" type="checkbox" checked={referenceLabels} onchange={e => onvisual('referenceLabels', e.currentTarget.checked)} />Reference labels</label><small>Display aid; does not change source precision.</small>{/if}
    </fieldset>
    <fieldset><legend>Interaction</legend><label for="cluster-zoom-duration">Cluster-click zoom<output>{clusterDuration} ms</output></label><input id="cluster-zoom-duration" type="range" min="0" max="700" step="20" value={clusterDuration} oninput={e => oninteraction('duration', Number(e.currentTarget.value))} />
    <label for="cluster-motion-duration">{tr('Cluster animation', $language)}<output>{clusterMotionDuration} ms</output></label><input id="cluster-motion-duration" type="range" min="0" max="400" step="10" value={clusterMotionDuration} oninput={e => oninteraction('motionDuration', Number(e.currentTarget.value))} />
    <label for="cluster-motion-idle-delay">{tr('Camera idle delay', $language)}<output>{clusterMotionIdleDelay} ms</output></label><input id="cluster-motion-idle-delay" type="range" min="0" max="500" step="25" value={clusterMotionIdleDelay} oninput={e => oninteraction('motionIdleDelay', Number(e.currentTarget.value))} />
    <label for="cluster-motion-limit">{tr('Animation mark limit', $language)}<output>{clusterMotionLimit}</output></label><input id="cluster-motion-limit" type="range" min="50" max="2000" step="50" value={clusterMotionLimit} oninput={e => oninteraction('motionLimit', Number(e.currentTarget.value))} />
    <label for="cluster-rebuild-debounce">Slider rebuild delay<output>{rebuildDelay} ms</output></label><input id="cluster-rebuild-debounce" type="range" min="0" max="500" step="25" value={rebuildDelay} oninput={e => oninteraction('debounce', Number(e.currentTarget.value))} /></fieldset>
  </details>
  <details open><summary>{tr('Layout & density', $language)}</summary><fieldset><legend class="sr-only">{tr('Layout & density', $language)}</legend>
    {#if mobileLayout}
    <label for="debug-sheet-height">{tr('Mobile sheet height', $language)}<output>{layout.mobileSheetPercent ?? 48}%</output></label><input id="debug-sheet-height" type="range" min="35" max="65" step="1" value={layout.mobileSheetPercent ?? 48} oninput={e => onlayout({...layout, mobileSheetPercent: Number(e.currentTarget.value)})} />
    <label for="debug-sheet-expanded">{tr('Expanded sheet height', $language)}<output>{layout.mobileExpandedPercent ?? 90}%</output></label><input id="debug-sheet-expanded" type="range" min="75" max="95" step="1" value={layout.mobileExpandedPercent ?? 90} oninput={e => onlayout({...layout, mobileExpandedPercent: Number(e.currentTarget.value)})} />
    {:else}<label for="debug-panel-width">{tr('Panel width', $language)}<output>{Math.round(layout.panelWidthPercent)}%</output></label><input id="debug-panel-width" type="range" min="25" max="55" step="1" value={layout.panelWidthPercent} oninput={e => onlayout({...layout, panelWidthPercent: Number(e.currentTarget.value)})} />{/if}
    <label for="debug-row-padding">{tr('Result spacing', $language)}<output>{layout.rowPadding} px</output></label><input id="debug-row-padding" type="range" min="10" max="22" step="1" value={layout.rowPadding} oninput={e => onlayout({...layout, rowPadding: Number(e.currentTarget.value)})} />
    <label for="debug-type-scale">{tr('Text size', $language)}<output>{Math.round(layout.typeScale * 100)}%</output></label><input id="debug-type-scale" type="range" min="0.9" max="1.15" step="0.05" value={layout.typeScale} oninput={e => onlayout({...layout, typeScale: Number(e.currentTarget.value)})} />
  </fieldset></details>
</aside>

<style>
  .map-diagnostics { position:absolute;z-index:20;bottom:3.7rem;left:.65rem;width:min(25rem,calc(100% - 1.3rem));max-height:calc(100% - 5rem);overflow:auto;padding:.85rem;border:1px solid var(--line,#565656);background:var(--panel,#181818);color:var(--ink,#f0eee8);font: .75rem/1.45 var(--font-body,system-ui);box-shadow:0 8px 30px #0003;color-scheme:var(--uec-color-scheme,dark); }
  header {display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:.55rem;}header strong{font-size:.9rem;}button{border:1px solid var(--line,#565656);background:transparent;color:inherit;cursor:pointer;min-height:44px;padding:.35rem .6rem;font:inherit;}header button{font-size:1.3rem;width:44px;}.debug-actions{display:flex;flex-wrap:wrap;gap:.4rem;}.debug-actions button{flex:1;font-size:.7rem;}details{border-top:1px solid var(--line,#444);margin-top:.75rem;}summary{cursor:pointer;min-height:44px;align-content:center;font-weight:600;}dl{display:grid;gap:.25rem;margin:0 0 .5rem;}dl div{display:flex;justify-content:space-between;gap:1rem;padding:.2rem 0;}dt{opacity:.72;}dd{margin:0;text-align:right;max-width:65%;overflow-wrap:anywhere;font-variant-numeric:tabular-nums;}fieldset{border:0;margin:.3rem 0 .8rem;padding:0;display:grid;gap:.1rem;}legend{font-weight:600;padding:0;margin-bottom:.4rem;}label{display:flex;justify-content:space-between;align-items:center;gap:.5rem;min-height:32px;}input[type=range]{width:100%;min-height:32px;accent-color:var(--ink,#eee);}select{background:var(--panel,#181818);color:inherit;border:1px solid var(--line,#565656);min-height:44px;padding:.35rem;}.checkbox{justify-content:flex-start;min-height:44px;}.checkbox input{width:18px;height:18px;accent-color:var(--ink,#eee);}small,output{opacity:.75;}.cache{width:100%;}button:hover{background:#8882;}button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid currentColor;outline-offset:3px;}.errors{padding-left:1rem;color:#efb1a9;}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);}
  @media(max-width:40rem){.map-diagnostics{bottom:8.7rem;max-height:calc(100% - 9.5rem);font-size:.75rem;}}
  .cache-controls input[type="range"] { min-height:44px; }
  .cache-controls label { min-height:36px; }
  .cache-controls .checkbox { min-height:44px; }
  .cache-controls fieldset { margin-bottom:1rem; }
  .cache-controls input:disabled { opacity:.4; }
</style>
