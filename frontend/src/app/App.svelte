<script lang="ts">
  import { onMount } from 'svelte';
  import { parseRoute, type RouteState } from './routeState';
  import MethodologyPage from './MethodologyPage.svelte';
  let DesignLab: typeof import('../design-lab/DesignLab.svelte').default | null = null;
  let DatabaseResearch: typeof import('./DatabaseResearch.svelte').default | null = null;
  let RecordPage: typeof import('./RecordPage.svelte').default | null = null;
  let PublicReleaseMap: typeof import('./PublicReleaseMap.svelte').default | null = null;
  let CommunityContributions: typeof import('./CommunityContributions.svelte').default | null = null;
  let communityModule: Promise<typeof import('./CommunityContributions.svelte')> | null = null;
  let reviewMode = false;

  let route: RouteState = { kind: 'map' };
  let loading = true;
  let loadError = '';

  const syncRoute = () => {
    try {
      route = parseRoute(window.location.hash);
      if (route.kind === 'community' && !CommunityContributions) {
        communityModule ??= import('./CommunityContributions.svelte');
        void communityModule.then(module => {
          CommunityContributions = module.default;
          loading = false;
          loadError = '';
        }).catch(() => {
          communityModule = null;
          loading = false;
          loadError = 'The community pilot could not be opened.';
        });
        loading = true;
      }
      const query = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
      const serverDataMode = document.querySelector<HTMLMetaElement>('meta[name="uec-local-data-mode"]')?.content ?? null;
      reviewMode = import.meta.env.DEV && (query.has('f1a') || (serverDataMode === 'real-preview' && (route.kind === 'map' || route.kind === 'database' || route.kind === 'record')));
      loading = false;
      loadError = '';
    } catch {
      loading = false;
      loadError = 'The requested page could not be opened.';
    }
  };

  onMount(() => {
    import('./PublicReleaseMap.svelte').then(module => PublicReleaseMap = module.default);
    if (import.meta.env.DEV) {
      import('../design-lab/DesignLab.svelte').then(module => DesignLab = module.default);
      import('./DatabaseResearch.svelte').then(module => DatabaseResearch = module.default);
      import('./RecordPage.svelte').then(module => RecordPage = module.default);
    }
    syncRoute();
    window.addEventListener('hashchange', syncRoute);
    return () => window.removeEventListener('hashchange', syncRoute);
  });
</script>

<svelte:head>
  <title>Until Every Cage</title>
  <meta name="description" content="A structural preview of the Until Every Cage application." />
</svelte:head>

{#if route.kind === 'methodology'}
  <MethodologyPage />
{:else if reviewMode && route.kind === 'map' && DesignLab}
  <svelte:component this={DesignLab} />
{:else if reviewMode && route.kind === 'database' && DatabaseResearch}
  <svelte:component this={DatabaseResearch} />
{:else if reviewMode && route.kind === 'record' && RecordPage}
  <svelte:component this={RecordPage} id={route.facilityId} />
{:else if reviewMode && (route.kind === 'map' || route.kind === 'database' || route.kind === 'record')}
  <main class="review-loading" aria-live="polite"><p role="status">Preparing the private-preview workspace…</p><small>The map module and its local data boundary are loading.</small></main>
{:else}
<div class="shell">
  <header class="site-header">
    <a class="wordmark" href="#/map">Until Every Cage</a>
    <nav aria-label="Main navigation">
      <a href="#/map" aria-current={route.kind === 'map' ? 'page' : undefined}>Map</a>
      <a href="#/database" aria-current={route.kind === 'database' ? 'page' : undefined}>Database</a>
      <a href="#/methodology">Methodology</a>
      {#if import.meta.env.VITE_COMMUNITY_PILOT === 'true'}
        <details class="tools-menu"><summary>Tools</summary><div class="tools-links"><a href="#/contribute">Contribute</a><a href="#/contribution-status">Check a receipt</a><a href="#/community">Community claims</a></div></details>
      {/if}
    </nav>
  </header>

  <main id="main-content" tabindex="-1">
    {#if loading}
      <p class="state" role="status">Loading page…</p>
    {:else if loadError}
      <section class="state" role="alert" aria-labelledby="error-heading">
        <h1 id="error-heading">Unable to open this page</h1>
        <p>{loadError}</p>
        <button type="button" onclick={syncRoute}>Try again</button>
      </section>
    {:else if route.kind === 'not-found'}
      <section class="state" aria-labelledby="not-found-heading">
        <h1 id="not-found-heading">Page not found</h1>
        <p>This address does not match a page in the preview.</p>
        <a href="#/map">Return to the map</a>
      </section>
    {:else if route.kind === 'map'}
      {#if PublicReleaseMap}
        <svelte:component this={PublicReleaseMap} />
      {:else}
        <p class="state" role="status">Preparing the map…</p>
      {/if}
    {:else if route.kind === 'database'}
      <section aria-labelledby="page-heading">
        <h1 id="page-heading">Database</h1>
        <p>This page is a structural shell. Database content is not connected yet.</p>
      </section>
    {:else if route.kind === 'record'}
      <section aria-labelledby="page-heading">
        <p><a href="#/database">Database</a></p>
        <h1 id="page-heading">Record</h1>
        <p class="record-id">Record ID: <code>{route.facilityId}</code></p>
        <p>This page is a structural shell. Record details are not connected yet.</p>
        {#if import.meta.env.VITE_COMMUNITY_PILOT === 'true'}<p><a href={`#/contribute?target=${encodeURIComponent(route.facilityId)}`}>Contribute evidence or a correction</a></p>{/if}
      </section>
    {:else if route.kind === 'community'}
      {#if CommunityContributions}
        <svelte:component this={CommunityContributions} page={route.page} targetRecordId={route.targetRecordId ?? ''} claimId={route.claimId ?? ''} releaseId={route.releaseId ?? ''} />
      {:else}
        <p class="state" role="status">Preparing the community pilot…</p>
      {/if}
    {/if}
  </main>
</div>
{/if}

<style>
  .review-loading{display:grid;place-content:center;min-height:100dvh;padding:2rem;background:#171a18;color:#f1efe8;font:1rem system-ui;text-align:center}
  .review-loading small{margin-top:.55rem;color:#b9c1b7;font-size:.76rem}
  .tools-menu{position:relative}.tools-menu summary{cursor:pointer;list-style:none}.tools-menu summary::-webkit-details-marker{display:none}.tools-menu summary::after{content:'⌄';margin-left:.3rem;color:#858e87}.tools-links{position:absolute;z-index:10;top:calc(100% + .6rem);right:0;display:grid;min-width:12rem;padding:.4rem;border:1px solid #69716a;background:#171a18;box-shadow:0 8px 24px #0008}.tools-links a{padding:.55rem;color:#ded8c9;text-decoration:none}.tools-links a:hover{background:#282e2a}
</style>
