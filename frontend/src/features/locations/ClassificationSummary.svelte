<script lang="ts">
  import { language, tr } from '../../app/language';
  import { classificationSummary, type ClassificationRecord } from './classificationSummary';
  let { record }: { record: ClassificationRecord } = $props();
  const classification = $derived(classificationSummary(record, label => tr(label, $language)));
</script>

<div class="classification-summary">
  {#if classification.summary}<p class="summary">{classification.summary}</p>{/if}
  {#if !classification.summary && !classification.supportingActivities.length && !classification.sourceLabels.length}<p class="summary">{tr('Activity details not provided', $language)}</p>{/if}
  {#if classification.activities.length && classification.hasAphisClassification}<p class="additional-activities"><span>{tr('Recorded activities', $language)}:</span> {classification.activities.join(', ')}</p>{/if}
  {#if classification.supportingActivities.length || classification.sourceLabels.length || classification.categories.length > 1}
    <details>
      <summary>{tr('Classification details', $language)}</summary>
      <dl>
        {#if classification.categories.length > 1}<div><dt>{tr('Categories', $language)}</dt><dd>{classification.categories.join(', ')}</dd></div>{/if}
        {#if classification.supportingActivities.length}<div><dt>{tr('Activity classification', $language)}</dt><dd>{classification.supportingActivities.join(', ')}</dd></div>{/if}
        {#if classification.sourceLabels.length}<div><dt>{tr('Source classification', $language)}</dt><dd>{classification.sourceLabels.join(' · ')}</dd></div>{/if}
      </dl>
    </details>
  {/if}
</div>

<style>
  .classification-summary { font: inherit; color: inherit; }
  .summary, .additional-activities { margin: .3rem 0 .5rem; line-height: 1.55; overflow-wrap: anywhere; }
  details { margin-top: .2rem; }
  summary { display: list-item; width: fit-content; min-height: 2.75rem; padding: .65rem 0; cursor: pointer; font-size: .75rem; }
  summary:focus-visible { outline: 2px solid currentColor; outline-offset: 3px; }
  dl { margin: 0 0 .5rem; }
  dl div { display: grid; grid-template-columns: minmax(5rem, 30%) minmax(0, 1fr); gap: .6rem; padding: .3rem 0; }
  dt { color: var(--ui-muted, var(--ink-muted, #aeb0b0)); font: 400 .75rem/1.5 system-ui, sans-serif; }
  dd { margin: 0; font: inherit; line-height: 1.5; overflow-wrap: anywhere; }
  @media (max-width: 25rem) { dl div { grid-template-columns: 1fr; gap: .15rem; } }
</style>
