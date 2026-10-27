<script lang="ts">
  import { tick } from "svelte";
  import type { MapDisplaySettings } from '../design-lab/contract';
  import { language, tr, LANGUAGE_OPTIONS, languageLoadState, selectLanguage, type Language } from './language';
  import ThemeControl from './ThemeControl.svelte';
  let {
    current,
    mapHref,
    debugEnabled = false,
    privateTools = false,
    publicReleaseLabel = null,
    releaseDescription = null,
    releaseOptions = [],
    selectedReleaseId = null,
    onreleasechange,
    ondebugchange,
    mapControlsReady = false,
    mapDisplaySettings = null,
    onmapdisplaychange,
  }: {
    current: "landing" | "map" | "database" | "api" | "methodology" | "about" | "faq" | "contribute";
    mapHref: string;
    databaseHref?: string;
    debugEnabled?: boolean;
    privateTools?: boolean;
    publicReleaseLabel?: string | null;
    releaseDescription?: string | null;
    releaseOptions?: readonly { id: string; label: string }[];
    selectedReleaseId?: string | null;
    onreleasechange?(releaseId: string): void;
    ondebugchange?(enabled: boolean): void;
    mapControlsReady?: boolean;
    mapDisplaySettings?: MapDisplaySettings | null;
    onmapdisplaychange?(patch: Partial<MapDisplaySettings>): void;
  } = $props();

  const logo = `${import.meta.env.BASE_URL}assets/icon.png`;
  const context = $derived(mapHref === '#/map' ? '' : `map=${encodeURIComponent(mapHref)}`);
  const aboutHref = $derived(`#/about${context ? `?${context}` : ''}`);
  const contributeHref = $derived(`#/contribute${context ? `?${context}` : ''}`);
  const menuHref = (path: string) => `#/${path}${context ? `?${context}` : ''}`;
  let toolsOpen = $state(false);
  let languageOpen = $state(false);
  let languageButton = $state<HTMLButtonElement>();
  let languageMenu = $state<HTMLElement>();
  const displayReleaseLabel = (label: string) => label.replaceAll('—', ':');
  const displayedReleaseLabel = $derived(publicReleaseLabel ? displayReleaseLabel(publicReleaseLabel) : 'No verified public release loaded');
  let actionArea = $state<HTMLDivElement>();
  let toolsButton = $state<HTMLButtonElement>();
  function closeTools(returnFocus = false) {
    toolsOpen = false;
    if (returnFocus) void tick().then(() => toolsButton?.focus());
  }
  function toggleTools(event: MouseEvent) {
    event.stopPropagation();
    languageOpen = false;
    toolsOpen = !toolsOpen;
  }
  function closeLanguages(returnFocus = false) {
    languageOpen = false;
    if (returnFocus) void tick().then(() => languageButton?.focus());
  }
  function toggleLanguages(event: MouseEvent) {
    event.stopPropagation();
    closeTools();
    languageOpen = !languageOpen;
    if (languageOpen) void tick().then(() => languageMenu?.querySelector<HTMLButtonElement>('[aria-pressed="true"]')?.focus());
  }
  async function chooseLanguage(value: Language) {
    if (await selectLanguage(value) && languageOpen) closeLanguages(true);
  }
  const sizeLabel = $derived(mapDisplaySettings?.optimizedPins ? 'Dot size' : 'Icon size');
  const sizeValue = $derived(mapDisplaySettings?.optimizedPins ? mapDisplaySettings.coordinateRadius : mapDisplaySettings?.pinScale ?? .8);
  const sizeText = $derived(mapDisplaySettings?.optimizedPins ? `${new Intl.NumberFormat($language, { maximumFractionDigits: 1 }).format(sizeValue)} px` : `${Math.round(sizeValue * 100)}%`);
  function resizePins(value: string) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || !mapDisplaySettings) return;
    onmapdisplaychange?.(mapDisplaySettings.optimizedPins ? { coordinateRadius: Math.max(3, Math.min(12, parsed)) } : { pinScale: Math.max(.6, Math.min(1.6, parsed)) });
  }
</script>

<svelte:window onhashchange={() => { closeTools(); closeLanguages(); }} onkeydown={(event) => { if (event.key === 'Escape') { if (languageOpen) { event.preventDefault(); closeLanguages(true); } else if (toolsOpen) { event.preventDefault(); closeTools(true); } } }} onclick={(event) => { if (event.target instanceof Node) { if (!actionArea?.contains(event.target)) closeTools(); if (!languageMenu?.contains(event.target) && !languageButton?.contains(event.target)) closeLanguages(); } }} />
<div class="masthead" role="banner" style:z-index={toolsOpen || languageOpen ? 20 : undefined}>
  <a class="wordmark" href="#/" aria-label={tr('Until Every Cage home', $language)}>
    <img src={logo} alt="" />
    <span>Until Every Cage</span>
  </a>
  <nav aria-label={tr('Primary', $language)}>
    <a href={mapHref} aria-current={current === "map" ? "page" : undefined}>{tr('Map', $language)}</a>
    <a href={menuHref('database/api')} aria-current={current === 'api' ? 'page' : undefined}>{tr('Data', $language)}</a>
    <span class="nav-separator" aria-hidden="true"></span>
    <a href={contributeHref} aria-current={current === "contribute" ? "page" : undefined}>{tr('Contribute', $language)}</a>
    <a href={aboutHref} aria-current={current === 'about' || current === 'methodology' ? 'page' : undefined}>{tr('About', $language)}</a>
  </nav>
  <div class="masthead-actions" bind:this={actionArea}>
    <ThemeControl />
    <button bind:this={languageButton} type="button" class="header-action language-action" aria-label={tr('Language', $language)} aria-expanded={languageOpen} aria-controls="shared-language-menu" onclick={toggleLanguages}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 8 6 6M4 5h12M10 3v2M13 5c-1 6-5 10-9 12m11 4 4-10 4 10m-7-3h6" /></svg>
    </button>
    <button bind:this={toolsButton} type="button" class="header-action tools-action" aria-label={tr('More tools', $language)} title={tr('More tools', $language)} aria-expanded={toolsOpen} aria-controls="shared-tools-menu" onclick={toggleTools}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg><span>{tr('More tools', $language)}</span>
    </button>
    {#if languageOpen}<div bind:this={languageMenu} id="shared-language-menu" class="header-menu language-menu" role="dialog" tabindex="-1" aria-label={tr('Language', $language)} aria-busy={$languageLoadState.state === 'loading'}>
      <header><strong>{tr('Language', $language)}</strong><button type="button" aria-label={tr('Close', $language)} onclick={() => closeLanguages(true)}>×</button></header>
      <div class="language-options">{#each LANGUAGE_OPTIONS as option}<button type="button" lang={option.code} aria-pressed={$language === option.code} onclick={() => void chooseLanguage(option.code)}><span>{option.name}</span><span aria-hidden="true">{$language === option.code ? '✓' : ''}</span></button>{/each}</div>
      {#if $languageLoadState.state === 'loading'}<p role="status">{tr('Loading…', $language)}</p>{:else if $languageLoadState.state === 'failed'}<div class="language-error"><p role="alert">{tr('Language could not be loaded.', $language)}</p><button type="button" onclick={() => void chooseLanguage($languageLoadState.requested)}>{tr('Retry', $language)}</button></div>{/if}
    </div>{/if}
    {#if toolsOpen}<aside id="shared-tools-menu" class="header-menu tools-menu" aria-label={tr('More tools', $language)}>
      <header><strong><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg> {tr('More tools', $language)}</strong><button type="button" aria-label={tr('Close more tools', $language)} onclick={() => closeTools(true)}>×</button></header>
      {#if current === 'map' && mapDisplaySettings && onmapdisplaychange}<section class="map-display-tools" role="group" aria-label={tr('Map display', $language)}>
        <h2>{tr('Map display', $language)}</h2>
        <label for="map-clustering-choice">{tr('Clustering', $language)}</label>
        <select id="map-clustering-choice" disabled={!mapControlsReady} value={mapDisplaySettings.clusterMode} onchange={event => onmapdisplaychange?.({ clusterMode: event.currentTarget.value as MapDisplaySettings['clusterMode'] })}><option value="auto">{tr('Automatic', $language)}</option><option value="on">{tr('On', $language)}</option><option value="off">{tr('Off', $language)}</option></select>
        <label class="toggle"><input type="checkbox" checked={mapDisplaySettings.optimizedPins} disabled={!mapControlsReady} onchange={event => onmapdisplaychange?.({ optimizedPins: event.currentTarget.checked })} />{tr('Use optimized pins', $language)}</label>
        <label class="size-label" for="map-pin-size"><span>{tr(sizeLabel, $language)}</span><output for="map-pin-size">{sizeText}</output></label>
        <input id="map-pin-size" type="range" aria-label={tr(sizeLabel, $language)} aria-valuetext={sizeText} disabled={!mapControlsReady} min={mapDisplaySettings.optimizedPins ? 3 : .6} max={mapDisplaySettings.optimizedPins ? 12 : 1.6} step={mapDisplaySettings.optimizedPins ? .5 : .05} value={sizeValue} oninput={event => resizePins(event.currentTarget.value)} />
      </section>{/if}
      <section><label for="release-choice">{tr('Current release', $language)}</label><select id="release-choice" aria-label={tr('Current release', $language)} title={displayedReleaseLabel} value={selectedReleaseId ?? ''} disabled={!releaseOptions.length || !onreleasechange} onchange={event => onreleasechange?.(event.currentTarget.value)}>{#if selectedReleaseId && !releaseOptions.some(release => release.id === selectedReleaseId)}<option value={selectedReleaseId} disabled>{tr('Selected release unavailable', $language)}</option>{/if}{#if releaseOptions.length}{#each releaseOptions as release}<option value={release.id}>{displayReleaseLabel(release.label)}</option>{/each}{:else}<option value="">{tr(displayedReleaseLabel, $language)}</option>{/if}</select><small>{tr(releaseDescription ?? (publicReleaseLabel ? 'Release metadata from the active public map.' : 'Release selection is available from the map.'), $language)}</small></section>
      {#if current === 'map'}<section><label class="toggle"><input type="checkbox" checked={debugEnabled} onchange={(event) => ondebugchange?.(event.currentTarget.checked)} /> {tr('Enable debug menu', $language)}</label><small>{tr('Map diagnostics and rendering controls.', $language)}</small></section>{/if}
    </aside>{/if}
  </div>
</div>

<style>
  .masthead {
    position: relative;
    z-index: 20;
    display: grid;
    grid-template-columns: minmax(0, 1fr) max-content minmax(0, 1fr);
    align-items: center;
    flex: none;
    gap: 1.375rem;
    min-height: 4.5rem;
    padding: .75rem 1.5rem;
    border-bottom: 1px solid var(--ui-line);
    background: var(--ui-surface);
    color: var(--ui-ink);
  }
  .wordmark {
    display: flex;
    align-items: center;
    gap: .5625rem;
    min-width: 0;
    color: inherit;
    font: 400 1.25rem/1.1 Georgia, serif;
    letter-spacing: -.025em;
    text-decoration: none;
    white-space: nowrap;
  }
  .wordmark img { width: 1.875rem; height: 1.875rem; flex: none; object-fit: contain; }
  nav { display: flex; align-items:center; justify-content:center; justify-self:center; gap: 1.25rem; font: .75rem/1.4 system-ui, sans-serif; }
  nav a { display:flex; align-items:center; min-height:2.75rem; color:var(--ui-muted); text-decoration:none; white-space:nowrap; }
  nav a:hover { color:var(--ui-ink); }
  nav .nav-separator { width:1px; height:.75rem; margin:0 -.5rem; background:var(--ui-line); }
  nav a[aria-current] { color:var(--ui-ink); font-weight:500; text-decoration:underline; text-decoration-thickness:1px; text-underline-offset:.625rem; }
  .masthead-actions { position:relative; justify-self:end; display:flex; align-items:center; gap:.3125rem; font-family:system-ui,sans-serif; }
  .header-action { display:flex; align-items:center; justify-content:center; gap:.5625rem; min-height:2.75rem; padding:.5rem .5625rem; border:1px solid transparent; border-radius:0; background:transparent; color:inherit; cursor:pointer; font:400 .75rem/1.4 system-ui,sans-serif; }
  .header-action:hover, .header-action[aria-expanded="true"] { background:var(--ui-hover); }
  .language-action { width:2.75rem; flex:none; padding:.5rem; }
  .language-menu { width:min(15rem,calc(100vw - 1.5rem)); }
  .language-options { display:grid; padding:.35rem; }
  .language-options button { min-height:2.75rem; display:flex; align-items:center; justify-content:space-between; gap:.75rem; width:100%; padding:.6rem .75rem; border:1px solid transparent; border-radius:0; color:inherit; background:transparent; font:400 .875rem/1.4 system-ui,sans-serif; text-align:left; cursor:pointer; }
  .language-options button:hover { background:var(--ui-hover); }
  .language-options button[aria-pressed=true] { background:var(--ui-selected); border-color:var(--ui-line); }
  .language-menu>p,.language-error { margin:0; padding:.6rem 1rem; font-size:.8rem; }
  .language-error p { margin:0 0 .4rem; }
  .language-error button { min-height:2.75rem; padding:.5rem .75rem; background:transparent; color:inherit; border:1px solid var(--ui-line); font:inherit; cursor:pointer; }
  .header-action svg, .header-menu svg { width:1.0625rem; height:1.0625rem; flex:none; fill:none; stroke:currentColor; stroke-width:1.5; stroke-linecap:round; stroke-linejoin:round; }
  .header-menu { position:absolute; z-index:30; top:calc(100% + .5rem); right:0; width:min(19rem, calc(100vw - 1.5rem)); max-height:calc(100dvh - 5.5rem); overflow:auto; overscroll-behavior:contain; border:1px solid var(--ui-line); background:var(--ui-raised); color:var(--ui-ink); box-shadow:0 .5rem 1.25rem #0002; }
  .header-menu header { display:flex; align-items:center; justify-content:space-between; min-height:3rem; padding:.25rem .75rem .25rem 1rem; border-bottom:1px solid var(--ui-line); }
  .header-menu header strong { display:flex; align-items:center; gap:.5rem; font-size:.8125rem; font-weight:500; }
  .header-menu header button { display:grid; place-items:center; min-width:2.75rem; min-height:2.75rem; padding:0; border:0; border-radius:0; background:transparent; color:inherit; cursor:pointer; font:400 1.35rem/1 system-ui,sans-serif; }
  .header-menu header button:hover { background:var(--ui-hover); }
  .header-menu section { display:grid; gap:.5rem; padding:1rem; border-bottom:1px solid var(--ui-line); }
  .header-menu section:last-child { border-bottom:0; }
  .header-menu label, .header-menu h2 { margin:0; font-size:.75rem; line-height:1.4; font-weight:500; }
  .header-menu .toggle { display:flex; align-items:center; gap:.625rem; min-height:2.75rem; cursor:pointer; }
  .toggle input { width:1rem; height:1rem; margin:0; accent-color:var(--ui-ink); }
  .header-menu small { margin:0; color:var(--ui-muted); font-size:.6875rem; line-height:1.5; }
  .tools-menu select { width:100%; max-width:100%; min-height:2.75rem; padding:.5rem .625rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; border:1px solid var(--ui-line); border-radius:0; background:var(--ui-raised); color:var(--ui-ink); font:.75rem/1.4 system-ui,sans-serif; }
  .map-display-tools .size-label { display:flex; justify-content:space-between; align-items:center; gap:1rem; }
  .size-label output { font-variant-numeric:tabular-nums; color:var(--ui-muted); }
  .map-display-tools input[type=range] { width:100%; min-width:0; min-height:2.75rem; margin:0; accent-color:var(--ui-ink); cursor:pointer; }
  .tools-menu :is(select,input):disabled { opacity:.58; cursor:default; }
  a:focus-visible, button:focus-visible, select:focus-visible, input:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
  @media (max-width: 60rem) {
    .masthead { grid-template-columns:minmax(0,1fr) auto; gap:.1875rem 1rem; padding:.5rem 1rem; }
    nav { grid-column:1 / -1; grid-row:2; width:100%; justify-content:center; gap:1.25rem; }
    .masthead-actions { grid-column:2; grid-row:1; }
    .header-menu { max-height:calc(100dvh - 4.75rem); }
  }
  @media (max-width: 38rem) {
    .masthead { padding:.5rem 1rem .25rem; }
    nav { justify-content:space-between; gap:.5rem; font-size:.6875rem; }
    nav .nav-separator { display:none; }
    .wordmark { font-size:1.125rem; }
    .wordmark img { width:1.6875rem; height:1.6875rem; }
    .tools-menu select { font-size:1rem; }
  }
  @media (max-width: 25rem) {
    .masthead { gap:.1875rem .5rem; padding-inline:.75rem; }
    .tools-action span { display:none; }
    .tools-action { width:2.75rem; padding:0; }
    .masthead-actions { gap:.25rem; }
    nav { font-size:.65625rem; gap:.375rem; }
  }
  @media (max-width: 22rem) {
    .masthead { column-gap:.25rem; }
    .wordmark { font-size:.875rem; gap:.375rem; }
    .wordmark img { width:1.375rem; height:1.375rem; }
    .masthead-actions { gap:0; }
    nav { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:0 .375rem; }
    nav a { justify-content:center; text-align:center; white-space:normal; }
  }
</style>
