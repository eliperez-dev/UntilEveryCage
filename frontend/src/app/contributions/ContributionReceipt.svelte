<script lang="ts">
  import type { Receipt } from '../../api/CommunityRepository';
  import { language, tr } from '../language';
  import { trackingHref } from './contributionForm';
  let { receipt, returnMapHref = '#/map', bug = false, onanother }: { receipt: Receipt; returnMapHref?: string; bug?: boolean; onanother?(): void } = $props();
  let copyState = $state<'idle' | 'copied' | 'failed'>('idle');
  const href = $derived(trackingHref(receipt, returnMapHref));
  async function copy() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error();
      await navigator.clipboard.writeText(new URL(href, window.location.href).href);
      copyState = 'copied';
    } catch { copyState = 'failed'; }
  }
</script>
<section class="contribution-receipt" aria-labelledby="receipt-heading" aria-live="polite">
  <p class="eyebrow">{tr(bug ? 'Report saved.' : 'Submission received', $language)}</p>
  <h1 id="receipt-heading">{tr('Contribution received', $language)}</h1>
  <p class="intro">{tr('Thank you. Your submission is waiting for review.', $language)}</p>
  <p class="reference">{tr('Reference', $language)} <span>{receipt.submission_id}</span></p>
  <div class="tracking">
    <div class="actions"><a class="primary" href={href}>{tr(bug ? 'Track report' : 'Track submission', $language)} <span aria-hidden="true">→</span></a><button type="button" onclick={copy}>{tr(copyState === 'copied' ? 'Copied' : 'Copy tracking link', $language)}</button></div>
    <p>{tr('Keep this private link. The reference alone won’t open your submission.', $language)}</p>
    {#if copyState === 'failed'}<p class="copy-error" role="alert">{tr('The link could not be copied. Open Track submission and copy the address instead.', $language)}</p>{/if}
  </div>
  <p class="next">{tr('We review submissions before changing records or publishing claims.', $language)}</p>
  {#if onanother}<button type="button" class="text-action" onclick={onanother}>{tr('Make another contribution', $language)}</button>{/if}
</section>
<style>
  .contribution-receipt{max-width:40rem;margin:0 auto;padding:1rem 0;color:var(--ink);font:.9rem/1.5 system-ui,sans-serif}.eyebrow{margin:0 0 1rem;color:var(--ink-muted);font-size:.75rem;text-transform:uppercase;letter-spacing:.1em}h1{font:400 clamp(2rem,5vw,2.6rem)/1.15 Georgia,serif;letter-spacing:-.035em;margin:0 0 .8rem}.intro{color:var(--ink-secondary)}.reference{margin:1.8rem 0 .9rem;font-size:.8rem;color:var(--ink-muted)}.reference span{display:block;overflow-wrap:anywhere;color:var(--ink);margin-top:.3rem}.tracking{padding:1.3rem 0;border-block:1px solid var(--line)}.actions{display:flex;align-items:center;flex-wrap:wrap;gap:.75rem}.actions a,.actions button{min-height:2.75rem;padding:.65rem 1rem;border:1px solid var(--line-strong);background:transparent;color:var(--ink);font:inherit;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;cursor:pointer}.actions .primary{background:var(--ink);color:var(--page);border-color:var(--ink)}.tracking p,.next{font-size:.8rem;color:var(--ink-muted);margin:.85rem 0 0}.next{margin:1.2rem 0}.copy-error{color:var(--ink)!important}.text-action{min-height:2.75rem;padding:.4rem 0;background:transparent;color:var(--ink);border:0;font:inherit;text-decoration:underline;text-underline-offset:.25em}.actions button:hover,.text-action:hover{background:var(--panel-hover)}:is(a,button):focus-visible{outline:3px solid var(--focus);outline-offset:3px}@media(max-width:36rem){.actions{align-items:stretch}.actions a,.actions button{width:100%}.actions{display:grid;grid-template-columns:minmax(0,1fr)}.contribution-receipt{padding-top:0}}
</style>
