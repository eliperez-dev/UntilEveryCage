<script lang="ts">
  import type { AreaSummary } from '../../design-lab/contract';
  import type { TaxonomyPrimaryKey } from '../../domain/taxonomy';
  import { CATEGORY_PRESENTATIONS } from '../locations/categoryPresentation';
  import { language, tr } from '../../app/language';
  let { summary, selectedCategories, nearby = false, canUpdate = false, oncategory, onclear, onupdate }: {
    summary: AreaSummary | null;
    selectedCategories: readonly string[];
    nearby?: boolean;
    canUpdate?: boolean;
    oncategory(key: TaxonomyPrimaryKey): void;
    onclear(): void;
    onupdate(): void;
  } = $props();
  const names: Record<TaxonomyPrimaryKey, string> = { slaughter:'Slaughter', animal_keeping_and_production:'Animal keeping', processing_and_preparation:'Processing', research_and_animal_use:'Research', other_regulated_premises:'Other premises', unclassified:'Unclassified' };
  const order: readonly TaxonomyPrimaryKey[] = ['slaughter','animal_keeping_and_production','processing_and_preparation','research_and_animal_use','other_regulated_premises','unclassified'];
  const counts = $derived(new Map(summary?.categories.map(category => [category.key, category.count]) ?? []));
  const largest = $derived(Math.max(1, ...counts.values()));
  const number = (value: number) => new Intl.NumberFormat($language).format(value);
</script>

<section class="area-summary" aria-labelledby="area-summary-title" aria-busy={!summary || summary.status === 'loading'}>
  <div class="area-heading"><h2 id="area-summary-title">{tr(nearby ? 'Near you' : 'In this area', $language)}</h2><button class="clear-area" type="button" onclick={onclear}>{tr('Clear area', $language)}</button></div>
  {#if summary?.status === 'ready'}
    <p class="area-total"><strong>{number(summary.total)}</strong><span>{tr('matching mapped records', $language)}</span></p>
    <div class="area-breakdown" role="group" aria-label={tr('Activity breakdown', $language)}>
      {#each order as key}
        {@const count = counts.get(key) ?? 0}
        <button type="button" class="category-row" class:selected={selectedCategories.includes(key)} aria-pressed={selectedCategories.includes(key)} aria-label={`${tr(names[key], $language)}: ${number(count)}`} style:--category-color={CATEGORY_PRESENTATIONS[key].color} style:--category-share={`${count / largest * 100}%`} onclick={() => oncategory(key)}><span class="category-name">{tr(names[key], $language)}</span><span class="category-count">{number(count)}</span><span class="category-bar" aria-hidden="true"></span></button>
      {/each}
    </div>
    <details class="area-evidence"><summary>{tr('{count} sources', $language).replace('{count}', number(summary.sourceCount))} · {tr('Location precision', $language)}</summary><dl><div><dt>{tr('Source-reported', $language)}</dt><dd>{number(summary.sourceReportedCount)}</dd></div><div><dt>{tr('Approximate', $language)}</dt><dd>{number(summary.approximateCount)}</dd></div></dl></details>
  {:else if summary?.status === 'error'}<p class="area-state" role="status">{tr('Area summary unavailable.', $language)}</p>
  {:else}<p class="area-state" role="status">{tr('Counting records…', $language)}</p>{/if}
  {#if !nearby}<button class="update-area" type="button" disabled={!canUpdate} onclick={onupdate}>{tr('Update to this view', $language)}<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><path d="M8 12h8m-4-4v8"/></svg></button>{/if}
</section>

<style>
  .area-summary { padding:1rem 1rem .7rem;border-bottom:1px solid var(--line); }
  .area-heading { display:flex;align-items:center;justify-content:space-between;gap:1rem; }
  h2 { margin:0;font:400 1.6rem/1.2 Georgia,serif;letter-spacing:-.025em; }
  button { color:var(--ink);background:transparent;border:0;font:inherit;cursor:pointer; }
  button:focus-visible,summary:focus-visible { outline:2px solid var(--ink);outline-offset:2px; }
  .clear-area { min-height:44px;padding:.4rem 0;font-size:.75rem;text-decoration:underline;text-underline-offset:3px; }
  .area-total { display:flex;align-items:baseline;gap:.65rem;margin:.15rem 0 .8rem; }
  .area-total strong { font:400 2.7rem/1 Georgia,serif;letter-spacing:-.04em; }
  .area-total span { color:var(--ui-muted,var(--muted));font-size:.75rem; }
  .area-breakdown { display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:.15rem 1.2rem; }
  .category-row { position:relative;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:.2rem .5rem;min-height:44px;padding:.45rem 0 .55rem;text-align:left; }
  .category-name { font-size:.75rem;line-height:1.3; }
  .category-count { font-variant-numeric:tabular-nums;font-size:.75rem; }
  .category-bar { grid-column:1/-1;height:3px;background:var(--line);overflow:hidden; }
  .category-bar::after { content:'';display:block;width:var(--category-share);height:100%;background:var(--category-color); }
  .category-row.selected .category-name { text-decoration:underline;text-underline-offset:3px; }
  .category-row:hover .category-name { text-decoration:underline; }
  .area-evidence { margin-top:.3rem;font-size:.6875rem;color:var(--ui-muted,var(--muted)); }
  .area-evidence summary { min-height:36px;display:flex;align-items:center;cursor:pointer; }
  .area-evidence summary::after { content:'+';margin-left:auto;font-size:1rem; }
  .area-evidence[open] summary::after { content:'−'; }
  dl { margin:.2rem 0 .6rem;display:flex;flex-wrap:wrap;gap:.4rem 1.2rem; }
  dl div { display:flex;gap:.4rem; } dd { margin:0;color:var(--ink);font-variant-numeric:tabular-nums; }
  .area-state { min-height:5rem;display:flex;align-items:center;color:var(--ui-muted,var(--muted));font-size:.8rem; }
  .update-area { min-height:44px;width:100%;display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--line);font-size:.75rem;text-align:left;padding:.5rem 0; }
  .update-area svg { width:1rem;height:1rem;fill:none;stroke:currentColor;stroke-width:1.5; }
  .update-area:disabled { opacity:.4;cursor:default; }
  @media(min-width:40rem) { .area-summary { padding:1.1rem 1.2rem .65rem; } }
</style>
