<script lang="ts">
  import { language, tr } from './language';
  import type { Receipt } from '../api/CommunityRepository';
  import ContributionForm from './contributions/ContributionForm.svelte';
  import ContributionReceipt from './contributions/ContributionReceipt.svelte';
  import { emptyIntakeDraft } from './contributions/contributionForm';
  let { returnMapHref = '#/map', embedded = false }: { returnMapHref?: string; embedded?: boolean } = $props();
  let draft = $state(emptyIntakeDraft()), receipt = $state<Receipt | null>(null);
</script>
<svelte:head><title>{tr('Report a bug', $language)} · Until Every Cage</title></svelte:head>
<section class="bug-page" class:embedded aria-label={tr('Report a bug', $language)}>
  {#if receipt}<ContributionReceipt {receipt} {returnMapHref} bug onanother={() => { receipt = null; draft = emptyIntakeDraft(); }} />
  {:else}<ContributionForm kind="bug" bind:draft {returnMapHref} onreceived={value => { receipt = value; draft = emptyIntakeDraft(); }} />{/if}
  <p class="issue-link"><a href="https://github.com/eliperez-dev/UntilEveryCage/issues/new" target="_blank" rel="noreferrer">{tr('Report a public issue on GitHub ↗', $language)}</a></p>
</section>
<style>
  .bug-page{width:min(100% - 3rem,48rem);margin:0 auto;padding:1.5rem 0 2.5rem;color:var(--ink);font:.9rem/1.5 system-ui,sans-serif}.bug-page.embedded{width:100%;margin:0;padding:0}.issue-link{margin-top:1.5rem;font-size:.8rem}.issue-link a{color:var(--ink);text-underline-offset:.25em;display:inline-flex;align-items:center;min-height:2.75rem}.issue-link a:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
</style>
