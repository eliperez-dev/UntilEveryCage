<script lang="ts">
  import { onMount } from 'svelte';
  import { LocalLocationRepository } from '../api/LocalLocationRepository';
  import type { Location } from '../domain/location';
  import { TAXONOMY_PRIMARY_KEYS, type TaxonomyPrimaryKey } from '../domain/taxonomy';
  import { CATEGORY_PRESENTATIONS } from '../features/locations/categoryPresentation';
  import RecordTable from './RecordTable.svelte';
  import { serializeRoute } from './routeState';
  import CopyValue from './CopyValue.svelte';
  import { precisionPresentation } from '../features/locations/precisionPresentation';
  let { onrelease }: { onrelease?: (label: string | null) => void } = $props();
  const repository = new LocalLocationRepository();
  let query = $state('');
  let categories = $state<readonly TaxonomyPrimaryKey[]>([]);
  let records = $state<readonly Location[]>([]);
  let selectedId = $state<string | null>(null);
  let cursor = $state<string | null>(null);
  let totalCount = $state<number | null>(null);
  let pageSize = $state<25 | 50 | 100>(50);
  let releaseId = $state<string | undefined>();
  let coverage = $state('');
  let busy = $state(false);
  let error = $state('');
  let unavailable = $state(false);
  let controller: AbortController;
  let timer: ReturnType<typeof setTimeout>;
  const selected = $derived(records.find(record => record.id === selectedId));
  const precision = (record: Location) => precisionPresentation(record.evidence?.displayPrecision);
  const listingActivity = (record: Location) => record.taxonomy?.leafActivities.map(activity => activity.label).join(' · ') || (record.category === 'unclassified' ? '' : record.category);
  const detailActivity = (record: Location) => listingActivity(record) || 'Category not provided';
  async function load(reset = true) {
    controller?.abort(); controller = new AbortController(); const current = controller;
    busy = true; error = ''; unavailable = false;
    if (reset) { records = []; cursor = null; totalCount = null; releaseId = undefined; selectedId = null; }
    try {
      const result = await repository.list('official', { q: query, category_keys: categories, limit: pageSize, ...(cursor ? { cursor } : {}) }, current.signal, releaseId);
      if (current.signal.aborted) return;
      records = [...new Map([...(reset ? [] : records), ...result.locations].map(record => [record.id, record])).values()];
      cursor = result.nextCursor; releaseId = result.releaseId; onrelease?.(result.releaseId); coverage = result.coverageNote;
      const counted = (result as unknown as { totalCount?: unknown }).totalCount;
      totalCount = typeof counted === 'number' ? counted : records.length;
    } catch (cause) {
      if (current.signal.aborted) return;
      unavailable = !!cause && typeof cause === 'object' && 'kind' in cause && cause.kind === 'no-release';
      error = unavailable ? 'No eligible public release is available yet.' : 'Records could not be loaded. Try again.';
    } finally { if (current === controller) busy = false; }
  }
  function toggleCategory(key: TaxonomyPrimaryKey, checked: boolean) { categories = checked ? [...new Set([...categories, key])] : categories.filter(value => value !== key); void load(); }
  function search(value: string) { query = value; clearTimeout(timer); timer = setTimeout(() => void load(), 180); }
  function clear() { clearTimeout(timer); query = ''; categories = []; void load(); }
  function setPageSize(value: string) { pageSize = Number(value) as 25 | 50 | 100; void load(); }
  const recordRoute = (id: string) => serializeRoute({kind:'record',facilityId:id,profile:'official',...(releaseId ? {releaseId} : {})});
  const recordHref = (id: string) => `${window.location.origin}${window.location.pathname}${recordRoute(id)}`;
  onMount(() => { void load(); return () => { controller?.abort(); clearTimeout(timer); }; });
</script>
<svelte:head><title>Browse records · Until Every Cage</title></svelte:head>
<section class="public-database" aria-labelledby="browse-title">
  <h1 id="browse-title">Browse records</h1><p class="intro">Search the curated public release by name, activity, source, or place.</p>
  <div class="browse-layout" class:has-selection={!!selected}>
    <aside class="filters" aria-label="Research filters"><label for="public-query">Search records</label><input id="public-query" type="search" placeholder="Name, activity, source, or place…" value={query} oninput={event => search(event.currentTarget.value)} /><fieldset><legend>Activity category</legend>{#each TAXONOMY_PRIMARY_KEYS.filter(key => key !== 'unclassified') as key}<label><input type="checkbox" checked={categories.includes(key)} onchange={event => toggleCategory(key, event.currentTarget.checked)} /> {CATEGORY_PRESENTATIONS[key].label}</label>{/each}</fieldset>{#if query || categories.length}<div class="active-filters" aria-label="Selected filters">{#if query}<button type="button" onclick={() => search('')}>Search: {query} ×</button>{/if}{#each categories as key}<button type="button" onclick={() => toggleCategory(key, false)}>{CATEGORY_PRESENTATIONS[key].label} ×</button>{/each}<button type="button" onclick={clear}>Clear filters</button></div>{/if}</aside>
    <div class="results" aria-live="polite"><div class="result-count"><span>{busy ? 'Loading records…' : `${(totalCount ?? 0).toLocaleString()} matching ${totalCount === 1 ? 'record' : 'records'}`}</span><label>Rows <select value={pageSize} onchange={event => setPageSize(event.currentTarget.value)}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label></div>{#if error}<p role={unavailable ? 'status' : 'alert'}>{error}</p>{#if !unavailable}<button type="button" onclick={() => void load()}>Retry</button>{/if}{:else if !busy && !records.length}<p>No eligible records match these filters in this release. This does not establish that no facility exists.</p>{:else}<RecordTable records={records.map(record => ({ id: record.id, name: record.name, activity: listingActivity(record), place: record.region, source: record.source }))} {selectedId} onselect={id => selectedId = id} />{/if}{#if cursor}<button disabled={busy} type="button" onclick={() => void load(false)}>Load more</button>{/if}{#if releaseId}<p class="coverage">Release {releaseId} · {coverage}</p>{/if}</div>
    {#if selected}<aside class="selected" aria-label="Selected record"><button type="button" onclick={() => selectedId = null}>Close details</button><h2>{selected.name}</h2><p>{selected.region} · {precision(selected)}</p><dl><dt>Activity</dt><dd>{detailActivity(selected)}</dd><dt>Source</dt><dd>{selected.source}{#if selected.evidence?.sourceUrl} · <a href={selected.evidence.sourceUrl} target="_blank" rel="noreferrer">Open source</a>{/if}</dd><dt>Observed</dt><dd>{selected.observed}</dd><dt>Record ID</dt><dd>{selected.id}</dd></dl><p><a href={recordRoute(selected.id)}>Open record page</a></p><CopyValue value={selected.id} label="Record ID" buttonLabel="Copy record ID" /><CopyValue value={recordHref(selected.id)} label="Record link" buttonLabel="Copy record link" /><nav aria-label="Record contribution actions">{#each [['evidence','Add evidence'],['correction','Suggest a correction'],['privacy-removal','Privacy or removal']] as [type,label]}<a href={`#/contribute/${type}?target=${encodeURIComponent(selected.id)}`}>{label}</a>{/each}</nav></aside>{/if}
  </div>
</section>
<style>
  .public-database{max-width:110rem;margin:auto;padding:.85rem 1rem;color:#edf0e9;font:.84rem/1.4 system-ui,sans-serif}h1{margin:0 0 .35rem;font:650 1.45rem/1.1 system-ui,sans-serif}.intro{margin:0 0 .65rem;color:#b9c3b7}.browse-layout{display:grid;grid-template-columns:12rem minmax(0,1fr);border-top:1px solid #3c4640}.browse-layout.has-selection{grid-template-columns:12rem minmax(0,1fr) 18rem}.filters{padding:.7rem .75rem .7rem 0;border-right:1px solid #3c4640}.filters>label,legend{display:block;font-weight:600;margin-bottom:.3rem}.filters>input{width:100%;box-sizing:border-box;min-height:2.15rem;padding:.4rem;border:1px solid #59615c;background:#202523;color:#edf0e9;font:inherit}fieldset{display:grid;gap:.25rem;margin:.65rem 0;padding:0;border:0;font-size:.78rem}.results{min-width:0}.results>p,.results>button{margin:.55rem}.result-count{display:flex;align-items:center;justify-content:space-between;gap:.6rem;padding:.45rem .55rem;border-bottom:1px solid #3c4640;font-variant-numeric:tabular-nums}.result-count label{display:flex;align-items:center;gap:.25rem;color:#b9c3b7;font-size:.74rem}.result-count select{background:#202523;color:#edf0e9;border:1px solid #59615c}.active-filters{display:flex;flex-wrap:wrap;gap:.25rem}button{min-height:1.8rem;padding:.25rem .45rem;border:1px solid #657466;background:#252f28;color:#edf0e9;font:.78rem system-ui;cursor:pointer}.coverage{color:#b9c3b7;font-size:.75rem}.selected{padding:.75rem;min-width:0;border-left:1px solid #3c4640;overflow-wrap:anywhere}.selected h2{font-size:1.05rem}.selected dt{color:#b9c3b7;font-size:.75rem;margin-top:.45rem}.selected dd{margin:0 0 .3rem}.selected nav{display:flex;flex-wrap:wrap;gap:.45rem;margin-top:.7rem}.selected :global(.copy-value){margin-top:.45rem}a{color:#dce8d9;text-underline-offset:.2em}button:focus-visible,input:focus-visible,a:focus-visible,select:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:72rem){.browse-layout.has-selection{grid-template-columns:12rem minmax(0,1fr)}.selected{grid-column:1/-1;border-left:0;border-top:1px solid #3c4640}}@media(max-width:43rem){.public-database{padding:.8rem}.browse-layout,.browse-layout.has-selection{display:block}.filters{padding:.65rem 0;border-right:0;border-bottom:1px solid #3c4640}fieldset{grid-template-columns:repeat(2,minmax(0,1fr))}.selected{padding:.7rem 0}}
</style>
