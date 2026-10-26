<script lang="ts">
  import { onMount } from 'svelte';
  import { CommunityError, createCommunityRepository, type ContributionStatus, type StatusResult } from '../../api/CommunityRepository';
  import { language, tr } from '../language';
  import { readTrackingLink } from './contributionForm';
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  let privateLink = $state(''), submissionId = $state(''), secret = $state('');
  let result = $state<StatusResult | null>(null), busy = $state(false), message = $state('');
  let manualOpen = $state(false), entryOpen = $state(false);
  let requestGeneration = 0;
  const repository = createCommunityRepository();
  const labels: Record<ContributionStatus, string> = { received: 'Received', held: 'Awaiting review', screened: 'Privacy screened', rejected: 'Not accepted', restricted: 'Restricted', removed: 'Removed from intake', published: 'Published to community submissions' };
  const meanings: Record<ContributionStatus, string> = {
    received: 'Your contribution is waiting for review.', held: 'A maintainer needs to review this contribution.',
    screened: 'Privacy screening is complete. This does not verify the facts or approve publication.',
    rejected: 'This contribution will not be published.', restricted: 'Access to this submission is restricted.',
    removed: 'This submission has been removed from intake.',
    published: 'Your contribution was published as an unreviewed community claim, separate from the curated release.',
  };
  const stage = $derived(result?.status === 'received' ? 0 : ['held', 'screened', 'restricted'].includes(result?.status ?? '') ? 1 : 2);
  const claimHref = $derived.by(() => {
    if (result?.status !== 'published' || !result.public_record_url) return '';
    const url = new URL(result.public_record_url, window.location.origin);
    const releaseId = url.searchParams.get('release_id');
    return releaseId ? `#/community/claim?id=${encodeURIComponent(result.submission_id)}&release_id=${encodeURIComponent(releaseId)}` : '';
  });
  async function check() {
    const generation = ++requestGeneration;
    message = ''; busy = true;
    try { const next = await repository.status(submissionId.trim(), secret.trim()); if (generation === requestGeneration) { result = next; entryOpen = false; } }
    catch (error) { if (generation === requestGeneration) { result = null; message = error instanceof CommunityError ? error.message : 'Status could not be checked. Try again.'; } }
    finally { if (generation === requestGeneration) busy = false; }
  }
  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (busy) return;
    if (privateLink.trim()) {
      const credentials = readTrackingLink(privateLink.trim());
      if (!credentials) { message = 'Paste the complete private tracking link from your receipt.'; return; }
      submissionId = credentials.submissionId; secret = credentials.secret;
    }
    void check();
  }
  function fromFragment() {
    const credentials = readTrackingLink(window.location.hash);
    if (!credentials) return;
    if (submissionId === credentials.submissionId && secret === credentials.secret && (result || busy)) return;
    privateLink = ''; submissionId = credentials.submissionId; secret = credentials.secret; result = null;
    void check();
  }
  onMount(() => { fromFragment(); return () => { requestGeneration += 1; }; });
  const contributeHref = $derived(`#/contribute${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`);
</script>
<svelte:window onhashchange={fromFragment} />
<section class="tracking-page" aria-labelledby="tracking-heading">
  <header class="page-heading"><div><h1 id="tracking-heading">{tr(result ? 'Your submission' : 'Track a submission', $language)}</h1>{#if result}<p class="reference">{tr('Reference', $language)} <span>{result.submission_id}</span></p>{/if}</div><a href={contributeHref}>{tr('Back to Contribute', $language)}</a></header>
  {#if result}
    <div class="status-workspace" aria-live="polite"><ol class="timeline" aria-label={tr('Submission progress', $language)}>{#each ['Received','Review','Decision'] as label, index}<li class:past={index < stage} class:current={index === stage}><strong>{tr(label, $language)}</strong><small>{tr(index === 0 ? 'Received' : index === 1 ? stage >= 1 ? 'Status recorded' : 'Pending' : stage === 2 ? 'Status recorded' : 'Not recorded', $language)}</small></li>{/each}</ol><section class="status-result"><p class="eyebrow">{tr('Current status', $language)}</p><h2>{tr(labels[result.status], $language)}</h2><p>{tr(meanings[result.status], $language)}</p>{#if claimHref}<a class="primary" href={claimHref}>{tr('Open the claim details', $language)} ↗</a>{:else if result.status === 'published'}<p class="quiet-note">{tr('No public link is currently available.', $language)}</p>{/if}<div class="status-actions"><button type="button" disabled={busy} onclick={() => void check()}>{tr(busy ? 'Checking…' : 'Refresh status', $language)}</button><button class="text-action" type="button" onclick={() => entryOpen = !entryOpen}>{tr('Use another tracking link', $language)}</button></div></section></div>
  {:else if busy}<p class="loading" role="status">{tr('Checking your submission…', $language)}</p>{/if}
  {#if (!result && !busy) || entryOpen}
    <form class="tracking-entry" onsubmit={submit} novalidate><label>{tr('Private tracking link', $language)}<input type="password" bind:value={privateLink} maxlength="3000" autocomplete="off" placeholder={tr('Paste the link from your receipt', $language)} /></label><details bind:open={manualOpen}><summary>{tr('Enter receipt details instead', $language)}</summary><div class="manual-fields"><label>{tr('Submission ID', $language)}<input bind:value={submissionId} maxlength="36" autocomplete="off" /></label><label>{tr('Private receipt', $language)}<input type="password" bind:value={secret} maxlength="80" autocomplete="off" /></label></div></details><button class="primary" type="submit" disabled={busy}>{tr(busy ? 'Checking…' : 'Check status', $language)}</button><p class="quiet-note">{tr('The private link grants access. A reference alone is not enough.', $language)}</p></form>
  {/if}
  {#if message}<p class="status-error" role="alert">{tr(message, $language)}</p>{/if}
</section>
<style>
  .tracking-page{width:min(100% - 4rem,64rem);margin:0 auto;padding:2rem 0 2.5rem;color:var(--ink);font:.9rem/1.5 system-ui,sans-serif}.page-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:1.2rem;margin-bottom:2rem}h1{font:400 2.3rem/1.15 Georgia,serif;letter-spacing:-.035em;margin:0 0 .65rem}.page-heading>a{font-size:.8rem;min-height:2.75rem;display:flex;align-items:center;white-space:nowrap}.reference{margin:0;color:var(--ink-muted);font-size:.8rem}.reference span{overflow-wrap:anywhere}.status-workspace{display:grid;grid-template-columns:13.7rem minmax(0,1fr);gap:2.5rem}.timeline{list-style:none;margin:0;padding:0}.timeline li{position:relative;padding:0 0 1.8rem 2rem;color:var(--ink-muted);font-size:.85rem}.timeline li:before{content:'';position:absolute;top:.2rem;left:.1rem;width:.75rem;height:.75rem;border:1px solid var(--ink-muted);border-radius:50%;background:var(--page)}.timeline li:not(:last-child):after{content:'';position:absolute;left:.5rem;top:1.4rem;bottom:.4rem;width:1px;background:var(--line)}.timeline li.past:before,.timeline li.current:before{background:var(--ink)}.timeline li.current{color:var(--ink)}.timeline li.current:before{outline:3px solid var(--line)}.timeline strong{font-weight:500}.timeline small{display:block;margin-top:.25rem;font-size:.75rem}.status-result{border-left:1px solid var(--line);padding-left:2.2rem;min-width:0}.eyebrow{font-size:.7rem;color:var(--ink-muted);text-transform:uppercase;letter-spacing:.1em;margin:0 0 1rem}h2{font:400 2rem/1.2 Georgia,serif;letter-spacing:-.02em;margin:0 0 .85rem}.status-result>p{max-width:34rem}.status-actions{display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;border-top:1px solid var(--line);margin-top:1.5rem;padding-top:1rem}button,.primary{min-height:2.75rem;padding:.6rem .9rem;border:1px solid var(--line-strong);background:transparent;color:var(--ink);font:inherit;cursor:pointer}.primary{display:inline-flex;align-items:center;justify-content:center;width:max-content;max-width:100%;background:var(--ink);border-color:var(--ink);color:var(--page);text-decoration:none}.text-action{border:0;text-decoration:underline;text-underline-offset:.25em}.tracking-entry{max-width:40rem;display:grid;gap:1rem;margin-top:1.5rem}label{display:grid;gap:.4rem;font-size:.8rem;font-weight:500}input{width:100%;min-height:2.75rem;padding:.6rem .75rem;border:1px solid var(--line-strong);background:var(--panel);color:var(--ink);font:400 .9rem/1.5 system-ui,sans-serif;border-radius:0}summary{min-height:2.75rem;cursor:pointer;color:var(--ink-muted);font-size:.8rem;padding:.4rem 0}.manual-fields{display:grid;gap:1rem;margin-top:.5rem}.quiet-note{font-size:.8rem;color:var(--ink-muted)}a{color:var(--ink);text-underline-offset:.25em}.status-error{border-left:2px solid var(--focus);padding:.65rem .8rem;font-size:.85rem;max-width:40rem}.loading{color:var(--ink-muted)}:is(a,button,input,summary):focus-visible{outline:3px solid var(--focus);outline-offset:3px}button:hover{background:var(--panel-hover)}button:disabled{opacity:.6;cursor:wait}@media(max-width:48rem){.status-workspace{grid-template-columns:11rem minmax(0,1fr);gap:1.4rem}.status-result{padding-left:1.4rem}}@media(max-width:37rem){.tracking-page{width:calc(100% - 2rem);padding-top:1.5rem}h1{font-size:2rem}.page-heading>a{font-size:.75rem}.status-workspace{display:block}.timeline{display:flex;gap:1rem;margin-bottom:1.4rem}.timeline li{flex:1;padding:1.5rem 0 0;font-size:.8rem}.timeline li:before{top:.1rem}.timeline li:not(:last-child):after{left:1.5rem;right:0;top:.5rem;bottom:auto;height:1px;width:auto}.timeline small{font-size:.7rem}.status-result{border-left:0;border-top:1px solid var(--line);padding:1.3rem 0 0}input{font-size:1rem}.reference span{display:block}.status-actions{align-items:stretch}}
</style>
