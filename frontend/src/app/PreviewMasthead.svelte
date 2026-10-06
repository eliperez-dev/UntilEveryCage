<script lang="ts">
  import { tick } from "svelte";
  let {
    current,
    mapHref,
    databaseHref,
    debugEnabled = false,
    privateTools = false,
    ondebugchange,
  }: {
    current: "map" | "database" | "methodology" | "about" | "contribute";
    mapHref: string;
    databaseHref: string;
    debugEnabled?: boolean;
    privateTools?: boolean;
    ondebugchange?(enabled: boolean): void;
  } = $props();

  const logo = `${import.meta.env.BASE_URL}assets/icon.png`;
  const context = $derived(mapHref === '#/map' ? '' : `map=${encodeURIComponent(mapHref)}`);
  const aboutHref = $derived(`#/about${context ? `?${context}` : ''}`);
  const contributeHref = $derived(`#/contribute${context ? `?${context}` : ''}`);
  const menuHref = (path: string) => `#/${path}${context ? `?${context}` : ''}`;
  let navOpen = $state<'about' | 'database' | null>(null);
  let navArea: HTMLElement;
  let aboutButton: HTMLButtonElement;
  let databaseButton: HTMLButtonElement;
  function toggleNav(menu: 'about' | 'database', focusFirst = false) {
    const next = focusFirst || navOpen !== menu; closeMenus(); navOpen = next ? menu : null;
    if (next && focusFirst) void tick().then(() => navArea?.querySelector<HTMLAnchorElement>(`#shared-${menu}-nav a`)?.focus());
  }
  let toolsOpen = $state(false);
  let releaseOpen = $state(false);
  let actionArea = $state<HTMLDivElement>();
  let toolsButton = $state<HTMLButtonElement>();
  let releaseButton = $state<HTMLButtonElement>();
  function closeMenus(returnFocus: "release" | "tools" | "about" | "database" | null = null) {
    navOpen = null;
    releaseOpen = false;
    toolsOpen = false;
    if (returnFocus) void tick().then(() => (returnFocus === "release" ? releaseButton : returnFocus === "tools" ? toolsButton : returnFocus === "database" ? databaseButton : aboutButton)?.focus());
  }
  function toggleRelease() { navOpen = null; toolsOpen = false; releaseOpen = !releaseOpen; }
  function toggleTools() { navOpen = null; releaseOpen = false; toolsOpen = !toolsOpen; }
</script>

<svelte:window onhashchange={() => closeMenus()} onkeydown={(event) => { if (event.key === "Escape" && (navOpen || releaseOpen || toolsOpen)) { event.preventDefault(); closeMenus(navOpen ?? (releaseOpen ? "release" : toolsOpen ? "tools" : "tools")); } }} onclick={(event) => { if (event.target instanceof Node && !actionArea?.contains(event.target) && !navArea?.contains(event.target)) closeMenus(); }} />
<header class="masthead">
  <a class="wordmark" href={mapHref} aria-label="Until Every Cage map home">
    <img src={logo} alt="" />
    <span>Until Every Cage</span>
  </a>
  <nav aria-label="Primary" bind:this={navArea}>
    <a href={mapHref} aria-current={current === "map" ? "page" : undefined}>Map</a>
    <div class="nav-group">
      <button bind:this={databaseButton} class="about-control" type="button" aria-current={current === 'database' ? 'page' : undefined} aria-expanded={navOpen === 'database'} aria-controls="shared-database-nav" onclick={() => toggleNav('database')} onkeydown={(event) => { if (event.key === 'ArrowDown') { event.preventDefault(); toggleNav('database', true); } }}>Database</button>
      {#if navOpen === 'database'}<div id="shared-database-nav" class="nav-dropdown" aria-label="Database destinations"><a href={databaseHref}>Browse records</a><a href={menuHref('database/downloads')}>Downloads</a><a href={menuHref('database/api')}>API documentation</a></div>{/if}
    </div>
    <a class="secondary-link" href={contributeHref} aria-current={current === "contribute" ? "page" : undefined}>Contribute</a>
    <div class="nav-group">
      <button bind:this={aboutButton} class="about-control" type="button" aria-current={current === "about" || current === "methodology" ? 'page' : undefined} aria-expanded={navOpen === 'about'} aria-controls="shared-about-nav" onclick={() => toggleNav('about')} onkeydown={(event) => { if (event.key === 'ArrowDown') { event.preventDefault(); toggleNav('about', true); } }}>About</button>
      {#if navOpen === 'about'}<div id="shared-about-nav" class="nav-dropdown about-dropdown" aria-label="About destinations">
        <a href={aboutHref}>Overview</a><a href={menuHref('about/sources')}>Sources & methodology</a><a href={menuHref('about/faq')}>FAQ</a><a href={menuHref('about/help')}>Help</a>
      </div>{/if}
    </div>
  </nav>
  {#if privateTools}<div class="masthead-actions" bind:this={actionArea}>
    <button bind:this={releaseButton} type="button" class="header-action preview-action" aria-expanded={releaseOpen} aria-controls="shared-release-menu" onclick={toggleRelease}>Preview</button>
    <button bind:this={toolsButton} type="button" class="header-action tools-action" aria-expanded={toolsOpen} aria-controls="shared-tools-menu" onclick={toggleTools}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg><span>Tools</span>
    </button>
    {#if releaseOpen}<aside id="shared-release-menu" class="header-menu release-menu" aria-label="Preview release">
      <header><strong>Preview release</strong><button type="button" aria-label="Close Preview release" onclick={() => closeMenus("release")}>×</button></header>
      <section><label for="release-choice">Current release</label><select id="release-choice" aria-label="Current release"><option>Private development preview</option><option disabled>v0 · planned, not available</option></select><small>Not publication-approved.</small></section>
      <section><h2>History</h2><p>No previous releases available.</p><small>Historical views will respect current privacy restrictions.</small></section>
    </aside>{/if}
    {#if toolsOpen}<aside id="shared-tools-menu" class="header-menu tools-menu" aria-label="Tools">
      <header><strong><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg> Map tools</strong><button type="button" aria-label="Close Tools" onclick={() => closeMenus("tools")}>×</button></header>
      <section><label class="toggle"><input type="checkbox" checked={debugEnabled} onchange={(event) => ondebugchange?.(event.currentTarget.checked)} /> Enable debug menu</label><small>Local development controls and diagnostics.</small></section>
    </aside>{/if}
  </div>{/if}
</header>

<style>
  .masthead {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
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
  nav { display: flex; align-items:center; gap: 1rem; font: 0.77rem ui-sans-serif, system-ui, sans-serif; }
  nav a { color: #aeb9af; text-decoration: none; }
  nav a[aria-current] { color: #f1efe8; text-decoration: underline; text-underline-offset: 0.35rem; }
  nav .secondary-link { margin-left:.2rem; padding-left:1rem; border-left:1px solid #48524a; }
  .nav-group{position:relative;display:flex;align-items:center;gap:.1rem}
  .about-control{display:flex;align-items:center;min-height:2rem;padding:0;border:0;background:transparent;color:#aeb9af;cursor:pointer;font:inherit}
  .about-control:hover,.about-control[aria-expanded="true"]{color:#fff}
  .about-control[aria-current]{color:#f1efe8;text-decoration:underline;text-underline-offset:.35rem}
  .nav-dropdown{position:absolute;z-index:50;top:calc(100% + .5rem);left:0;display:grid;width:13rem;max-width:calc(100vw - 2rem);padding:.35rem;border:1px solid #536158;background:#171a18;box-shadow:0 .5rem 1rem #0007}
  .nav-dropdown a{display:flex;align-items:center;min-height:2.35rem;padding:.4rem .6rem;color:#eee9df;font-size:.82rem;text-decoration:none}
  .nav-dropdown a:hover{background:#2a332c}.about-dropdown{left:auto;right:0;width:14rem}
  .masthead-actions { position:relative; justify-self:end; display:flex; align-items:center; gap:.4rem; font-family:system-ui,sans-serif; }
  .header-action { display:flex; align-items:center; justify-content:center; gap:.4rem; min-height:2.1rem; padding:.3rem .45rem; border:1px solid #536158; background:#1a201c; color:#f1efe8; cursor:pointer; font:650 .68rem system-ui; }
  .preview-action { color:#c7d0c7; font-weight:600; }
  .header-action svg, .header-menu svg { width:1rem; height:1rem; flex:none; fill:none; stroke:currentColor; stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; }
  .header-menu { position:absolute; z-index:30; top:calc(100% + .65rem); right:0; width:min(19rem, calc(100vw - 1rem)); border:1px solid #536158; background:#171a18; color:#f1efe8; box-shadow:0 .7rem 1.5rem #0009; }
  .header-menu header { display:flex; align-items:center; justify-content:space-between; min-height:2.5rem; padding:.45rem .7rem; border-bottom:1px solid #48504b; }
  .header-menu header strong { display:flex; align-items:center; gap:.45rem; font-size:.77rem; }
  .header-menu header button { border:0; background:none; color:#f1efe8; cursor:pointer; font-size:1.2rem; }
  .header-menu section { display:grid; gap:.35rem; padding:.7rem; border-bottom:1px solid #343a36; }
  .header-menu label, .header-menu h2 { margin:0; font-size:.7rem; font-weight:650; }
  .header-menu .toggle { display:flex; align-items:center; gap:.55rem; min-height:2rem; cursor:pointer; }
  .header-menu p, .header-menu small { margin:0; color:#b9c2b9; font-size:.64rem; line-height:1.4; }
  a:focus-visible, button:focus-visible, select:focus-visible { outline:2px solid #eee7d6; outline-offset:2px; }
  @media (max-width: 60rem) {
    .masthead{grid-template-columns:minmax(0,1fr) auto;gap:.35rem 1rem;padding:.55rem 1rem}
    nav{grid-column:1 / -1;grid-row:2;justify-content:center;gap:1.2rem}
    .masthead-actions{grid-column:2;grid-row:1}
  }
  @media (max-width: 50rem) {
    .masthead { gap: 0.7rem; padding-inline: 0.75rem; }
    .masthead { grid-template-columns:minmax(0,1fr) auto; }
  }
  @media (max-width: 25rem) {
    .wordmark{font-size:.9rem}.wordmark img{width:1.6rem;height:1.6rem}
    .masthead { min-height: 3.9rem; }
    .preview-action, .tools-action span { display:none; }
    .masthead-actions { gap:.25rem; }
    nav { gap:.65rem; }
    nav .secondary-link { margin-left:0; padding-left:.5rem; }
  }
</style>
