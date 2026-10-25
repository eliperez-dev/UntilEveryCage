<script lang="ts">
  import { tick } from "svelte";
  import { language, tr } from './language';
  import ThemeControl from './ThemeControl.svelte';
  let {
    current,
    mapHref,
    databaseHref,
    debugEnabled = false,
    privateTools = false,
    publicReleaseLabel = null,
    releaseDescription = null,
    releaseOptions = [],
    selectedReleaseId = null,
    onreleasechange,
    ondebugchange,
  }: {
    current: "map" | "database" | "api" | "methodology" | "about" | "faq" | "contribute";
    mapHref: string;
    databaseHref: string;
    debugEnabled?: boolean;
    privateTools?: boolean;
    publicReleaseLabel?: string | null;
    releaseDescription?: string | null;
    releaseOptions?: readonly { id: string; label: string }[];
    selectedReleaseId?: string | null;
    onreleasechange?(releaseId: string): void;
    ondebugchange?(enabled: boolean): void;
  } = $props();

  const logo = `${import.meta.env.BASE_URL}assets/icon.png`;
  const context = $derived(mapHref === '#/map' ? '' : `map=${encodeURIComponent(mapHref)}`);
  const aboutHref = $derived(`#/about${context ? `?${context}` : ''}`);
  const faqHref = $derived(`#/faq${context ? `?${context}` : ''}`);
  const contributeHref = $derived(`#/contribute${context ? `?${context}` : ''}`);
  const menuHref = (path: string) => `#/${path}${context ? `?${context}` : ''}`;
  let toolsOpen = $state(false);
  const displayReleaseLabel = (label: string) => label.replaceAll('—', ':');
  const displayedReleaseLabel = $derived(publicReleaseLabel ? displayReleaseLabel(publicReleaseLabel) : 'No verified public release loaded');
  let actionArea = $state<HTMLDivElement>();
  let toolsButton = $state<HTMLButtonElement>();
  function closeTools(returnFocus = false) {
    toolsOpen = false;
    if (returnFocus) void tick().then(() => toolsButton?.focus());
  }
  function toggleTools() { toolsOpen = !toolsOpen; }
</script>

<svelte:window onhashchange={() => closeTools()} onkeydown={(event) => { if (event.key === "Escape" && toolsOpen) { event.preventDefault(); closeTools(true); } }} onclick={(event) => { if (event.target instanceof Node && !actionArea?.contains(event.target)) closeTools(); }} />
<div class="masthead" role="banner">
  <a class="wordmark" href={mapHref} aria-label="Until Every Cage map home">
    <img src={logo} alt="" />
    <span>Until Every Cage</span>
  </a>
  <nav aria-label={tr('Primary', $language)}>
    <a href={mapHref} aria-current={current === "map" ? "page" : undefined}>{tr('Map', $language)}</a>
    <a href={databaseHref} aria-current={current === 'database' ? 'page' : undefined}>{tr('Database', $language)}</a>
    <a href={menuHref('database/api')} aria-current={current === 'api' ? 'page' : undefined}>{tr('API', $language)}</a>
    <span class="nav-separator" aria-hidden="true">|</span>
    <a href={contributeHref} aria-current={current === "contribute" ? "page" : undefined}>{tr('Contribute', $language)}</a>
    <a href={aboutHref} aria-current={current === 'about' || current === 'methodology' ? 'page' : undefined}>{tr('About', $language)}</a>
    <a href={faqHref} aria-current={current === 'faq' ? 'page' : undefined}>{tr('FAQ', $language)}</a>
  </nav>
  <div class="masthead-actions" bind:this={actionArea}>
    <ThemeControl />
    <button bind:this={toolsButton} type="button" class="header-action tools-action" aria-label={tr('Tools', $language)} aria-expanded={toolsOpen} aria-controls="shared-tools-menu" onclick={toggleTools}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg><span>{tr('Tools', $language)}</span>
    </button>
    {#if toolsOpen}<aside id="shared-tools-menu" class="header-menu tools-menu" aria-label={tr('Tools', $language)}>
      <header><strong><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg> {tr('Tools', $language)}</strong><button type="button" aria-label={tr('Close Tools', $language)} onclick={() => closeTools(true)}>×</button></header>
      <section><label for="language-choice">{tr('Language', $language)}</label><select id="language-choice" aria-label={tr('Language', $language)} value={$language} onchange={event => language.set(event.currentTarget.value === 'es' ? 'es' : 'en')}><option value="en">English</option><option value="es">Español</option></select></section>
      <section><label for="release-choice">{tr('Current release', $language)}</label><select id="release-choice" aria-label={tr('Current release', $language)} title={displayedReleaseLabel} value={selectedReleaseId ?? ''} disabled={!releaseOptions.length || !onreleasechange} onchange={event => onreleasechange?.(event.currentTarget.value)}>{#if selectedReleaseId && !releaseOptions.some(release => release.id === selectedReleaseId)}<option value={selectedReleaseId} disabled>{tr('Selected release unavailable', $language)}</option>{/if}{#if releaseOptions.length}{#each releaseOptions as release}<option value={release.id}>{displayReleaseLabel(release.label)}</option>{/each}{:else}<option value="">{displayedReleaseLabel}</option>{/if}</select><small>{releaseDescription ?? (publicReleaseLabel ? 'Release metadata from the active public map.' : 'Release selection is available from the map.')}</small></section>
      <section><h2>{tr('History', $language)}</h2><p>{tr('Open a record to view its available release history.', $language)}</p><small>{tr('Historical views follow current privacy restrictions.', $language)}</small></section>
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
    gap: 1.25rem;
    min-height: 4rem;
    padding: 0.5rem clamp(1rem, 3vw, 3.2rem);
    border-bottom: 1px solid #3d4740;
    background: #141916;
    color: #f1efe8;
  }
  .wordmark {
    display: flex;
    align-items: center;
    gap: 0.58rem;
    min-width: 0;
    color: inherit;
    font: 600 1rem Georgia, serif;
    text-decoration: none;
    white-space: nowrap;
  }
  .wordmark img { width: 2rem; height: 2rem; }
  nav { display: flex; align-items:center; justify-content:center; justify-self:center; gap: 1rem; font: 0.77rem ui-sans-serif, system-ui, sans-serif; }
  nav a { color: #aeb9af; text-decoration: none; }
  nav .nav-separator{color:#657067;font-size:.72rem;user-select:none}
  nav a[aria-current] { color: #f1efe8; text-decoration: underline; text-underline-offset: 0.35rem; }
  .masthead-actions { position:relative; justify-self:end; display:flex; align-items:center; gap:.4rem; font-family:system-ui,sans-serif; }
  .header-action { display:flex; align-items:center; justify-content:center; gap:.4rem; min-height:2.1rem; padding:.3rem .45rem; border:1px solid #536158; background:#1a201c; color:#f1efe8; cursor:pointer; font:650 .68rem system-ui; }
  .header-action svg, .header-menu svg { width:1rem; height:1rem; flex:none; fill:none; stroke:currentColor; stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; }
  .header-menu { position:absolute; z-index:30; top:calc(100% + .65rem); right:0; width:min(19rem, calc(100vw - 1rem)); border:1px solid #536158; background:#171a18; color:#f1efe8; box-shadow:0 .7rem 1.5rem #0009; }
  .header-menu header { display:flex; align-items:center; justify-content:space-between; min-height:2.5rem; padding:.45rem .7rem; border-bottom:1px solid #48504b; }
  .header-menu header strong { display:flex; align-items:center; gap:.45rem; font-size:.77rem; }
  .header-menu header button { border:0; background:none; color:#f1efe8; cursor:pointer; font-size:1.2rem; }
  .header-menu section { display:grid; gap:.35rem; padding:.7rem; border-bottom:1px solid #343a36; }
  .header-menu label, .header-menu h2 { margin:0; font-size:.7rem; font-weight:650; }
  .header-menu .toggle { display:flex; align-items:center; gap:.55rem; min-height:2rem; cursor:pointer; }
  .header-menu p, .header-menu small { margin:0; color:#b9c2b9; font-size:.64rem; line-height:1.4; }
  .tools-menu select { width:100%; max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  a:focus-visible, button:focus-visible, select:focus-visible { outline:2px solid #eee7d6; outline-offset:2px; }
  @media (any-pointer:coarse) {
    nav > a{display:flex;align-items:center;min-height:2.75rem}
  }
  @media (max-width: 60rem) {
    .masthead{grid-template-columns:minmax(0,1fr) auto;gap:.35rem 1rem;padding:.55rem 1rem}
    nav{grid-column:1 / -1;grid-row:2;justify-content:center;gap:1rem}
    .masthead-actions{grid-column:2;grid-row:1}
  }
  @media (max-width: 50rem) {
    .masthead { gap: 0.7rem; padding-inline: 0.75rem; }
    .masthead { grid-template-columns:minmax(0,1fr) auto; }
  }
  @media (max-width: 25rem) {
    .masthead { min-height:0; gap:.35rem .65rem; }
    .wordmark{font-size:.9rem}.wordmark img{width:1.6rem;height:1.6rem}
    .masthead-actions { grid-column:2; grid-row:1; }
    .tools-action span { display:none; }
    .masthead-actions { gap:.25rem; }
    nav { grid-row:2; gap:.55rem; }
  }
</style>
