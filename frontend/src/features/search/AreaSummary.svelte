<script lang="ts">
  import type { AreaSummary } from '../../design-lab/contract';
  import type { TaxonomyPrimaryKey } from '../../domain/taxonomy';
  import { CATEGORY_PRESENTATIONS } from '../locations/categoryPresentation';
  import { language, tr } from '../../app/language';
  let { summary, selectedCategories, nearby = false, radiusKm = null, oncategory }: {
    summary: AreaSummary | null;
    selectedCategories: readonly string[];
    nearby?: boolean;
    radiusKm?: number | null;
    oncategory(key: TaxonomyPrimaryKey): void;
  } = $props();
  const names: Record<TaxonomyPrimaryKey, string> = { slaughter:'Slaughter', animal_keeping_and_production:'Animal keeping', processing_and_preparation:'Processing', research_and_animal_use:'Research', other_regulated_premises:'Other premises', unclassified:'Unclassified' };
  const order: readonly TaxonomyPrimaryKey[] = ['slaughter','animal_keeping_and_production','processing_and_preparation','research_and_animal_use','other_regulated_premises','unclassified'];
  const counts = $derived(new Map(summary?.categories.map(category => [category.key, category.count]) ?? []));
  const largest = $derived(Math.max(1, ...counts.values()));
  const number = (value: number) => new Intl.NumberFormat($language).format(value);
</script>

<section class="area-summary" aria-labelledby="area-summary-title" aria-busy={!summary || summary.status === 'loading'}>
  <div class="area-heading"><div class="scope-context"><h2 id="area-summary-title">{tr(nearby ? 'Near you' : 'In this area', $language)}</h2>{#if radiusKm !== null}<span class="scope-radius">{tr('{count} mile radius', $language).replace('{count}', number(Math.round(radiusKm / 1.609344)))}</span>{/if}</div></div>
  {#if summary?.status === 'ready'}
    <p class="area-total"><strong>{number(summary.total)}</strong><span>{tr('matching mapped records', $language)}</span></p>
    <details class="area-details"><summary title={tr('Activity breakdown', $language)}><span>{tr('Activity breakdown', $language)}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary>
    <div class="area-breakdown" role="group" aria-label={tr('Activity breakdown', $language)}>
      {#each order as key}
        {@const count = counts.get(key) ?? 0}
        <button type="button" class="category-row" class:selected={selectedCategories.includes(key)} aria-pressed={selectedCategories.includes(key)} aria-label={`${tr(names[key], $language)}: ${number(count)}`} style:--category-color={CATEGORY_PRESENTATIONS[key].color} style:--category-share={`${count / largest * 100}%`} onclick={() => oncategory(key)}><span class="category-name">{tr(names[key], $language)}</span><span class="category-count">{number(count)}</span><span class="category-bar" aria-hidden="true"></span></button>
      {/each}
    </div>
    <div class="area-evidence"><p>{tr('{count} sources', $language).replace('{count}', number(summary.sourceCount))} · {tr('Location precision', $language)}</p><dl><div><dt>{tr('Source-reported', $language)}</dt><dd>{number(summary.sourceReportedCount)}</dd></div><div><dt>{tr('Approximate', $language)}</dt><dd>{number(summary.approximateCount)}</dd></div></dl></div></details>
  {:else if summary?.status === 'error'}<p class="area-state" role="status">{tr('Area summary unavailable.', $language)}</p>
  {:else}<p class="area-state" role="status">{tr('Counting records…', $language)}</p>{/if}
</section>

<style>
  .area-summary { position:relative;flex:none;padding:.45rem 1rem .25rem;border-bottom:1px solid var(--line); }
  .area-heading { display:flex;align-items:center;justify-content:space-between;gap:.5rem;min-height:32px; }
  .scope-context { display:flex;align-items:baseline;flex-wrap:wrap;gap:.15rem .5rem;min-width:0; }
  h2 { margin:0;font:400 1.15rem/1.2 Georgia,serif;letter-spacing:-.025em; }
  .scope-radius { color:var(--ui-muted,var(--muted));font-size:.6875rem;white-space:nowrap; }
  button { color:var(--ink);background:transparent;border:0;font:inherit;cursor:pointer; }
  button:focus-visible,summary:focus-visible { outline:2px solid var(--ink);outline-offset:2px; }
  svg { width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.5;flex:none; }
  .area-total { display:flex;align-items:baseline;gap:.4rem;margin:0;min-height:27px;padding-right:8rem; }
  .area-total strong { font:400 1.5rem/1 Georgia,serif;letter-spacing:-.04em; }
  .area-total span { color:var(--ui-muted,var(--muted));font-size:.6875rem; }
  .area-details > summary { display:flex;align-items:center;gap:.4rem;min-height:44px;width:fit-content;max-width:9rem;margin:-36px 0 0 auto;font-size:.6875rem;cursor:pointer;list-style:none; }
  .area-details > summary::-webkit-details-marker { display:none; }
  .area-details[open] > summary svg { transform:rotate(180deg); }
  .area-breakdown { display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:.15rem 1.2rem; }
  .category-row { position:relative;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:.2rem .5rem;min-height:44px;padding:.45rem 0 .55rem;text-align:left; }
  .category-name { font-size:.75rem;line-height:1.3; }
  .category-count { font-variant-numeric:tabular-nums;font-size:.75rem; }
  .category-bar { grid-column:1/-1;height:3px;background:var(--line);overflow:hidden; }
  .category-bar::after { content:'';display:block;width:var(--category-share);height:100%;background:var(--category-color); }
  .category-row.selected .category-name { text-decoration:underline;text-underline-offset:3px; }
  .category-row:hover .category-name { text-decoration:underline; }
  .area-evidence { margin-top:.3rem;font-size:.6875rem;color:var(--ui-muted,var(--muted)); }
  .area-evidence p { margin:.5rem 0; }
  dl { margin:.2rem 0 .6rem;display:flex;flex-wrap:wrap;gap:.4rem 1.2rem; }
  dl div { display:flex;gap:.4rem; } dd { margin:0;color:var(--ink);font-variant-numeric:tabular-nums; }
  .area-state { min-height:27px;margin:0 0 .4rem;display:flex;align-items:center;color:var(--ui-muted,var(--muted));font-size:.75rem; }
  @media(max-width:40rem) { .area-total { padding-right:0; } .area-total span { max-width:11rem; } .area-details > summary { max-width:none;min-height:36px;margin:0; } }
  @media(max-width:40rem) and (max-height:700px) {
    .area-summary { padding:.25rem .65rem; }
    .area-heading { padding-right:44px;min-height:44px; }
    .scope-context { flex-direction:column;gap:.1rem;align-items:flex-start; }
    h2 { font-size:1rem; }
    .scope-radius { font-size:.625rem; }
    .area-details > summary span { position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap; }
    .area-total { position:absolute;top:17px;left:46%;min-height:0; }
    .area-total strong { font-size:1.15rem; }
    .area-total span { position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap; }
    .area-details > summary { position:absolute;right:.65rem;top:.25rem;width:44px;height:44px;justify-content:center; }
    .area-details[open] { padding-top:.5rem; }
  }
</style>
