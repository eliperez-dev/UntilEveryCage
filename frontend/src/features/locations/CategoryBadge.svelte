<script lang="ts">
  import { language, tr } from '../../app/language';
  import { recordCategoryIdentity, type ClassificationRecord } from './classificationSummary';
  let { record, onfilter }: { record: ClassificationRecord; onfilter?: ((key: string) => void) | undefined } = $props();
  const category = $derived(recordCategoryIdentity(record));
</script>

{#if onfilter}
  <button type="button" class="category-badge" onclick={() => onfilter?.(category.key)}><img src={`${import.meta.env.BASE_URL}v1-pins/${category.pinFile}`} alt="" width="14" height="23" /><span>{tr(category.label, $language)}</span></button>
{:else}
  <span class="category-badge"><img src={`${import.meta.env.BASE_URL}v1-pins/${category.pinFile}`} alt="" width="14" height="23" /><span>{tr(category.label, $language)}</span></span>
{/if}

<style>
  .category-badge { display: inline-flex; align-items: center; gap: .5rem; max-width: 100%; min-width: 0; color: inherit; font: 500 calc(.75rem * var(--result-type-scale, 1))/1.4 system-ui, sans-serif; }
  .category-badge img { flex: none; width: 14px; height: 23px; object-fit: contain; }
  .category-badge span { overflow-wrap: anywhere; }
  button.category-badge { min-height: 2.75rem; padding: 0; border: 0; background: transparent; text-align: left; cursor: pointer; }
  button:hover span { text-decoration: underline; text-underline-offset: .2em; }
  button:focus-visible { outline: 2px solid currentColor; outline-offset: 3px; }
</style>
