<script lang="ts">
  import { onMount } from 'svelte';
  import { LocalLocationRepository } from '../api/LocalLocationRepository';
  import { FacetsRepository, type Facet, type FacetResponse } from '../api/FacetsRepository';
  import type { Location } from '../domain/location';
  import { TAXONOMY_PRIMARY_KEYS, type TaxonomyPrimaryKey } from '../domain/taxonomy';
  import { CATEGORY_PRESENTATIONS } from '../features/locations/categoryPresentation';
  import RecordTable from './RecordTable.svelte';
  import { serializeRoute } from './routeState';
  let { releaseId: requestedReleaseId, returnMapHref = '#/map', onrelease }: { releaseId?: string; returnMapHref?: string; onrelease?: (label: string | null) => void } = $props();
  const repository = new LocalLocationRepository();
  const facetsRepository = new FacetsRepository();
  let countries = $state<readonly Facet[]>([]);
  let sources = $state<readonly Facet[]>([]);
  let country = $state('');
  let source = $state('');
  let facetsRelease = '';
  let facetController: AbortController | undefined;
  let query = $state('');
  let categories = $state<readonly TaxonomyPrimaryKey[]>([]);
  let records = $state<readonly Location[]>([]);
  let cursor = $state<string | null>(null);
  let totalCount = $state<number | null>(null);
  let pageSize = $state<25 | 50 | 100>(50);
  let releaseId = $state<string | undefined>();
  let busy = $state(false);
  let error = $state('');
  let unavailable = $state(false);
  let controller: AbortController;
  let timer: ReturnType<typeof setTimeout>;
  const listingActivity = (record: Location) => record.taxonomy?.leafActivities.map(activity => activity.label).join(' · ') || (record.category === 'unclassified' ? '' : record.category);
  async function load(reset = true, initialFacets?: Promise<FacetResponse>) {
    controller?.abort(); controller = new AbortController(); const current = controller;
    busy = true; error = ''; unavailable = false;
    if (reset) { records = []; cursor = null; totalCount = null; releaseId = requestedReleaseId; }
    try {
      const result = await repository.list('official', { ...(query.trim() ? { q: query.trim() } : {}), category_keys: categories, country_code: country || undefined, source_id: source || undefined, limit: pageSize, ...(cursor ? { cursor } : {}) }, current.signal, releaseId);
      if (current.signal.aborted) return;
      records = [...new Map([...(reset ? [] : records), ...result.locations].map(record => [record.id, record])).values()];
      cursor = result.nextCursor; releaseId = result.releaseId; onrelease?.(result.releaseId);
      if (facetsRelease !== result.releaseId && result.ruleset) {
        facetsRelease = result.releaseId;
        // The first page adopts the in-flight prefetch; only later generations
        // replace it. Attach a rejection handler immediately below.
        const activeFacetController = facetController ?? new AbortController();
        facetController = activeFacetController;
        const facetSignal = activeFacetController.signal;
        void (async () => {
          let value: FacetResponse | undefined;
          if (initialFacets) {
            try { value = await initialFacets; } catch { if (facetSignal.aborted) return; }
          }
          if (!value || value.releaseId !== result.releaseId || value.ruleset !== result.ruleset) {
            value = await facetsRepository.get('official', {}, { releaseId: result.releaseId, ...(result.ruleset ? { ruleset: result.ruleset } : {}) }, facetSignal);
          }
          if (!facetSignal.aborted && value.releaseId === result.releaseId && value.ruleset === result.ruleset) {
            countries = value.dimensions.country_code ?? []; sources = value.dimensions.source_id ?? [];
          }
        })().catch(() => { if (!facetSignal.aborted) facetsRelease = ''; });
      }
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
  function clear() { clearTimeout(timer); query = ''; categories = []; country = ''; source = ''; void load(); }
  function setPageSize(value: string) { pageSize = Number(value) as 25 | 50 | 100; void load(); }
  const recordRoute = (id: string) => serializeRoute({kind:'record',facilityId:id,profile:'official',...(releaseId ? {releaseId} : {}),returnMapHref});
  onMount(() => {
    facetController = new AbortController();
    const initialFacets = facetsRepository.get('official', {}, requestedReleaseId ? { releaseId: requestedReleaseId } : {}, facetController.signal);
    void load(true, initialFacets);
    return () => { controller?.abort(); facetController?.abort(); clearTimeout(timer); };
  });
</script>
<svelte:head><title>Browse records · Until Every Cage</title></svelte:head>
<section class="public-database" aria-labelledby="browse-title">
  <h1 id="browse-title">Browse records</h1><p class="intro">Search the curated public release by name, activity, source, or place.</p>
  <div class="browse-layout">
    <aside class="filters" aria-label="Research filters"><label for="public-query">Search records</label><input id="public-query" type="search" placeholder="Name, activity, source, or place…" value={query} oninput={event => search(event.currentTarget.value)} /><label for="public-country">Country</label><select id="public-country" value={country} onchange={event => { country = event.currentTarget.value; void load(); }}><option value="">All countries</option>{#each countries as facet}<option value={facet.value}>{new Intl.DisplayNames(['en'], { type: 'region' }).of(facet.value) ?? facet.value} ({facet.count})</option>{/each}</select><label for="public-source">Source</label><select id="public-source" value={source} onchange={event => { source = event.currentTarget.value; void load(); }}><option value="">All sources</option>{#each sources as facet}<option value={facet.value}>{facet.label ?? facet.value} ({facet.count})</option>{/each}</select><fieldset><legend>Activity category</legend>{#each TAXONOMY_PRIMARY_KEYS.filter(key => key !== 'unclassified') as key}<label><input type="checkbox" checked={categories.includes(key)} onchange={event => toggleCategory(key, event.currentTarget.checked)} /> {CATEGORY_PRESENTATIONS[key].label}</label>{/each}</fieldset>{#if query || categories.length || country || source}<div class="active-filters" aria-label="Selected filters">{#if query}<button type="button" onclick={() => search('')}>Search: {query} ×</button>{/if}{#each categories as key}<button type="button" onclick={() => toggleCategory(key, false)}>{CATEGORY_PRESENTATIONS[key].label} ×</button>{/each}<button type="button" onclick={clear}>Clear filters</button></div>{/if}</aside>
    <div class="results" aria-live="polite"><div class="result-count"><span>{busy ? 'Loading records…' : `${(totalCount ?? 0).toLocaleString()} matching ${totalCount === 1 ? 'record' : 'records'}`}</span><label>Rows <select value={pageSize} onchange={event => setPageSize(event.currentTarget.value)}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label></div>{#if error}<p role={unavailable ? 'status' : 'alert'}>{error}</p>{#if !unavailable}<button type="button" onclick={() => void load()}>Retry</button>{/if}{:else if !busy && !records.length}<p>No records match these filters in this release.</p>{:else}<RecordTable records={records.map(record => ({ id: record.id, name: record.name, activity: listingActivity(record), place: record.region, source: record.source, href: recordRoute(record.id) }))} />{/if}{#if cursor}<button disabled={busy} type="button" onclick={() => void load(false)}>Load more</button>{/if}</div>
  </div>
</section>
  <style>
  .public-database{max-width:110rem;margin:auto;padding:.85rem 1rem;color:#edf0e9;font:.84rem/1.4 system-ui,sans-serif}h1{margin:0 0 .35rem;font:650 1.45rem/1.1 system-ui,sans-serif}.intro{margin:0 0 .65rem;color:#b9c3b7}.browse-layout{display:grid;grid-template-columns:12rem minmax(0,1fr);border-top:1px solid #3c4640}.filters{padding:.7rem .75rem .7rem 0;border-right:1px solid #3c4640}.filters>label,legend{display:block;font-weight:600;margin-bottom:.3rem}.filters>input,.filters>select{width:100%;box-sizing:border-box;min-height:2.15rem;padding:.4rem;border:1px solid #59615c;background:#202523;color:#edf0e9;font:inherit}fieldset{display:grid;gap:.25rem;margin:.65rem 0;padding:0;border:0;font-size:.78rem}.results{min-width:0}.results>p,.results>button{margin:.55rem}.result-count{display:flex;align-items:center;justify-content:space-between;gap:.6rem;padding:.45rem .55rem;border-bottom:1px solid #3c4640;font-variant-numeric:tabular-nums}.result-count label{display:flex;align-items:center;gap:.25rem;color:#b9c3b7;font-size:.74rem}.result-count select{background:#202523;color:#edf0e9;border:1px solid #59615c}.active-filters{display:flex;flex-wrap:wrap;gap:.25rem}button{min-height:1.8rem;padding:.25rem .45rem;border:1px solid #657466;background:#252f28;color:#edf0e9;font:.78rem system-ui;cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:43rem){.public-database{padding:.8rem}.browse-layout{display:block}.filters{padding:.65rem 0;border-right:0;border-bottom:1px solid #3c4640}fieldset{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
