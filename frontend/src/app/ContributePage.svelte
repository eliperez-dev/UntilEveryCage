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
  let emailUpdatesEnabled = $state(false);
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
    const result = await communityCapabilities(fetch, true);
    capability = result.enabled ? 'enabled' : 'disabled';
    emailUpdatesEnabled = result.emailUpdatesEnabled === true;
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
    <header class="page-heading">
      <h1 id="contribute-title">{tr('Contribute', $language)}</h1>
      <a href={SECURE_INBOX_LOCAL ? '#/secure-inbox' : utilityHref('contribution-status')}>{tr('Track a submission', $language)}</a>
    </header>
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
        <a href={taskHref('facility')} aria-current={formKind === 'facility' ? 'page' : undefined} aria-disabled={submitting} onclick={preventWhileSending}>{tr('Add a facility', $language)}</a>
        <a href={taskHref(updateKind ? formKind : 'correction')} aria-current={updateKind ? 'page' : undefined} aria-disabled={submitting} onclick={preventWhileSending}>{tr('Update a record', $language)}</a>
        <a href={taskHref('bug')} aria-current={formKind === 'bug' ? 'page' : undefined} aria-disabled={submitting} onclick={preventWhileSending}>{tr('Report a problem', $language)}</a>
        <a href={taskHref('privacy_removal')} aria-current={formKind === 'privacy_removal' ? 'page' : undefined} aria-disabled={submitting} onclick={preventWhileSending}>{tr('Privacy / removal', $language)}</a>
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
          <Form kind={formKind} bind:draft={drafts[formKind]} {targetRecordId} {returnMapHref} {emailUpdatesEnabled} onreceived={received} onbusychange={value => submitting = value} />
        {:else}<p role="status">{tr('Loading form…', $language)}</p>{/if}
      </div>
    </div>
  {/if}
  <footer class="contribute-footer">{#if formKind === 'bug'}<a href="https://github.com/eliperez-dev/UntilEveryCage/issues/new" target="_blank" rel="noreferrer">{tr('Report a public issue on GitHub', $language)} <span aria-hidden="true">↗</span></a>{/if}<a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">{tr('Contribute code on GitHub', $language)} <span aria-hidden="true">↗</span></a>{#if communityReleasePublished}<a href={utilityHref('community')}>{tr('Community submissions', $language)}</a>{/if}<a href={returnMapHref}>{tr('Back to map', $language)}</a></footer>
</section>
<style>
  .contribute-page {
    width: min(calc(100% - 3rem), 42rem);
    margin: 0 auto;
    padding: 2rem 0 2.5rem;
  }
  .page-heading {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    column-gap: 1rem;
    margin-bottom: .75rem;
  }
  h1 { margin: 0; }
  a { color: var(--ink); text-underline-offset: .25em; }
  a[aria-disabled=true] { opacity: .55; cursor: wait; }
  .page-heading a, .contribute-footer a {
    display: inline-flex;
    align-items: center;
    min-height: 2.75rem;
    font-size: .85rem;
  }
  .task-nav, .update-nav {
    display: flex;
    flex-wrap: wrap;
    column-gap: .45rem;
  }
  .task-nav {
    border-block: 1px solid var(--line);
    margin-bottom: 1.55rem;
  }
  .task-nav a, .update-nav a {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 2.75rem;
    padding: .5rem .65rem;
    text-decoration: none;
    font-size: .85rem;
    overflow-wrap: anywhere;
  }
  .task-nav a { flex: 1 1 auto; box-shadow: inset 0 -2px transparent; }
  .task-nav a[aria-current] {
    background: var(--panel);
    box-shadow: inset 0 -2px var(--ink);
    font-weight: 600;
  }
  .task-nav a:hover, .update-nav a:hover { background: var(--panel-hover); }
  .update-nav { margin-bottom: 1.15rem; gap: .35rem; }
  .update-nav a { border: 1px solid var(--line); }
  .update-nav a[aria-current] {
    background: var(--ink);
    color: var(--page);
    border-color: var(--ink);
  }
  .form-pane { min-width: 0; }
  .contribute-footer {
    display: flex;
    flex-wrap: wrap;
    column-gap: 1rem;
    margin-top: 2rem;
    padding-top: .45rem;
    border-top: 1px solid var(--line);
  }
  .contribute-footer a { color: var(--ink-muted); font-size: .8rem; gap: .35rem; }
  .unavailable h2 { font: 400 1.6rem/1.2 var(--ui-font); margin-top: 0; }
  .unavailable p { overflow-wrap: anywhere; color: var(--ink-secondary); }
  .unavailable button {
    min-height: 2.75rem;
    padding: .5rem .8rem;
    background: var(--panel);
    color: var(--ink);
    border: 1px solid var(--line-strong);
    font: inherit;
  }
  :is(a, button, select):focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
  .mobile-task-chooser { display: none; }
  @media (max-width: 48rem), (max-width: 60rem) and (max-height: 32rem) {
    .contribute-page { width: min(calc(100% - 2rem), 42rem); padding: 1.25rem 0 1.5rem; }
    .page-heading a { font-size: .8rem; }
    .task-nav { display: none; }
    .mobile-task-chooser {
      display: grid;
      gap: .35rem;
      margin-bottom: 1.3rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--line);
    }
    .mobile-task-chooser label { font-size: .8rem; color: var(--ink-muted); }
    .mobile-task-chooser select {
      width: 100%;
      min-width: 0;
      min-height: 2.75rem;
      padding: .6rem .7rem;
      background: var(--panel);
      color: var(--ink);
      border: 1px solid var(--line-strong);
      border-radius: 0;
      font: 400 1rem/1.4 var(--ui-font);
    }
    .mobile-task-chooser select:disabled { opacity: .55; cursor: wait; }
    .update-nav a { flex: 1 1 auto; padding-inline: .45rem; min-width: 0; }
    .contribute-footer { margin-top: 1.5rem; }
  }
</style>
