<script lang="ts">
  import { onMount } from 'svelte';
  import { parseRoute, type RouteState } from './routeState';
  import MethodologyPage from './MethodologyPage.svelte';
  import AboutPage from './AboutPage.svelte';
  import ContributePage from './ContributePage.svelte';
  import HelpPage from './HelpPage.svelte';
  import DownloadsPage from './DownloadsPage.svelte';
  import FaqPage from './FaqPage.svelte';
  import ProjectFooter from './ProjectFooter.svelte';
  import PublicDatabase from './PublicDatabase.svelte';
  import PublicRecord from './PublicRecord.svelte';
  let ApiPage = $state<typeof import('./ApiPage.svelte').default | null>(null);
  let apiModule: Promise<typeof import('./ApiPage.svelte')> | null = null;
  import PreviewMasthead from './PreviewMasthead.svelte';
  let DesignLab = $state<typeof import('../design-lab/DesignLab.svelte').default | null>(null);
  let DatabaseResearch = $state<typeof import('./DatabaseResearch.svelte').default | null>(null);
  let RecordPage = $state<typeof import('./RecordPage.svelte').default | null>(null);
  let CommunityContributions = $state<typeof import('./CommunityContributions.svelte').default | null>(null);
  let communityModule: Promise<typeof import('./CommunityContributions.svelte')> | null = null;
  let reviewMode = $state(false);
  let verifiedReleaseLabel = $state<string | null>(null);

  let route = $state<RouteState>({ kind: 'map' });
  let loading = $state(true);
  let loadError = $state('');
  let returnMapHref = $derived.by(() => {
    if (route.kind === 'about' || route.kind === 'contribute' || route.kind === 'bug-report' || route.kind === 'community' || route.kind === 'methodology' || route.kind === 'help' || route.kind === 'api' || route.kind === 'faq' || route.kind === 'downloads') return route.returnMapHref ?? '#/map';
    const currentQuery = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
    return import.meta.env.DEV && currentQuery.get('f1a') === 'field' ? '#/map?f1a=field' : '#/map';
  });
  let databaseHref = $derived.by(() => {
    const query = returnMapHref.split('?')[1];
    return query ? `#/database?${query}` : '#/database';
  });

  const syncRoute = () => {
    try {
      route = parseRoute(window.location.hash);
      if (route.kind === 'map' && !DesignLab) {
        void import('../design-lab/DesignLab.svelte').then(module => DesignLab = module.default).catch(() => { loadError = 'The public map could not be opened.'; });
      }
      if (route.kind === 'api' && !ApiPage) {
        apiModule ??= import('./ApiPage.svelte');
        void apiModule.then(module => ApiPage = module.default).catch(() => { apiModule = null; loadError = 'The API page could not be opened.'; });
      }
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
      const explicitPublicRecord = route.kind === 'record' && (query.has('profile') || query.has('release_id'));
      reviewMode = import.meta.env.DEV && !explicitPublicRecord && (query.has('f1a') || ((serverDataMode === 'real-preview' || serverDataMode === 'candidate-preview') && route.kind === 'map'));
      loading = false;
      loadError = '';
    } catch {
      loading = false;
      loadError = 'The requested page could not be opened.';
    }
  };

  onMount(() => {
    if (import.meta.env.DEV) {
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
  <MethodologyPage returnMapHref={route.returnMapHref ?? '#/map'} />
{:else if route.kind === 'map' && DesignLab}
  <DesignLab />
{:else if reviewMode && route.kind === 'database' && DatabaseResearch}
  <DatabaseResearch />
{:else if reviewMode && route.kind === 'record' && RecordPage}
  <RecordPage id={route.facilityId} />
{:else if reviewMode && (route.kind === 'database' || route.kind === 'record')}
  <main class="review-loading" aria-live="polite"><p role="status">Preparing the private-preview workspace…</p><small>The map module and its local data boundary are loading.</small></main>
{:else}
<div class="shell">
  <PreviewMasthead publicReleaseLabel={verifiedReleaseLabel ? `Release ${verifiedReleaseLabel}` : null} current={route.kind === 'about' || route.kind === 'help' || route.kind === 'faq' ? 'about' : route.kind === 'contribute' || route.kind === 'bug-report' || route.kind === 'community' ? 'contribute' : route.kind === 'database' || route.kind === 'record' || route.kind === 'api' || route.kind === 'downloads' ? 'database' : 'map'} mapHref={returnMapHref} {databaseHref} />

  <main id="main-content" class="shell-content" tabindex="-1">
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
    {:else if route.kind === 'about'}
      <AboutPage returnMapHref={route.returnMapHref ?? '#/map'} />
    {:else if route.kind === 'downloads'}
      <DownloadsPage {returnMapHref} />
    {:else if route.kind === 'faq'}
      <FaqPage {returnMapHref} />
    {:else if route.kind === 'help'}
      <HelpPage returnMapHref={route.returnMapHref ?? '#/map'} />
    {:else if route.kind === 'api'}
      {#if ApiPage}<ApiPage />{:else}<p class="state" role="status">Loading API reference…</p>{/if}
    {:else if route.kind === 'contribute'}
      <ContributePage formKind={route.formKind ?? 'facility'} targetRecordId={route.targetRecordId ?? ''} returnMapHref={route.returnMapHref ?? '#/map'} />
    {:else if route.kind === 'bug-report'}
      <ContributePage formKind="bug" returnMapHref={route.returnMapHref ?? '#/map'} />
    {:else if route.kind === 'map'}
      <p class="state" role="status">Preparing the map…</p>
    {:else if route.kind === 'database'}
      <PublicDatabase onrelease={label => verifiedReleaseLabel = label} />
    {:else if route.kind === 'record'}
      <PublicRecord id={route.facilityId} profile={route.profile ?? 'official'} releaseId={route.releaseId} onrelease={label => verifiedReleaseLabel = label} />
    {:else if route.kind === 'community'}
      {#if route.page === 'form'}
        <ContributePage formKind={route.formKind ?? 'facility'} targetRecordId={route.targetRecordId ?? ''} returnMapHref={route.returnMapHref ?? '#/map'} />
      {:else if CommunityContributions}
        <CommunityContributions page={route.page} formKind={route.formKind ?? 'facility'} targetRecordId={route.targetRecordId ?? ''} claimId={route.claimId ?? ''} releaseId={route.releaseId ?? ''} returnMapHref={route.returnMapHref ?? '#/map'} />
      {:else}
        <p class="state" role="status">Preparing the community pilot…</p>
      {/if}
    {/if}
  </main>
  {#if route.kind !== 'map'}<ProjectFooter {returnMapHref} />{/if}
</div>
{/if}

<style>
  .review-loading{display:grid;place-content:center;min-height:100dvh;padding:2rem;background:#171a18;color:#f1efe8;font:1rem system-ui;text-align:center}
  .review-loading small{margin-top:.55rem;color:#b9c1b7;font-size:.76rem}
  .shell{max-width:none;padding:0}.shell-content{padding:0}.shell-content > :global(section:not(.contribute-page):not(.about-page):not(.community-page):not(.help-page):not(.api-page):not(.downloads-page):not(.faq-page):not(.public-database):not(.public-record)){padding:1.5rem}
</style>
