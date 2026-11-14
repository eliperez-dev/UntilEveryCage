<script lang="ts">
  import type { LabFilters } from '../../design-lab/contract';
  import type { CandidateFacets } from '../../api/TestReleaseRepository';
  import { CATEGORY_PRESENTATIONS } from '../locations/categoryPresentation';
  import { language, tr } from '../../app/language';
  let { filters, sourceId, facets, facetsStatus, onchange, onclose }: {
    filters:LabFilters; sourceId:string|null; facets:CandidateFacets|null;
    facetsStatus:'loading'|'ready'|'error'|'unauthorized';
    onchange(value:{filters:LabFilters;sourceId:string|null}):void; onclose():void;
  } = $props();
  const names:Record<string,string>={slaughter:'Slaughter',animal_keeping_and_production:'Animal keeping',processing_and_preparation:'Processing',research_and_animal_use:'Research',other_regulated_premises:'Other premises',unclassified:'Unclassified'};
  function toggle(field:'categories'|'countries'|'sources', value:string, checked:boolean) {
    const selected = checked ? [...new Set([...filters[field], value])] : filters[field].filter(item => item !== value);
    onchange({filters: {...filters, [field]: selected}, sourceId: field === 'sources' && value === sourceId ? null : sourceId});
  }
  function country(value:string) { try { return new Intl.DisplayNames([$language],{type:'region'}).of(value)??value; } catch { return value; } }
  const countryChoices = $derived([
    ...(facets?.countries ?? []),
    ...filters.countries.filter(value => !facets?.countries.some(facet => facet.value === value)).map(value => ({ value, count: 0 })),
  ]);
  const selectedSources = $derived([...new Set([...(sourceId ? [sourceId] : []), ...filters.sources])]);
  const sourceChoices = $derived([
    ...(facets?.sources ?? []),
    ...selectedSources.filter(value => !facets?.sources.some(facet => facet.value === value)).map(value => ({ value, count: 0, label: value })),
  ]);
  function sourceName(value: string) { return facets?.sources.find(facet => facet.value === value)?.label ?? value; }
  function clear() { onchange({filters: {categories:[],countries:[],sources:[],activities:[],precisions:[]}, sourceId: null}); }
</script>
<section class="mobile-filter-view" aria-labelledby="mobile-filter-title">
  <header><h2 id="mobile-filter-title">{tr('Filters',$language)}</h2><button type="button" aria-label={tr('Close',$language)} onclick={onclose}>×</button></header>
  <div class="mobile-filter-scroll">
    {#if facetsStatus==='loading'}<p role="status">{tr('Loading filters…',$language)}</p>{:else if facetsStatus==='error'||facetsStatus==='unauthorized'}<p role="status">{tr('Filters are unavailable. Search remains available.',$language)}</p>{/if}
    <fieldset><legend>{tr('Activity category',$language)}</legend>{#each Object.entries(CATEGORY_PRESENTATIONS) as [key,presentation]}<label><input type="checkbox" checked={filters.categories.includes(key)} onchange={event=>toggle('categories',key,event.currentTarget.checked)} /><span class="swatch" style:background={presentation.color}></span><span>{tr(names[key]??presentation.label,$language)}</span></label>{/each}</fieldset>
    <details><summary>{tr('Country',$language)}<span>{filters.countries.length?filters.countries.map(country).join(', '):tr('All countries',$language)}</span></summary><fieldset class="one-column">{#each countryChoices as facet(facet.value)}<label><input type="checkbox" checked={filters.countries.includes(facet.value)} onchange={event=>toggle('countries',facet.value,event.currentTarget.checked)} />{country(facet.value)} <small>{new Intl.NumberFormat($language).format(facet.count)}</small></label>{/each}</fieldset></details>
    <details><summary>{tr('Source',$language)}<span>{selectedSources.length?selectedSources.map(sourceName).join(', '):tr('All sources',$language)}</span></summary><fieldset class="one-column">{#each sourceChoices as facet(facet.value)}<label><input type="checkbox" checked={selectedSources.includes(facet.value)} onchange={event=>toggle('sources',facet.value,event.currentTarget.checked)} />{facet.label??facet.value} <small>{new Intl.NumberFormat($language).format(facet.count)}</small></label>{/each}</fieldset></details>
  </div>
  <footer><button type="button" onclick={clear}>{tr('Clear filters',$language)}</button></footer>
</section>
<style>
  .mobile-filter-view{display:flex;flex:1;min-height:0;flex-direction:column;background:var(--panel);color:var(--ink)}
  header{display:flex;align-items:center;justify-content:space-between;min-height:44px;flex:none;padding:0 .85rem .35rem;border-bottom:1px solid var(--line)}h2{font:600 .875rem/1.4 system-ui,sans-serif;margin:0}button{min-height:44px;border:0;background:none;color:var(--ink);font:inherit;font-size:.75rem;cursor:pointer}header button{width:44px;font-size:1.3rem;color:var(--muted)}
  .mobile-filter-scroll{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:0 .85rem .6rem}fieldset{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 .65rem;margin:.55rem 0 .7rem;padding:0;border:0;min-width:0}legend{padding:.3rem 0;font-size:.9375rem;font-weight:600}label{display:flex;align-items:center;gap:.45rem;min-height:44px;font-size:.9375rem;line-height:1.35;overflow-wrap:anywhere;min-width:0}input{width:16px;height:16px;flex:none;margin:0;accent-color:var(--ink)}.swatch{width:6px;height:6px;border-radius:50%;flex:none}.one-column{grid-template-columns:minmax(0,1fr);margin:.2rem 0}.one-column small{margin-left:auto;color:var(--muted);font-variant-numeric:tabular-nums}
  details{border-top:1px solid var(--line)}summary{display:flex;align-items:center;justify-content:space-between;gap:.65rem;min-height:44px;font-size:.75rem;cursor:pointer;list-style:none}summary::after{content:'⌄';color:var(--muted);flex:none}summary>span{max-width:65%;min-width:0;margin-left:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)}summary::-webkit-details-marker{display:none}p{font-size:.75rem;line-height:1.5;color:var(--muted)}
  footer{flex:none;padding:0 .85rem env(safe-area-inset-bottom);border-top:1px solid var(--line)}footer button{padding:0 .55rem}button:focus-visible,input:focus-visible,summary:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
</style>
