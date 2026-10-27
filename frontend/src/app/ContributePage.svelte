<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { communityCapabilities, type Receipt } from '../api/CommunityRepository';
  import { PublicReleaseRepository } from '../api/PublicReleaseRepository';
  import { language, tr } from './language';
  import { serializeRoute, type ContributionType } from './routeState';
  import ContributionReceipt from './contributions/ContributionReceipt.svelte';
  import { createIntakeDrafts, emptyIntakeDraft, intakeTitles } from './contributions/contributionForm';
  import { SECURE_INBOX_LOCAL } from '../features/contributions/secureInboxMode';
  let { formKind = 'facility', targetRecordId = '', returnMapHref = '#/map' }: { formKind?: ContributionType; targetRecordId?: string; returnMapHref?: string } = $props();
  let Form = $state<typeof import('./contributions/ContributionForm.svelte').default | null>(null);
  let SecureFlow = $state<typeof import('./contributions/secure/SecureContributionFlow.svelte').default | null>(null);
  let loadError = $state(''), receipt = $state<Receipt | null>(null), submitting = $state(false);
  let drafts = $state(createIntakeDrafts());
  const fixtureEnabled = import.meta.env.VITE_COMMUNITY_ENABLED === 'true' || import.meta.env.VITE_COMMUNITY_PILOT === 'true';
  let capability = $state<'loading' | 'enabled' | 'disabled'>(fixtureEnabled ? 'enabled' : 'loading');
  let communityReleasePublished = $state(false);
  const updateKind = $derived(['correction', 'evidence', 'duplicate'].includes(formKind));
  const taskHref = (kind: ContributionType) => serializeRoute({ kind: 'contribute', formKind: kind, ...(targetRecordId ? { targetRecordId } : {}), ...(returnMapHref !== '#/map' ? { returnMapHref } : {}) });
  const utilityHref = (path: string) => `#/${path}${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`;
  async function loadForm() {
    loadError = '';
    try { Form = (await import('./contributions/ContributionForm.svelte')).default; }
    catch { loadError = 'The form could not be opened.'; }
  }
  async function loadSecureFlow() {
    loadError = '';
    try { SecureFlow = (await import('./contributions/secure/SecureContributionFlow.svelte')).default; }
    catch { loadError = 'The form could not be opened.'; }
  }
  async function loadCapability() {
    capability = 'loading';
    capability = (await communityCapabilities(fetch, true)).enabled ? 'enabled' : 'disabled';
  }
  $effect(() => { if (!SECURE_INBOX_LOCAL && (capability === 'enabled' || formKind === 'bug') && !Form && !loadError) void loadForm(); });
  $effect(() => { if (SECURE_INBOX_LOCAL && !SecureFlow && !loadError) void loadSecureFlow(); });
  $effect(() => { formKind; targetRecordId; untrack(() => { receipt = null; submitting = false; }); });
  function received(value: Receipt) { receipt = value; drafts[formKind] = emptyIntakeDraft(); }
  function another() { receipt = null; }
  function preventWhileSending(event: MouseEvent) { if (submitting) event.preventDefault(); }
  function chooseTask(event: Event) {
    if (submitting) return;
    window.location.hash = taskHref((event.currentTarget as HTMLSelectElement).value as ContributionType);
  }
  onMount(() => {
    if (!SECURE_INBOX_LOCAL && !fixtureEnabled) void loadCapability();
    void new PublicReleaseRepository().current('community').then(value => communityReleasePublished = value !== null).catch(() => communityReleasePublished = false);
  });
</script>
<svelte:head><title>{tr(intakeTitles[formKind], $language)} · Until Every Cage</title></svelte:head>
<section class="contribute-page" aria-labelledby={receipt ? 'receipt-heading' : 'contribute-title'}>
  {#if receipt}<ContributionReceipt {receipt} {returnMapHref} bug={formKind === 'bug'} onanother={another} />
  {:else}
    <header class="page-heading"><div><h1 id="contribute-title">{tr('Contribute', $language)}</h1><p>{tr('Help improve the map.', $language)}</p></div><a href={SECURE_INBOX_LOCAL ? '#/secure-inbox' : utilityHref('contribution-status')}>{tr('Track a submission', $language)} ↗</a></header>
    <div class="contribution-workspace">
      <div class="mobile-task-chooser">
        <label for="contribution-task">{tr('Contribution tasks', $language)}</label>
        <select id="contribution-task" value={updateKind ? 'correction' : formKind} disabled={submitting} onchange={chooseTask}>
          <option value="facility">{tr('Add a facility', $language)}</option>
          <option value="correction">{tr('Update a record', $language)}</option>
          <option value="bug">{tr('Report a problem', $language)}</option>
          <option value="privacy_removal">{tr('Privacy / removal', $language)}</option>
        </select>
      </div>
      <nav class="task-nav" aria-label={tr('Contribution tasks', $language)}>
        <a href={taskHref('facility')} aria-current={formKind === 'facility' ? 'page' : undefined} aria-disabled={submitting} onclick={preventWhileSending}><span aria-hidden="true">＋</span><span><strong>{tr('Add a facility', $language)}</strong><small>{tr('Share a new location', $language)}</small></span></a>
        <a href={taskHref(updateKind ? formKind : 'correction')} aria-current={updateKind ? 'page' : undefined} aria-disabled={submitting} onclick={preventWhileSending}><span aria-hidden="true">↗</span><span><strong>{tr('Update a record', $language)}</strong><small>{tr('Correct, support, or flag', $language)}</small></span></a>
        <a href={taskHref('bug')} aria-current={formKind === 'bug' ? 'page' : undefined} aria-disabled={submitting} onclick={preventWhileSending}><span aria-hidden="true">!</span><span><strong>{tr('Report a problem', $language)}</strong><small>{tr('Something isn’t working', $language)}</small></span></a>
        <div class="privacy-link"><a href={taskHref('privacy_removal')} aria-current={formKind === 'privacy_removal' ? 'page' : undefined} aria-disabled={submitting} onclick={preventWhileSending}>{tr('Privacy / removal', $language)} ↗</a></div>
      </nav>
      <div class="form-pane">
        {#if updateKind && (SECURE_INBOX_LOCAL ? SecureFlow : Form)}<nav class="update-nav" aria-label={tr('Type of update', $language)}>{#each ['correction','evidence','duplicate'] as kind}<a href={taskHref(kind as ContributionType)} aria-current={formKind === kind ? 'page' : undefined} aria-disabled={submitting} onclick={preventWhileSending}>{tr(kind === 'correction' ? 'Correction' : kind === 'evidence' ? 'Evidence' : 'Duplicate', $language)}</a>{/each}</nav>{/if}
        {#if SECURE_INBOX_LOCAL}
          {#if loadError}<p role="alert">{tr(loadError, $language)}</p><button type="button" onclick={() => window.location.reload()}>{tr('Retry', $language)}</button>
          {:else if SecureFlow}<SecureFlow kind={formKind} bind:draft={drafts[formKind]} {targetRecordId} {returnMapHref} onbusychange={value => submitting = value} />
          {:else}<p role="status">{tr('Opening local encrypted intake…', $language)}</p>{/if}
        {:else if capability === 'loading' && formKind !== 'bug'}<p role="status">{tr('Opening contribution form…', $language)}</p>
        {:else if capability === 'disabled' && formKind !== 'bug'}<section class="unavailable"><h2>{tr('Submissions are unavailable', $language)}</h2><p>{tr('For corrections or privacy requests, contact', $language)} <a href="mailto:untileverycageproject@protonmail.com">untileverycageproject@protonmail.com</a>.</p><button type="button" onclick={() => void loadCapability()}>{tr('Retry', $language)}</button></section>
        {:else if loadError}<p role="alert">{tr(loadError, $language)}</p><button type="button" onclick={() => window.location.reload()}>{tr('Retry', $language)}</button>
        {:else if Form}
          <Form kind={formKind} bind:draft={drafts[formKind]} {targetRecordId} {returnMapHref} onreceived={received} onbusychange={value => submitting = value} />
        {:else}<p role="status">{tr('Loading form…', $language)}</p>{/if}
      </div>
    </div>
  {/if}
  <footer class="contribute-footer">{#if formKind === 'bug'}<a href="https://github.com/eliperez-dev/UntilEveryCage/issues/new" target="_blank" rel="noreferrer">{tr('Report a public issue on GitHub', $language)} <span aria-hidden="true">↗</span></a>{/if}<a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">{tr('Contribute code on GitHub', $language)} <span aria-hidden="true">↗</span></a>{#if communityReleasePublished}<a href={utilityHref('community')}>{tr('Community submissions', $language)}</a>{/if}<a href={returnMapHref}>{tr('Back to map', $language)}</a></footer>
</section>
<style>
  .contribute-page{width:min(100% - 4rem,64rem);margin:0 auto;padding:2rem 0 2.5rem;color:var(--ink);font:.9rem/1.5 system-ui,sans-serif}.page-heading{display:flex;justify-content:space-between;align-items:center;gap:1rem;margin-bottom:1.8rem}h1{font:400 2.3rem/1.15 Georgia,serif;letter-spacing:-.035em;margin:0 0 .45rem}.page-heading p{color:var(--ink-muted);margin:0}.page-heading>a{font-size:.8rem;min-height:2.75rem;display:flex;align-items:center;white-space:nowrap}.contribution-workspace{display:grid;grid-template-columns:13.7rem minmax(0,1fr);gap:2.5rem;align-items:start}.task-nav{display:flex;flex-direction:column;gap:.2rem}.task-nav>a{display:flex;align-items:center;gap:.8rem;min-height:4.1rem;padding:.75rem .8rem;text-decoration:none;border:1px solid transparent}.task-nav>a[aria-current]{background:var(--panel);border-color:var(--line)}.task-nav>a:hover{background:var(--panel-hover)}.task-nav>a>span:first-child{width:1.2rem;flex:none;color:var(--ink-muted);font-size:1.3rem;text-align:center}.task-nav strong{font-weight:500;font-size:.85rem}.task-nav small{display:block;color:var(--ink-muted);font-size:.75rem;margin-top:.2rem}.privacy-link{margin-top:1rem;padding:.6rem .8rem 0;border-top:1px solid var(--line)}.privacy-link a{display:inline-flex;align-items:center;min-height:2.75rem;font-size:.8rem}.privacy-link [aria-current]{text-decoration-thickness:2px}.form-pane{min-width:0;border-left:1px solid var(--line);padding-left:2.2rem}.update-nav{display:flex;flex-wrap:wrap;gap:.4rem;margin:0 0 1rem}.update-nav a{min-height:2.75rem;padding:.5rem .8rem;border:1px solid var(--line);display:flex;align-items:center;text-decoration:none;font-size:.8rem}.update-nav [aria-current]{background:var(--ink);color:var(--page);border-color:var(--ink)}a{color:var(--ink);text-underline-offset:.25em}a[aria-disabled=true]{opacity:.55;cursor:wait}.contribute-footer{display:flex;gap:1.25rem;flex-wrap:wrap;margin-top:2.3rem;padding-top:1rem;border-top:1px solid var(--line);font-size:.75rem;color:var(--ink-muted)}.contribute-footer a{color:var(--ink-muted);display:flex;align-items:center;min-height:2.75rem}.unavailable h2{font:400 1.7rem Georgia,serif}.unavailable p{overflow-wrap:anywhere;color:var(--ink-secondary)}:is(a,button):focus-visible{outline:3px solid var(--focus);outline-offset:3px}.mobile-task-chooser{display:none}
  @media(max-width:48rem), (max-width:60rem) and (max-height:32rem){
    .contribute-page{width:min(calc(100% - 2rem),42rem);padding:1.2rem 0 1.5rem}
    .page-heading{align-items:flex-start;gap:.5rem;margin-bottom:1.15rem;flex-wrap:wrap}
    h1{font-size:2rem;margin-bottom:.25rem}
    .page-heading p{display:none}
    .page-heading>a{font-size:.8rem;white-space:normal;max-width:100%;gap:.3rem;text-align:right;justify-content:flex-end;min-height:2.75rem}
    .contribution-workspace{display:block}
    .task-nav{display:none}
    .mobile-task-chooser{display:grid;gap:.35rem;margin-bottom:1.4rem}
    .mobile-task-chooser label{font-size:.75rem;color:var(--ink-muted)}
    .mobile-task-chooser select{width:100%;min-width:0;min-height:2.75rem;padding:.6rem .7rem;background:var(--panel);color:var(--ink);border:1px solid var(--line-strong);border-radius:0;font:400 1rem/1.4 system-ui,sans-serif}
    .mobile-task-chooser select:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
    .mobile-task-chooser select:disabled{opacity:.55;cursor:wait}
    .form-pane{padding:0;border:0}
    .update-nav{gap:.35rem;margin-bottom:1.15rem}
    .update-nav a{flex:1;justify-content:center;padding:.5rem .45rem;font-size:.8rem;min-width:0;overflow-wrap:anywhere}
    .contribute-footer{margin-top:1.5rem;gap:.15rem 1rem;padding-top:.6rem}
    .unavailable h2{font-size:1.6rem;margin-top:0}
    .unavailable button{min-height:2.75rem;padding:.5rem .8rem;color:var(--ink);background:var(--panel);border:1px solid var(--line-strong);font:inherit}
  }
  @media(max-width:22rem){.page-heading>a{font-size:.75rem}.page-heading{align-items:center}.contribute-page{width:calc(100% - 1.5rem)}}
</style>
