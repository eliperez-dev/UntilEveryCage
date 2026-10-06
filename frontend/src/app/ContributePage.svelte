<script lang="ts">
  let CommunityContributions = $state<typeof import('./CommunityContributions.svelte').default | null>(null);
  let loadError = $state('');
  let communityModule: Promise<typeof import('./CommunityContributions.svelte')> | null = null;
  function loadForm() {
    loadError = '';
    communityModule ??= import('./CommunityContributions.svelte');
    void communityModule.then(module => CommunityContributions = module.default).catch(() => { communityModule = null; loadError = 'The form could not be opened.'; });
  }
  import BugReportPage from './BugReportPage.svelte';
  import { serializeRoute, type ContributionType } from './routeState';
  let { formKind = 'facility', targetRecordId = '', returnMapHref = '#/map' }: { formKind?: ContributionType; targetRecordId?: string; returnMapHref?: string } = $props();
  $effect(() => { if (formKind !== 'bug' && !CommunityContributions && !loadError) loadForm(); });
  const taskHref = (formKind: ContributionType) => serializeRoute({ kind: 'contribute', formKind, ...(targetRecordId ? { targetRecordId } : {}), ...(returnMapHref !== '#/map' ? { returnMapHref } : {}) });
  const utilityHref = (path: string) => `#/${path}${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`;
  const taskNames: Record<ContributionType, string> = { facility: 'Facility', evidence: 'Evidence', correction: 'Correction', duplicate: 'Duplicate', privacy_removal: 'Privacy/removal', bug: 'Bug report' };
  const labels: Record<ContributionType, string> = { facility: 'Add a facility', evidence: 'Add evidence', correction: 'Suggest a correction', duplicate: 'Report a duplicate', privacy_removal: 'Privacy or removal', bug: 'Report a bug' };
</script>
<svelte:head><title>{labels[formKind]} · Until Every Cage</title></svelte:head>
<section class="contribute-page" aria-labelledby="contribute-title">
  <h1 id="contribute-title">{labels[formKind]}</h1>
  <p id="contribution-choice" class="choice-label">Choose a contribution type</p>
  <nav class="task-nav" aria-label="Contribution tasks" aria-describedby="contribution-choice">
    {#each Object.entries(taskNames) as [type, label]}<a href={taskHref(type as ContributionType)} aria-current={formKind === type ? 'page' : undefined}>{label}</a>{/each}
  </nav>
  {#key `${formKind}:${targetRecordId}`}
    {#if formKind === 'bug'}<BugReportPage embedded {returnMapHref} />
    {:else if CommunityContributions}<CommunityContributions page="form" embedded {formKind} {targetRecordId} {returnMapHref} />
    {:else if loadError}<p role="alert">{loadError}</p><button type="button" onclick={loadForm}>Try again</button>
    {:else}<p role="status">Loading form…</p>{/if}
  {/key}
  <footer class="contribute-footer">
    <p class="code-invitation">The code is open source. Help with code, design, tests, or data adapters: <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">Contribute code on GitHub</a>.</p>
    <div class="project-links" aria-label="Project links">
    <a href={utilityHref('contribution-status')}>Check status</a>
    <a href={utilityHref('community')}>Community submissions</a>
    <a href="mailto:untileverycageproject@protonmail.com">Email</a>
    <a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">Ko-fi</a>
    <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">GitHub</a>
    <a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noreferrer">Discord</a>
    <a href="https://linktr.ee/veganresource" target="_blank" rel="noreferrer">Resources</a>
    </div>
  </footer>
</section>
<style>
  .contribute-page{width:min(100% - 3rem,46rem);margin:auto;padding:1.5rem 0 2.5rem;font:.9rem/1.5 system-ui,sans-serif;color:#f1efe8}
  h1{margin:0 0 1rem;font:500 2rem/1.15 Georgia,serif;letter-spacing:-.02em}
  .task-nav{display:flex;flex-wrap:wrap;gap:.3rem 1.1rem;margin:0 0 1rem;font-size:.85rem}
  .choice-label{margin:0;font-weight:600;font-size:.85rem}.task-nav a{display:flex;align-items:center;min-height:2rem;color:#bfc9bd;text-decoration:underline;text-underline-offset:.25rem;text-decoration-color:#637266}
  .task-nav a[aria-current]{color:#f1efe8;text-decoration:underline;text-underline-offset:.35rem;text-decoration-thickness:2px}
  .task-nav a:hover{color:#fff}
  .contribute-footer{margin-top:1.5rem;padding-top:1rem;border-top:1px solid #3d4740}.code-invitation{margin:0 0 .75rem;color:#c6d0c5;font-size:.85rem}
  .project-links{display:flex;flex-wrap:wrap;gap:.5rem 1.1rem;font-size:.85rem}
  a{color:#dce8d9;text-underline-offset:.2em}a:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}
  @media(max-width:40rem){.contribute-page{width:calc(100% - 2rem)}h1{font-size:1.65rem}}
</style>
