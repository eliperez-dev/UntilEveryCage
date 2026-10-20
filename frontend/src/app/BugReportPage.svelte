<script lang="ts">
  import { createCommunityRepository, type Receipt } from '../api/CommunityRepository';
  let { returnMapHref = '#/map', embedded = false }: { returnMapHref?: string; embedded?: boolean } = $props();
  const repository = createCommunityRepository();
  let receipt = $state<Receipt | null>(null);
  let busy = $state(false);
  let error = $state('');
  const trackingHref = $derived(receipt ? `#/contribution-status?${new URLSearchParams({ submission_id: receipt.submission_id, receipt_secret: receipt.receipt_secret })}` : '');

  async function submitReport(event: SubmitEvent) {
    event.preventDefault();
    if (busy || receipt) return;
    const form = event.currentTarget as HTMLFormElement;
    const values = new FormData(form);
    const field = (name: string) => String(values.get(name) ?? '').trim();
    busy = true; error = '';
    try {
      receipt = await repository.submit({ kind: 'bug', consent: true,
        description: field('happened'), reproduction_steps: field('steps'),
        ...(field('expected') ? { expected_behavior: field('expected') } : {}),
        ...(field('page_url') ? { page_url: field('page_url') } : {}),
      });
    } catch { error = 'Could not send the report. Try again.'; }
    finally { busy = false; }
  }
</script>

<svelte:head><title>Report a bug · Until Every Cage</title></svelte:head>
<section class="bug-page" class:embedded aria-label="Report a bug">
  {#if !embedded}<p><a href={`#/contribute${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`}>Contribute</a></p>
  <h1>Report a bug</h1>{/if}
  <p class="intro">Send a bug report to the project.</p>
  <form class="bug-form" onsubmit={submitReport}>
    <label>What happened?<textarea name="happened" required maxlength="2000" rows="2"></textarea></label>
    <label>What did you expect?<textarea name="expected" maxlength="1000" rows="2"></textarea></label>
    <label>Steps to reproduce<textarea name="steps" required maxlength="2000" rows="2"></textarea></label>
    <label>Page link (optional)<input name="page_url" type="url" maxlength="1000" placeholder="https://…" /></label>
    <button type="submit" disabled={busy || receipt !== null}>{busy ? 'Sending…' : receipt ? 'Sent' : 'Send report'}</button>
  </form>
  {#if error}<p role="alert">{error}</p>{/if}
  {#if receipt}<p class="draft-link" role="status">Report saved. <a href={trackingHref}>Track report</a></p>{/if}
  <p class="issue-link"><a href="https://github.com/eliperez-dev/UntilEveryCage/issues/new" target="_blank" rel="noreferrer">Report a public issue on GitHub ↗</a></p>
</section>

<style>
  .bug-page{width:min(100% - 3rem,48rem);margin:0 auto;padding:1.5rem 0 2.5rem;color:#f1efe8;font:.9rem/1.5 ui-sans-serif,system-ui,sans-serif}.bug-page a{color:#dce8d9;text-underline-offset:.25em}.bug-page h1{margin:.4rem 0 .75rem;font:400 clamp(1.65rem,4vw,2rem)/1.08 Georgia,serif;letter-spacing:-.035em}.intro{max-width:42rem;color:#d3dbd1;font-size:.9rem}.bug-form{display:grid;gap:.75rem;margin-top:.75rem}.bug-form label{display:grid;gap:.4rem;color:#e6e2d8;font-size:.9rem}.bug-form textarea,.bug-form input{width:100%;padding:.45rem .6rem;border:1px solid #59615c;border-radius:2px;background:#202523;color:#f4f1e9;font:inherit}.bug-form textarea{resize:vertical}.bug-form :focus-visible{outline:3px solid #d49a62;outline-offset:2px}.bug-form button{width:max-content;min-height:2.5rem;padding:.55rem 1rem;border:1px solid #c58a58;border-radius:2px;background:#8f553d;color:#fff;font:600 .9rem system-ui;cursor:pointer}.draft-link,.issue-link{margin-top:1.3rem}.draft-link a{display:inline-flex;padding:.7rem .9rem;border:1px solid #9a7556;background:#262b27}.issue-link{color:#bec8bf;font-size:.88rem}@media(max-width:40rem){.bug-page{width:min(100% - 2rem,48rem)}}
.bug-page.embedded{width:100%;margin:0;padding:0}
</style>
