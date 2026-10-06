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
  const repository = new LocalLocationRepository();
  let query = $state('');
  let categories = $state<readonly TaxonomyPrimaryKey[]>([]);
  let records = $state<readonly Location[]>([]);
  let selectedId = $state<string | null>(null);
  let cursor = $state<string | null>(null);
  let releaseId = $state<string | undefined>();
  let coverage = $state('');
  let busy = $state(false);
  let error = $state('');
  let unavailable = $state(false);
  let controller: AbortController;
  let timer: ReturnType<typeof setTimeout>;
  const selected = $derived(records.find(record => record.id === selectedId));
  const precision = (record: Location) => precisionPresentation(record.evidence?.displayPrecision);
  async function load(reset = true) {
    controller?.abort(); controller = new AbortController(); const current = controller;
    busy = true; error = ''; unavailable = false;
    if (reset) { records = []; cursor = null; releaseId = undefined; selectedId = null; }
    try {
      const result = await repository.list('official', { q: query, category_keys: categories, limit: 100, ...(cursor ? { cursor } : {}) }, current.signal, releaseId);
      if (current.signal.aborted) return;
      records = [...new Map([...(reset ? [] : records), ...result.locations].map(record => [record.id, record])).values()];
      cursor = result.nextCursor; releaseId = result.releaseId; coverage = result.coverageNote;
    } catch (cause) {
      if (current.signal.aborted) return;
      unavailable = !!cause && typeof cause === 'object' && 'kind' in cause && cause.kind === 'no-release';
      error = unavailable ? 'No eligible public release is available yet.' : 'Records could not be loaded. Try again.';
    } finally { if (current === controller) busy = false; }
  }
  function toggleCategory(key: TaxonomyPrimaryKey, checked: boolean) { categories = checked ? [...new Set([...categories, key])] : categories.filter(value => value !== key); void load(); }
  function search(value: string) { query = value; clearTimeout(timer); timer = setTimeout(() => void load(), 180); }
  function clear() { clearTimeout(timer); query = ''; categories = []; void load(); }
  const recordRoute = (id: string) => serializeRoute({kind:'record',facilityId:id,profile:'official',...(releaseId ? {releaseId} : {})});
  const recordHref = (id: string) => `${window.location.origin}${window.location.pathname}${recordRoute(id)}`;
  onMount(() => { void load(); return () => { controller?.abort(); clearTimeout(timer); }; });
</script>
<svelte:head><title>Browse records · Until Every Cage</title></svelte:head>
<section class="public-database" aria-labelledby="browse-title">
  <h1 id="browse-title">Browse records</h1><p class="intro">Search the curated public release by name, activity, source, or place.</p>
  <div class="browse-layout" class:has-selection={!!selected}>
    <aside class="filters" aria-label="Research filters"><label for="public-query">Search records</label><input id="public-query" type="search" placeholder="Name, activity, source, or place…" value={query} oninput={event => search(event.currentTarget.value)} /><fieldset><legend>Activity category</legend>{#each TAXONOMY_PRIMARY_KEYS as key}<label><input type="checkbox" checked={categories.includes(key)} onchange={event => toggleCategory(key, event.currentTarget.checked)} /> {CATEGORY_PRESENTATIONS[key].label}</label>{/each}</fieldset>{#if query || categories.length}<div class="active-filters" aria-label="Selected filters">{#if query}<button type="button" onclick={() => search('')}>Search: {query} ×</button>{/if}{#each categories as key}<button type="button" onclick={() => toggleCategory(key, false)}>{CATEGORY_PRESENTATIONS[key].label} ×</button>{/each}<button type="button" onclick={clear}>Clear filters</button></div>{/if}</aside>
    <div class="results" aria-live="polite"><p class="result-count">{busy ? 'Loading records…' : `${records.length} ${records.length === 1 ? 'record' : 'records'} loaded`}{#if !busy && !error} · {cursor ? 'More records available' : 'End of results'}{/if}</p>{#if error}<p role={unavailable ? 'status' : 'alert'}>{error}</p>{#if !unavailable}<button type="button" onclick={() => void load()}>Retry</button>{/if}{:else if !busy && !records.length}<p>No eligible records match these filters in this release. This does not establish that no facility exists.</p>{:else}<RecordTable records={records.map(record => ({ id: record.id, name: record.name, activity: record.taxonomy?.leafActivities.map(activity => activity.label).join(' · ') || record.category, place: record.region, source: record.source, precision: precision(record) }))} {selectedId} onselect={id => selectedId = id} />{/if}{#if cursor}<button disabled={busy} type="button" onclick={() => void load(false)}>Load more</button>{/if}{#if releaseId}<p class="coverage">Release {releaseId} · {coverage}</p>{/if}</div>
    {#if selected}<aside class="selected" aria-label="Selected record"><button type="button" onclick={() => selectedId = null}>Close details</button><h2>{selected.name}</h2><p>{selected.region} · {precision(selected)}</p><dl><dt>Activity</dt><dd>{selected.taxonomy?.leafActivities.map(activity => activity.label).join(' · ') || selected.category}</dd><dt>Source</dt><dd>{selected.source}{#if selected.evidence?.sourceUrl} · <a href={selected.evidence.sourceUrl} target="_blank" rel="noreferrer">Open source</a>{/if}</dd><dt>Observed</dt><dd>{selected.observed}</dd><dt>Record ID</dt><dd>{selected.id}</dd></dl><p><a href={recordRoute(selected.id)}>Open record page</a></p><CopyValue value={selected.id} label="Record ID" buttonLabel="Copy record ID" /><CopyValue value={recordHref(selected.id)} label="Record link" buttonLabel="Copy record link" /><nav aria-label="Record contribution actions">{#each [['evidence','Add evidence'],['correction','Suggest a correction'],['privacy-removal','Privacy or removal']] as [type,label]}<a href={`#/contribute/${type}?target=${encodeURIComponent(selected.id)}`}>{label}</a>{/each}</nav></aside>{/if}
  </div>
</section>
<style>
  .public-database{max-width:96rem;margin:auto;padding:1.5rem;color:#edf0e9;font:.9rem/1.5 system-ui,sans-serif}h1{margin:0 0 .75rem;font:500 2rem/1.15 Georgia,serif}.intro{margin:0 0 1rem;color:#b9c3b7}.browse-layout{display:grid;grid-template-columns:13rem minmax(0,1fr);border-top:1px solid #3c4640}.browse-layout.has-selection{grid-template-columns:13rem minmax(0,1fr) 19rem}.filters{padding:1rem 1rem 1rem 0;border-right:1px solid #3c4640}.filters>label,legend{display:block;font-weight:600;margin-bottom:.4rem}.filters>input{width:100%;box-sizing:border-box;min-height:2.5rem;padding:.55rem;border:1px solid #59615c;background:#202523;color:#edf0e9;font:inherit}fieldset{display:grid;gap:.4rem;margin:1rem 0;padding:0;border:0;font-size:.85rem}.results{min-width:0}.results>p,.results>button{margin:.85rem .75rem}.result-count{padding-bottom:.75rem;border-bottom:1px solid #3c4640}.active-filters{display:flex;flex-wrap:wrap;gap:.4rem}button{min-height:2rem;padding:.35rem .55rem;border:1px solid #657466;background:#252f28;color:#edf0e9;font:.85rem system-ui;cursor:pointer}.coverage{color:#b9c3b7;font-size:.82rem}.selected{padding:1rem;min-width:0;border-left:1px solid #3c4640;overflow-wrap:anywhere}.selected h2{font-size:1.15rem}.selected dt{color:#b9c3b7;font-size:.8rem;margin-top:.65rem}.selected dd{margin:0 0 .4rem}.selected nav{display:flex;flex-wrap:wrap;gap:.6rem;margin-top:1rem}.selected :global(.copy-value){margin-top:.65rem}a{color:#dce8d9;text-underline-offset:.2em}button:focus-visible,input:focus-visible,a:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:72rem){.browse-layout.has-selection{grid-template-columns:13rem minmax(0,1fr)}.selected{grid-column:1/-1;border-left:0;border-top:1px solid #3c4640}}@media(max-width:43rem){.public-database{padding:1.5rem 1rem}h1{font-size:1.75rem}.browse-layout,.browse-layout.has-selection{display:block}.filters{padding:1rem 0;border-right:0;border-bottom:1px solid #3c4640}fieldset{grid-template-columns:repeat(2,minmax(0,1fr))}.selected{padding:1rem 0}}
</style>
