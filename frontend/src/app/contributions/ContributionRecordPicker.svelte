<script lang="ts">
  import { tick } from 'svelte';
  import { LocalLocationRepository } from '../../api/LocalLocationRepository';
  import type { Location } from '../../domain/location';
  import { categoryPresentation } from '../../features/locations/categoryPresentation';
  import { language, tr } from '../language';
  import { parseRecordReference } from '../recordReference';
  let { value = $bindable(''), label = 'Facility', id = 'contribution-record', error = '', releaseId }: { value?: string; label?: string; id?: string; error?: string; releaseId?: string | undefined } = $props();
  const repository = new LocalLocationRepository();
  const reference = $derived(parseRecordReference(value));
  let selected = $state<Location | null>(null);
  let results = $state<readonly Location[]>([]);
  let searchState = $state<'idle' | 'loading' | 'ready' | 'failed'>('idle');
  let input = $state<HTMLInputElement>();
  let retry = $state(0);
  $effect(() => {
    const query = value.trim(), recordId = reference, release = releaseId;
    retry;
    const controller = new AbortController();
    results = []; selected = null; searchState = 'idle';
    if (recordId) {
      searchState = 'loading';
      void repository.detail(recordId, 'official', controller.signal, release).then(result => {
        if (!controller.signal.aborted) { selected = result.location; searchState = 'ready'; }
      }).catch(() => { if (!controller.signal.aborted) searchState = 'failed'; });
      return () => controller.abort();
    }
    if (query.length < 2 || query.length > 160) return () => controller.abort();
    searchState = 'loading';
    const timer = window.setTimeout(() => {
      void repository.list('official', { q: query, limit: 5 }, controller.signal, release).then(result => {
        if (!controller.signal.aborted) { results = result.locations.slice(0, 5); searchState = 'ready'; }
      }).catch(() => { if (!controller.signal.aborted) searchState = 'failed'; });
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  });
  async function clear() { value = ''; await tick(); input?.focus(); }
</script>
<div class="record-picker">
  <label for={id}>{tr(label, $language)} <span aria-hidden="true">*</span></label>
  {#if reference}
    <div class="selected-record">
      <div><strong>{selected?.name ?? tr('Linked record', $language)}</strong><small>{selected ? `${tr(categoryPresentation(selected.taxonomy?.displayCategory ?? selected.category).label, $language)} · ${selected.region}` : tr(searchState === 'loading' ? 'Loading record details…' : 'Record link ready. Public details are unavailable.', $language)}</small></div>
      <button type="button" onclick={clear}>{tr('Change', $language)}</button>
    </div>
    <input type="hidden" id={id} value={reference} />
  {:else}
    <input bind:this={input} id={id} bind:value maxlength="1000" autocomplete="off" placeholder={tr('Search a facility or paste its link', $language)} aria-invalid={error ? 'true' : undefined} aria-describedby={error ? `${id}-error` : `${id}-help`} />
    <span id={`${id}-help`} class="help">{tr('A record link works even when public details are unavailable.', $language)}</span>
    {#if searchState === 'loading'}<p class="search-state" role="status">{tr('Searching…', $language)}</p>
    {:else if searchState === 'failed'}<p class="search-state" role="status">{tr('Search is unavailable. You can paste a record link.', $language)} <button class="retry" type="button" onclick={() => retry += 1}>{tr('Retry', $language)}</button></p>
    {:else if searchState === 'ready' && !results.length}<p class="search-state" role="status">{tr('No matching facilities. Try another name or paste a record link.', $language)}</p>{/if}
    {#if results.length}<ul aria-label={tr('Matching facilities', $language)}>{#each results as record (record.id)}{@const category = categoryPresentation(record.taxonomy?.displayCategory ?? record.category)}<li><button type="button" onclick={() => value = record.id}><span class="category-mark" style:background={category.color} aria-hidden="true"></span><span><strong>{record.name}</strong><small>{tr(category.label, $language)} · {record.region}</small></span><span aria-hidden="true">↗</span></button></li>{/each}</ul>{/if}
  {/if}
  {#if error}<p id={`${id}-error`} class="field-error" role="alert">{tr(error, $language)}</p>{/if}
</div>
<style>
  .record-picker{display:grid;gap:.4rem;min-width:0}label{font-size:.8rem;font-weight:500;color:var(--ink)}input:not([type=hidden]){width:100%;min-height:2.75rem;padding:.6rem .75rem;border:1px solid var(--line-strong);background:var(--panel);color:var(--ink);font:inherit;border-radius:0}.help,.search-state{font-size:.75rem;color:var(--ink-muted)}.search-state{margin:.15rem 0}.field-error{font-size:.8rem;margin:0;color:var(--ink)}input[aria-invalid=true]{border-color:var(--focus)}.selected-record{display:flex;align-items:center;justify-content:space-between;gap:1rem;min-height:3rem;border-left:2px solid var(--line-strong);padding-left:.75rem}.selected-record>div{min-width:0}.selected-record strong,strong{font-size:.85rem;font-weight:500;overflow-wrap:anywhere}.selected-record small,small{display:block;color:var(--ink-muted);font-size:.75rem;overflow-wrap:anywhere;margin-top:.2rem}button{min-height:2.75rem;color:var(--ink);border:1px solid var(--line);background:transparent;font:inherit;padding:.5rem .7rem;cursor:pointer}.selected-record button{font-size:.8rem;flex:none}button:hover{background:var(--panel-hover)}ul{list-style:none;padding:0;margin:0;border:1px solid var(--line)}li+li{border-top:1px solid var(--line)}li button{display:flex;gap:.7rem;align-items:center;width:100%;border:0;text-align:left;padding:.65rem .75rem}li button>span:nth-child(2){min-width:0;flex:1}.category-mark{display:block;width:.65rem;height:.85rem;flex:none;border-radius:50% 50% 50% 0;transform:rotate(-45deg)}.retry{font-size:.75rem;border:0;text-decoration:underline;padding:.3rem .5rem;min-height:2.75rem}:is(button,input):focus-visible{outline:3px solid var(--focus);outline-offset:3px}@media(max-width:48rem), (max-width:60rem) and (max-height:32rem){input:not([type=hidden]){font-size:1rem}}
</style>
