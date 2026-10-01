<script lang="ts">
  import { tick } from "svelte";
  let {
    current,
    mapHref,
    databaseHref,
    debugEnabled = false,
    ondebugchange,
  }: {
    current: "map" | "database" | "methodology";
    mapHref: string;
    databaseHref: string;
    debugEnabled?: boolean;
    ondebugchange?(enabled: boolean): void;
  } = $props();

  const logo = `${import.meta.env.BASE_URL}assets/icon.png`;
  const methodologyHref = $derived(`#/methodology?map=${encodeURIComponent(mapHref)}`);
  let toolsOpen = $state(false);
  let releaseOpen = $state(false);
  let accountOpen = $state(false);
  let actionArea: HTMLDivElement;
  let toolsButton: HTMLButtonElement;
  let accountButton: HTMLButtonElement;
  let releaseButton: HTMLButtonElement;
  function closeMenus(returnFocus: "release" | "tools" | "account" | null = null) {
    releaseOpen = false;
    toolsOpen = false;
    accountOpen = false;
    if (returnFocus) void tick().then(() => (returnFocus === "release" ? releaseButton : returnFocus === "tools" ? toolsButton : accountButton)?.focus());
  }
  function toggleRelease() { toolsOpen = false; accountOpen = false; releaseOpen = !releaseOpen; }
  function toggleTools() { releaseOpen = false; accountOpen = false; toolsOpen = !toolsOpen; }
  function toggleAccount() { releaseOpen = false; toolsOpen = false; accountOpen = !accountOpen; }
</script>

<svelte:window onkeydown={(event) => { if (event.key === "Escape" && (releaseOpen || toolsOpen || accountOpen)) { event.preventDefault(); closeMenus(releaseOpen ? "release" : toolsOpen ? "tools" : "account"); } }} onclick={(event) => { if ((releaseOpen || toolsOpen || accountOpen) && event.target instanceof Node && !actionArea?.contains(event.target)) closeMenus(); }} />
<header class="masthead">
  <a class="wordmark" href={mapHref} aria-label="Until Every Cage map home">
    <img src={logo} alt="" />
    <span>Until Every Cage</span>
  </a>
  <nav aria-label="Primary">
    <a href={mapHref} aria-current={current === "map" ? "page" : undefined}>Map</a>
    <a href={databaseHref} aria-current={current === "database" ? "page" : undefined}>Database</a>
    <a class="secondary-link" href={methodologyHref} aria-current={current === "methodology" ? "page" : undefined}>Methodology</a>
  </nav>
  <div class="masthead-actions" bind:this={actionArea}>
    <button bind:this={releaseButton} type="button" class="header-action preview-action" aria-expanded={releaseOpen} aria-controls="shared-release-menu" onclick={toggleRelease}>Preview</button>
    <button bind:this={toolsButton} type="button" class="header-action tools-action" aria-expanded={toolsOpen} aria-controls="shared-tools-menu" onclick={toggleTools}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg><span>Tools</span>
    </button>
    <button bind:this={accountButton} type="button" class="header-action account-action" aria-label="Account menu" aria-expanded={accountOpen} aria-controls="shared-account-menu" onclick={toggleAccount}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M4.5 20c.4-4.1 3-6.3 7.5-6.3s7.1 2.2 7.5 6.3"/></svg>
    </button>
    {#if releaseOpen}<aside id="shared-release-menu" class="header-menu release-menu" aria-label="Preview release">
      <header><strong>Preview release</strong><button type="button" aria-label="Close Preview release" onclick={() => closeMenus("release")}>×</button></header>
      <section><label for="release-choice">Current release</label><select id="release-choice" aria-label="Current release"><option>Private development preview</option><option disabled>v0 · planned, not available</option></select><small>Not publication-approved.</small></section>
      <section><h2>History</h2><p>No previous releases available.</p><small>Historical views will respect current privacy restrictions.</small></section>
    </aside>{/if}
    {#if toolsOpen}<aside id="shared-tools-menu" class="header-menu tools-menu" aria-label="Tools">
      <header><strong><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg> Map tools</strong><button type="button" aria-label="Close Tools" onclick={() => closeMenus("tools")}>×</button></header>
      <section><label class="toggle"><input type="checkbox" checked={debugEnabled} onchange={(event) => ondebugchange?.(event.currentTarget.checked)} /> Enable debug menu</label><small>Local development controls and diagnostics.</small></section>
      <section><button type="button" disabled><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v18M3 12h18"/></svg>Add a location · planned</button><small>Submissions require review before appearing on the map.</small></section>
    </aside>{/if}
    {#if accountOpen}<aside id="shared-account-menu" class="header-menu account-menu" aria-label="Account">
      <header><strong>Account</strong><button type="button" aria-label="Close Account" onclick={() => closeMenus("account")}>×</button></header>
      <section><p>No account is connected.</p><button type="button" disabled>Sign in · planned</button></section>
    </aside>{/if}
  </div>
</header>

<style>
  .masthead {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
    align-items: center;
    gap: 1.25rem;
    min-height: 4.8rem;
    padding: 0.75rem clamp(1rem, 3vw, 3.2rem);
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
  nav { display: flex; gap: 1.2rem; font: 0.77rem ui-sans-serif, system-ui, sans-serif; }
  nav a { color: #aeb9af; text-decoration: none; }
  nav a[aria-current] { color: #f1efe8; text-decoration: underline; text-underline-offset: 0.35rem; }
  nav .secondary-link { margin-left:.2rem; padding-left:1rem; border-left:1px solid #48524a; }
  .masthead-actions { position:relative; justify-self:end; display:flex; align-items:center; gap:.4rem; font-family:system-ui,sans-serif; }
  .header-action { display:flex; align-items:center; justify-content:center; gap:.4rem; min-height:2.1rem; padding:.3rem .45rem; border:1px solid #536158; background:#1a201c; color:#f1efe8; cursor:pointer; font:650 .68rem system-ui; }
  .preview-action { color:#c7d0c7; font-weight:600; }
  .header-action svg, .header-menu svg { width:1rem; height:1rem; flex:none; fill:none; stroke:currentColor; stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; }
  .account-action { width:2.1rem; padding:.3rem; }
  .header-menu { position:absolute; z-index:30; top:calc(100% + .65rem); right:0; width:min(19rem, calc(100vw - 1rem)); border:1px solid #536158; background:#171a18; color:#f1efe8; box-shadow:0 .7rem 1.5rem #0009; }
  .header-menu header { display:flex; align-items:center; justify-content:space-between; min-height:2.5rem; padding:.45rem .7rem; border-bottom:1px solid #48504b; }
  .header-menu header strong { display:flex; align-items:center; gap:.45rem; font-size:.77rem; }
  .header-menu header button { border:0; background:none; color:#f1efe8; cursor:pointer; font-size:1.2rem; }
  .header-menu section { display:grid; gap:.35rem; padding:.7rem; border-bottom:1px solid #343a36; }
  .header-menu label, .header-menu h2 { margin:0; font-size:.7rem; font-weight:650; }
  .header-menu select, .header-menu section button { width:100%; min-height:2rem; padding:.35rem .5rem; border:1px solid #5c665e; background:#202622; color:#f1efe8; text-align:left; font:.7rem system-ui; }
  .header-menu section button { display:flex; align-items:center; gap:.5rem; }
  .header-menu section button:disabled { color:#b8c0b8; cursor:not-allowed; }
  .header-menu .toggle { display:flex; align-items:center; gap:.55rem; min-height:2rem; cursor:pointer; }
  .header-menu p, .header-menu small { margin:0; color:#b9c2b9; font-size:.64rem; line-height:1.4; }
  a:focus-visible, button:focus-visible, select:focus-visible { outline:2px solid #eee7d6; outline-offset:2px; }
  @media (max-width: 50rem) {
    .masthead { gap: 0.7rem; padding-inline: 0.75rem; }
    .masthead { grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); }
  }
  @media (max-width: 25rem) {
    .wordmark span { display: none; }
    .masthead { min-height: 3.9rem; }
    .preview-action, .tools-action span { display:none; }
    .masthead-actions { gap:.25rem; }
    nav { gap:.65rem; }
    nav .secondary-link { margin-left:0; padding-left:.5rem; }
  }
</style>
