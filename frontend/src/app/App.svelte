<script lang="ts">
  import { onMount } from 'svelte';
  import { createNavigationCommitGuard } from './navigationCommit';
  import { canonicalRouteHref, mapHrefFromHash, parseRoute, safeMapHref, type RouteState } from './routeState';
  import LandingPage from './LandingPage.svelte';
  import AboutPage from './AboutPage.svelte';
  import ContributePage from './ContributePage.svelte';
  import ProjectFooter from './ProjectFooter.svelte';
  import PublicRecord from './PublicRecord.svelte';
  let ApiPage = $state<typeof import('./ApiPage.svelte').default | null>(null);
  let apiModule: Promise<typeof import('./ApiPage.svelte')> | null = null;
  import PreviewMasthead from './PreviewMasthead.svelte';
  import { publicReleaseLabel } from '../features/locations/releasePresentation';
  import { language, tr } from './language';
  import { SECURE_INBOX_LOCAL } from '../features/contributions/secureInboxMode';
  import { requestDeviceLocation } from '../features/search/nearbySearch';
  import type { NearbySearchCommand } from '../design-lab/contract';
  let SecureInbox = $state<typeof import('./contributions/secure/SecureInbox.svelte').default | null>(null);
  let SecureReview = $state<typeof import('./contributions/secure/SecureReview.svelte').default | null>(null);
  let DesignLab = $state<typeof import('../design-lab/DesignLab.svelte').default | null>(null);
  let DatabaseResearch = $state<typeof import('./DatabaseResearch.svelte').default | null>(null);
  let RecordPage = $state<typeof import('./RecordPage.svelte').default | null>(null);
  let CommunityContributions = $state<typeof import('./CommunityContributions.svelte').default | null>(null);
  let communityModule: Promise<typeof import('./CommunityContributions.svelte')> | null = null;
  let reviewMode = $state(false);
  let publicMapVisited = $state(false);
  let publicMapActivation = $state(0);
  let wasPublicMap = false;
  let verifiedReleaseLabel = $state<string | null>(null);
  let nearbyCommand = $state<NearbySearchCommand | null>(null);
  let nearbyCommandId = 0;

  let route = $state<RouteState>(parseRoute(window.location.hash, false, SECURE_INBOX_LOCAL));
  let routeGeneration = 0;
  let navigationCommit: ReturnType<typeof createNavigationCommitGuard> | undefined;
  let loading = $state(true);
  let loadError = $state('');
  let returnMapHref = $derived.by(() => {
    if (route.kind === 'about' || route.kind === 'contribute' || route.kind === 'bug-report' || route.kind === 'community' || route.kind === 'api' || route.kind === 'downloads' || route.kind === 'database' || route.kind === 'record') return safeMapHref(route.returnMapHref) ?? mapHrefFromHash(window.location.hash, route.kind === 'database' || route.kind === 'record' ? route.releaseId : undefined);
    return mapHrefFromHash(window.location.hash, route.kind === 'map' ? route.releaseId : undefined);
  });
  let databaseHref = $derived.by(() => {
    const query = returnMapHref.split('?')[1];
    return query ? `#/database?${query}` : '#/database';
  });
  async function findNearby(signal: AbortSignal) {
    const coordinates = await requestDeviceLocation(signal);
    if (signal.aborted || route.kind !== 'landing') return;
    nearbyCommand = { id: ++nearbyCommandId, ...coordinates };
    window.location.hash = returnMapHref;
  }

  const syncRoute = () => {
    const generation = ++routeGeneration;
    try {
      const query = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
      const serverDataMode = document.querySelector<HTMLMetaElement>('meta[name="uec-local-data-mode"]')?.content ?? null;
      const privateDatabase = import.meta.env.DEV && !query.has('profile') && !query.has('release_id') && (query.has('f1a') || serverDataMode === 'candidate-preview');
      const canonicalHref = canonicalRouteHref(window.location.hash, privateDatabase);
      if (canonicalHref && canonicalHref !== window.location.hash) window.history.replaceState(null, '', canonicalHref);
      route = parseRoute(window.location.hash, privateDatabase, SECURE_INBOX_LOCAL);
      if (import.meta.env.DEV && import.meta.env.VITE_SECURE_INBOX_EXPERIMENT === 'true') {
        if (route.kind === 'secure-inbox' && !SecureInbox) void import('./contributions/secure/SecureInbox.svelte')
          .then(module => { if (generation === routeGeneration) SecureInbox = module.default; })
          .catch(() => { if (generation === routeGeneration) loadError = 'The encrypted inbox could not be opened.'; });
        if (route.kind === 'secure-review' && !SecureReview) void import('./contributions/secure/SecureReview.svelte')
          .then(module => { if (generation === routeGeneration) SecureReview = module.default; })
          .catch(() => { if (generation === routeGeneration) loadError = 'The encrypted review page could not be opened.'; });
      }
      if (route.kind === 'map' && !DesignLab) {
        void import('../design-lab/DesignLab.svelte').then(module => {
          if (generation !== routeGeneration) return;
          navigationCommit?.commit(() => {
            if (generation === routeGeneration && window.location.hash.split('?')[0] === '#/map') DesignLab = module.default;
          });
        }).catch(() => { if (generation === routeGeneration) loadError = 'The public map could not be opened.'; });
      }
      if ((route.kind === 'api' || route.kind === 'downloads') && !ApiPage) {
        apiModule ??= import('./ApiPage.svelte');
        void apiModule.then(module => { if (generation === routeGeneration) ApiPage = module.default; }).catch(() => { apiModule = null; if (generation === routeGeneration) loadError = 'The API page could not be opened.'; });
      }
      if (route.kind === 'community' && route.page !== 'form' && !CommunityContributions) {
        communityModule ??= import('./CommunityContributions.svelte');
        void communityModule.then(module => {
          if (generation !== routeGeneration) return;
          CommunityContributions = module.default;
          loading = false;
          loadError = '';
        }).catch(() => {
          communityModule = null;
          if (generation !== routeGeneration) return;
          loading = false;
          loadError = 'The community pilot could not be opened.';
        });
        loading = true;
      }
      const explicitPublicRoute = (route.kind === 'record' || route.kind === 'database') && (query.has('profile') || query.has('release_id'));
      reviewMode = import.meta.env.DEV && !explicitPublicRoute && (query.has('f1a') || (serverDataMode === 'candidate-preview' && (route.kind === 'map' || route.kind === 'database' || route.kind === 'record')) || (serverDataMode === 'real-preview' && route.kind === 'map'));
      const publicMap = route.kind === 'map' && !reviewMode;
      if (reviewMode) publicMapVisited = false;
      if (publicMap) {
        publicMapVisited = true;
        if (!wasPublicMap) publicMapActivation++;
      }
      wasPublicMap = publicMap;
      if (generation !== routeGeneration) return;
      if (route.kind !== 'community' || route.page === 'form') loading = false;
      loadError = '';
    } catch {
      loading = false;
      loadError = 'The requested page could not be opened.';
    }
  };

  onMount(() => {
    navigationCommit = createNavigationCommitGuard(window);
    if (import.meta.env.DEV) {
      import('./DatabaseResearch.svelte').then(module => DatabaseResearch = module.default);
      import('./RecordPage.svelte').then(module => RecordPage = module.default);
    }
    syncRoute();
    window.addEventListener('hashchange', syncRoute);
    return () => { navigationCommit?.dispose(); window.removeEventListener('hashchange', syncRoute); };
  });
</script>

<svelte:head>
  <title>Until Every Cage</title>
  <meta name="description" content="Behind closed doors, animals are bred, confined, experimented on and killed. Until Every Cage maps the industries responsible." />
</svelte:head>

{#if DesignLab && publicMapVisited && !reviewMode}
  <div class="retained-public-map" hidden={route.kind !== 'map'} inert={route.kind !== 'map'}>
    <DesignLab active={route.kind === 'map'} activationId={publicMapActivation} {nearbyCommand} onnearbyconsumed={id => { if (nearbyCommand?.id === id) nearbyCommand = null; }} />
  </div>
{/if}

{#if route.kind === 'landing'}
  <LandingPage mapHref={returnMapHref} onfindnearby={findNearby} />
{:else if route.kind === 'map' && DesignLab}
  {#if reviewMode}<DesignLab />{/if}
{:else if reviewMode && route.kind === 'database' && DatabaseResearch}
  <DatabaseResearch />
{:else if reviewMode && route.kind === 'record' && RecordPage}
  <RecordPage id={route.facilityId} />
{:else if reviewMode && (route.kind === 'database' || route.kind === 'record')}
  <main class="review-loading" aria-live="polite"><p role="status">Preparing the private-preview workspace…</p><small>The map module and its local data boundary are loading.</small></main>
{:else}
<div class="shell">
  <PreviewMasthead publicReleaseLabel={publicReleaseLabel(verifiedReleaseLabel)} current={route.kind === 'about' ? 'about' : route.kind === 'contribute' || route.kind === 'bug-report' || route.kind === 'community' || route.kind === 'secure-inbox' || route.kind === 'secure-review' ? 'contribute' : route.kind === 'api' || route.kind === 'downloads' ? 'api' : 'map'} mapHref={returnMapHref} {databaseHref} />

  <main id="main-content" class="shell-content" tabindex="-1">
    {#if loading}
      <p class="state" role="status">{tr('Loading page…', $language)}</p>
    {:else if loadError}
      <section class="state" role="alert" aria-labelledby="error-heading">
        <h1 id="error-heading">{tr('Unable to open this page', $language)}</h1>
        <p>{loadError}</p>
        <button type="button" onclick={() => window.location.reload()}>{tr('Reload to try again', $language)}</button>
      </section>
    {:else if route.kind === 'not-found'}
      <section class="state" aria-labelledby="not-found-heading">
        <h1 id="not-found-heading">{tr('Page not found', $language)}</h1>
        <p>{tr('This address does not match a page in this application.', $language)}</p>
        <a href="#/map">{tr('Return to the map', $language)}</a>
      </section>
    {:else if route.kind === 'about'}
      <AboutPage {returnMapHref} section={route.section} />
    {:else if route.kind === 'api' || route.kind === 'downloads'}
      {#if ApiPage}<ApiPage selectedReleaseId={new URLSearchParams(route.returnMapHref?.split('?')[1] ?? '').get('release_id')} />{:else}<p class="state" role="status">{tr('Loading API reference…', $language)}</p>{/if}
    {:else if route.kind === 'contribute' || route.kind === 'bug-report' || (route.kind === 'community' && route.page === 'form')}
      <ContributePage formKind={route.kind === 'bug-report' ? 'bug' : route.formKind ?? 'facility'} targetRecordId={route.kind === 'bug-report' ? '' : route.targetRecordId ?? ''} returnMapHref={route.returnMapHref ?? '#/map'} />
    {:else if SECURE_INBOX_LOCAL && route.kind === 'secure-inbox'}
      {#if SecureInbox}<SecureInbox />{:else}<p class="state" role="status">{tr('Opening encrypted inbox…', $language)}</p>{/if}
    {:else if SECURE_INBOX_LOCAL && route.kind === 'secure-review'}
      {#if SecureReview}<SecureReview />{:else}<p class="state" role="status">{tr('Opening encrypted review…', $language)}</p>{/if}
    {:else if route.kind === 'map'}
      <p class="state" role="status">{tr('Preparing the map…', $language)}</p>
    {:else if route.kind === 'record'}
      <PublicRecord id={route.facilityId} profile={route.profile ?? 'official'} releaseId={route.releaseId} returnMapHref={returnMapHref} onrelease={label => verifiedReleaseLabel = label} />
    {:else if route.kind === 'community'}
      {#if CommunityContributions}
        <CommunityContributions page={route.page} formKind={route.formKind ?? 'facility'} targetRecordId={route.targetRecordId ?? ''} claimId={route.claimId ?? ''} releaseId={route.releaseId ?? ''} returnMapHref={route.returnMapHref ?? '#/map'} />
      {:else}
        <p class="state" role="status">{tr('Preparing the community pilot…', $language)}</p>
      {/if}
    {/if}
  </main>
  {#if route.kind !== 'map'}<ProjectFooter {returnMapHref} />{/if}
</div>
{/if}

<style>
  .retained-public-map[hidden] { display: none; }
  .review-loading{display:grid;place-content:center;min-height:100dvh;padding:2rem;background:#171a18;color:#f1efe8;font:1rem system-ui;text-align:center}
  .review-loading small{margin-top:.55rem;color:#b9c1b7;font-size:.76rem}
  .shell{max-width:none;padding:0}.shell-content{padding:0}.shell-content > :global(section:not(.contribute-page):not(.about-page):not(.community-page):not(.help-page):not(.api-page):not(.downloads-page):not(.faq-page):not(.public-database):not(.public-record)){padding:1.5rem}
</style>
