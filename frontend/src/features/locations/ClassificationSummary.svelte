<script lang="ts">
  import { language, tr } from '../../app/language';
  import { classificationSummary, type ClassificationRecord } from './classificationSummary';
  import { classificationExplanation } from './classificationExplanation';
  let { record, presentation = 'all' }: { record: ClassificationRecord; presentation?: 'all' | 'summary' | 'details' } = $props();
  const classification = $derived(classificationSummary(record, label => tr(label, $language)));
  const explanation = $derived(classificationExplanation(record, label => tr(label, $language), $language));
</script>

<div class="classification-summary">
  {#if presentation !== 'details'}
    <p class="summary" data-classification-explanation>{explanation.text}</p>
  {/if}
  {#if presentation !== 'summary'}
    <details>
      <summary>{tr('Classification details', $language)}</summary>
      <dl>
        {#if classification.categories.length > 1}<div><dt>{tr('Categories', $language)}</dt><dd>{classification.categories.join(', ')}</dd></div>{/if}
        {#if classification.supportingActivities.length}<div><dt>{tr('Activity classification', $language)}</dt><dd>{classification.supportingActivities.join(', ')}</dd></div>{/if}
        {#if classification.sourceLabels.length}<div><dt>{tr('Source classification', $language)}</dt><dd>{classification.sourceLabels.join(' · ')}</dd></div>{/if}
        <div><dt>{tr('Category definitions', $language)}</dt><dd class="references">{#each explanation.references as reference}<a href={reference.href} target={reference.href.startsWith('https:') ? '_blank' : undefined} rel={reference.href.startsWith('https:') ? 'noopener noreferrer' : undefined}>{tr(reference.label, $language)}</a>{/each}</dd></div>
      </dl>
    </details>
  {/if}
</div>

<style>
  .classification-summary { font: inherit; color: inherit; }
  .summary { margin: .3rem 0 .5rem; line-height: 1.55; overflow-wrap: anywhere; }
  .references { display:flex;flex-direction:column;align-items:flex-start; }
  .references a { display:inline-flex;align-items:center;min-height:2.75rem;text-underline-offset:3px; }
  details { margin-top: .2rem; }
  summary { display: list-item; width: fit-content; min-height: 2.75rem; padding: .65rem 0; cursor: pointer; font-size: .75rem; }
  summary:focus-visible { outline: 2px solid currentColor; outline-offset: 3px; }
  dl { margin: 0 0 .5rem; }
  dl div { display: grid; grid-template-columns: minmax(5rem, 30%) minmax(0, 1fr); gap: .6rem; padding: .3rem 0; }
  dt { color: var(--ui-muted, var(--ink-muted, #aeb0b0)); font: 400 .75rem/1.5 system-ui, sans-serif; }
  dd { margin: 0; font: inherit; line-height: 1.5; overflow-wrap: anywhere; }
  @media (max-width: 25rem) { dl div { grid-template-columns: 1fr; gap: .15rem; } }
</style>
