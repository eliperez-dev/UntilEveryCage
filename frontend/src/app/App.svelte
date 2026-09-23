<script lang="ts">
  import { onMount } from 'svelte';
  import { parseRoute, type RouteState } from './routeState';
  let DesignLab: typeof import('../design-lab/DesignLab.svelte').default | null = null;
  let reviewMode = false;

  let route: RouteState = { kind: 'map' };
  let loading = true;
  let loadError = '';

  const syncRoute = () => {
    try {
      route = parseRoute(window.location.hash);
      const query = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
      const serverDataMode = document.querySelector<HTMLMetaElement>('meta[name="uec-local-data-mode"]')?.content ?? null;
      reviewMode = import.meta.env.DEV && (query.has('f1a') || (serverDataMode === 'real-preview' && route.kind === 'map'));
      loading = false;
      loadError = '';
    } catch {
      loading = false;
      loadError = 'The requested page could not be opened.';
    }
  };

  onMount(() => {
    if (import.meta.env.DEV) import('../design-lab/DesignLab.svelte').then(module => DesignLab = module.default);
    syncRoute();
    window.addEventListener('hashchange', syncRoute);
    return () => window.removeEventListener('hashchange', syncRoute);
  });
</script>

<svelte:head>
  <title>Until Every Cage</title>
  <meta name="description" content="A structural preview of the Until Every Cage application." />
</svelte:head>

{#if reviewMode && route.kind === 'map' && DesignLab}
  <svelte:component this={DesignLab} />
{:else}
<div class="shell">
  <header class="site-header">
    <a class="wordmark" href="#/map">Until Every Cage</a>
    <nav aria-label="Main navigation">
      <a href="#/map" aria-current={route.kind === 'map' ? 'page' : undefined}>Map</a>
      <a href="#/database" aria-current={route.kind === 'database' ? 'page' : undefined}>Database</a>
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
      <section aria-labelledby="page-heading">
        <h1 id="page-heading">Map</h1>
        <p>This page is a structural shell. Map content is not connected yet.</p>
      </section>
    {:else if route.kind === 'database'}
      <section aria-labelledby="page-heading">
        <h1 id="page-heading">Database</h1>
        <p>This page is a structural shell. Database content is not connected yet.</p>
      </section>
    {:else}
      <section aria-labelledby="page-heading">
        <p><a href="#/database">Database</a></p>
        <h1 id="page-heading">Record</h1>
        <p class="record-id">Record ID: <code>{route.facilityId}</code></p>
        <p>This page is a structural shell. Record details are not connected yet.</p>
      </section>
    {/if}
  </main>
</div>
{/if}
