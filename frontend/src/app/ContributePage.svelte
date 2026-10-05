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
  function selectType(event: Event) {
    const type = (event.currentTarget as HTMLSelectElement).value as ContributionType;
    window.location.hash = serializeRoute({ kind: 'contribute', formKind: type, ...(targetRecordId ? { targetRecordId } : {}), ...(returnMapHref !== '#/map' ? { returnMapHref } : {}) });
  }
  const labels: Record<ContributionType, string> = { facility: 'Add a facility', evidence: 'Add evidence', correction: 'Suggest a correction', duplicate: 'Report a duplicate', privacy_removal: 'Privacy or removal', bug: 'Report a bug' };
</script>
<svelte:head><title>Contribute · Until Every Cage</title></svelte:head>
<section class="contribute-page" aria-labelledby="contribute-title">
  <h1 id="contribute-title">Contribute</h1>
  <label class="type-selector">Contribution type
    <select value={formKind} onchange={selectType}>{#each Object.entries(labels) as [type, label]}<option value={type}>{label}</option>{/each}</select>
  </label>
  {#key `${formKind}:${targetRecordId}`}
    {#if formKind === 'bug'}<BugReportPage embedded {returnMapHref} />
    {:else if CommunityContributions}<CommunityContributions page="form" embedded {formKind} {targetRecordId} {returnMapHref} />
    {:else if loadError}<p role="alert">{loadError}</p><button type="button" onclick={loadForm}>Try again</button>
    {:else}<p role="status">Loading form…</p>{/if}
  {/key}
  <footer class="project-links" aria-label="Project links">
    <a href="mailto:untileverycageproject@protonmail.com">Email</a>
    <a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">Ko-fi</a>
    <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">GitHub</a>
    <a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noreferrer">Discord</a>
    <a href="https://linktr.ee/veganresource" target="_blank" rel="noreferrer">Resources</a>
  </footer>
</section>
<style>
  .contribute-page{width:min(100% - 3rem,46rem);margin:auto;padding:1.5rem 0 2.5rem;font:.9rem/1.5 system-ui,sans-serif;color:#f1efe8}
  h1{margin:0 0 1rem;font:500 2rem/1.15 Georgia,serif;letter-spacing:-.02em}
  .type-selector{display:grid;gap:.3rem;max-width:26rem;font-weight:600}
  select{min-height:2.5rem;width:100%;padding:.45rem .6rem;border:1px solid #59615c;border-radius:2px;background:#202523;color:#f4f1e9;font:inherit}
  .project-links{display:flex;flex-wrap:wrap;gap:.5rem 1.1rem;margin-top:1.5rem;padding-top:1rem;border-top:1px solid #3d4740;font-size:.85rem}
  a{color:#dce8d9;text-underline-offset:.2em}select:focus-visible,a:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}
  @media(max-width:40rem){.contribute-page{width:calc(100% - 2rem)}h1{font-size:1.65rem}}
</style>
