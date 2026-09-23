<script lang="ts">
  import type { DirectionViewProps, Precision } from '../../contract';
  import MapSurface from '../../components/MapSurface.svelte';
  import RecordList from '../../components/RecordList.svelte';

  let { state, records, dispatch }: DirectionViewProps = $props();

  const categories = ['Poultry', 'Pig', 'Dairy', 'Processing', 'Laboratory', 'Aquaculture'];
  const precisions: readonly Precision[] = ['exact', 'city', 'coarse', 'unmapped'];
  const mappedRecords = $derived(records.filter(record => record.latitude !== null && record.longitude !== null));
  const selectedRecord = $derived(records.find(record => record.id === state.selectedId) ?? null);
  const activeFilterCount = $derived(state.filters.categories.length + state.filters.precisions.length);

  function toggleCategory(category: string, checked: boolean) {
    const categories = checked
      ? [...state.filters.categories, category]
      : state.filters.categories.filter(value => value !== category);
    dispatch({ type: 'filters', value: { ...state.filters, categories } });
  }

  function togglePrecision(precision: Precision, checked: boolean) {
    const values = checked
      ? [...state.filters.precisions, precision]
      : state.filters.precisions.filter(value => value !== precision);
    dispatch({ type: 'filters', value: { ...state.filters, precisions: values } });
  }

  function closeIndex() {
    dispatch({ type: 'list', value: false });
  }
</script>

<section class="index-view" aria-label="Map and research index">
  <div class="map-column">
    <div class="map-caption">
      <span class="eyebrow">Spatial overview</span>
      <span>Selection and index remain linked</span>
    </div>
    {#if state.scenario === 'loading'}
      <p class="index-state" role="status">Loading the synthetic map field…</p>
    {:else if state.scenario === 'error'}
      <p class="index-state error" role="alert">Records unavailable. No live fallback was attempted.</p>
    {:else}
      <MapSurface
        records={mappedRecords}
        {state}
        onselect={id => dispatch({ type: 'select', value: id })}
        oncluster={value => dispatch({ type: 'cluster', value })}
        onbasemap={value => dispatch({ type: 'basemap', value })}
        onviewport={value => dispatch({ type: 'viewport', value })}
      />
    {/if}
    <div class="map-footnote">
      <span>Provisional map field</span>
      <span>Exact points · approximate areas · no point for unmapped records</span>
    </div>
  </div>

  <aside class:sheet-open={state.listOpen} class="index-rail" aria-label="Research index">
    <header class="rail-heading">
      <div>
        <p class="eyebrow">Field index / 01</p>
        <h2>Records</h2>
      </div>
      <button class="mobile-dismiss" type="button" aria-label="Return to map" onclick={closeIndex}>×</button>
    </header>

    <form class="index-search" role="search" onsubmit={event => event.preventDefault()}>
      <label for="index-query">Search all records</label>
      <div class="search-field">
        <span aria-hidden="true">⌕</span>
        <input
          id="index-query"
          type="search"
          autocomplete="off"
          placeholder="Name, category, country, place"
          value={state.query}
          oninput={event => dispatch({ type: 'query', value: event.currentTarget.value })}
        />
        <kbd>/</kbd>
      </div>
      <small>Global search · not limited to the visible map</small>
    </form>

    <details class="index-filters">
      <summary><span>Refine index</span><span class="filter-count">{activeFilterCount ? `${activeFilterCount} active` : 'Filters'}</span></summary>
      <fieldset>
        <legend>Record category</legend>
        {#each categories as category}
          <label><input type="checkbox" checked={state.filters.categories.includes(category)} onchange={event => toggleCategory(category, event.currentTarget.checked)} />{category}</label>
        {/each}
      </fieldset>
      <fieldset>
        <legend>Location precision</legend>
        {#each precisions as precision}
          <label><input type="checkbox" checked={state.filters.precisions.includes(precision)} onchange={event => togglePrecision(precision, event.currentTarget.checked)} />{precision}</label>
        {/each}
      </fieldset>
      <button class="reset-filters" type="button" onclick={() => dispatch({ type: 'reset-filters' })}>Clear search and filters</button>
    </details>

    <div class="result-ledger" aria-live="polite">
      <span class="result-total">{records.length.toString().padStart(2, '0')}</span>
      <span>eligible synthetic records</span>
      <span class="ledger-rule"></span>
      <span class="precision-counts">{records.filter(record => record.precision === 'exact').length} exact<br />{records.filter(record => record.precision === 'city' || record.precision === 'coarse').length} approximate<br />{records.filter(record => record.precision === 'unmapped').length} without point</span>
    </div>

    {#if selectedRecord && state.scenario !== 'loading' && state.scenario !== 'error'}
      <article class="record-reading" aria-labelledby="reading-title">
        <div class="reading-topline"><span>Selected record</span><button type="button" onclick={() => dispatch({ type: 'select', value: null })} aria-label="Close selected record">×</button></div>
        <span class="record-type">{selectedRecord.category} / {selectedRecord.precision} location</span>
        <h3 id="reading-title">{selectedRecord.name}</h3>
        <p class="record-place">{selectedRecord.locality}, {selectedRecord.country}</p>
        <p class="record-disclosure">Synthetic development record. It makes no factual claim. {selectedRecord.precision === 'unmapped' ? 'No publishable coordinate is available.' : selectedRecord.precision === 'city' ? 'Approximate city-level location; not a facility point.' : selectedRecord.precision === 'coarse' ? 'Coarse area only; no exact facility point is shown.' : 'Exact display precision is not a claim of independent verification.'}</p>
      </article>
    {/if}

    <div class="list-heading"><span>Index entries</span><span>NAME / LOCATION</span></div>
    {#if state.scenario === 'loading'}
      <p class="empty-index" role="status">Loading synthetic records…</p>
    {:else if state.scenario === 'error'}
      <p class="empty-index error" role="alert">The test failure is contained. No live fallback was attempted.</p>
    {:else}
      <RecordList records={records} selectedId={state.selectedId} hidden={!state.listOpen} onselect={id => dispatch({ type: 'select', value: id })} />
      {#if records.length === 0}<p class="empty-index" role="status">No eligible synthetic records match this search and these filters.</p>{/if}
    {/if}
    <footer class="rail-footer"><span>Development corpus</span><span>Synthetic · not a release</span></footer>
  </aside>

  <button class="index-return" type="button" aria-expanded={state.listOpen} onclick={() => dispatch({ type: 'list', value: !state.listOpen })}>
    {state.listOpen ? 'Hide index' : 'Open index'}
  </button>
</section>

<style>
  .index-view {
    --ink: #f1eee7;
    --muted: #a8aaa4;
    --line: #3c4240;
    --line-soft: #2c3230;
    --accent: #d8b879;
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(19rem, 25rem);
    height: calc(100dvh - 7rem);
    color: var(--ink);
    background: #171a1a;
    font-family: "Aptos", "Segoe UI", sans-serif;
    font-size: .875rem;
  }
  .index-state { display: grid; place-content: center; min-height: 100%; margin: 0; padding: 1.5rem; color: #e1dfd7; background: #202725; font: .85rem/1.5 ui-monospace, Consolas, monospace; }
  .index-state.error, .empty-index.error { color: #f0cbc0; }

  .map-column { display: grid; grid-template-rows: auto minmax(30rem, 1fr) auto; min-width: 0; padding: 1rem 1rem 1rem 1.25rem; }
  .map-caption, .map-footnote { display: flex; align-items: center; justify-content: space-between; gap: 1rem; color: var(--muted); font-size: .72rem; }
  .map-caption { padding: .1rem .1rem .75rem; }
  .map-footnote { padding: .6rem .1rem 0; border-top: 1px solid var(--line-soft); font-family: ui-monospace, Consolas, monospace; font-size: .63rem; }
  .eyebrow { margin: 0; color: var(--accent); font: 600 .64rem/1.4 ui-monospace, Consolas, monospace; letter-spacing: .12em; text-transform: uppercase; }
  .index-rail { display: flex; flex-direction: column; min-width: 0; height: 100%; border-left: 1px solid var(--line); background: #1c2020; }
  .rail-heading { display: flex; align-items: flex-end; justify-content: space-between; padding: 1.05rem 1.1rem .8rem; border-bottom: 1px solid var(--line); }
  .rail-heading h2 { margin: .2rem 0 0; font-size: 1.35rem; font-weight: 500; letter-spacing: -.035em; }
  .mobile-dismiss { display: none; }
  .index-search { display: grid; gap: .42rem; padding: .9rem 1.1rem .75rem; border-bottom: 1px solid var(--line-soft); }
  .index-search > label { color: #d4d2cb; font-size: .73rem; }
  .search-field { display: flex; align-items: center; gap: .55rem; min-width: 0; min-height: 2.75rem; padding: 0 .65rem; border: 1px solid #5a615d; background: #141717; }
  .search-field > span { color: var(--accent); font-size: 1.2rem; }
  .search-field input { width: 100%; min-width: 0; padding: .55rem 0; border: 0; outline: 0; color: var(--ink); background: transparent; font: inherit; font-size: .77rem; }
  .search-field input::placeholder { color: #9c9f99; opacity: 1; }
  .search-field kbd { padding: .1rem .3rem; border: 1px solid #4e5551; color: var(--muted); font: .68rem ui-monospace, Consolas, monospace; }
  .index-search small { color: var(--muted); font-size: .66rem; }
  .index-filters { border-bottom: 1px solid var(--line-soft); }
  .index-filters summary { display: flex; justify-content: space-between; padding: .68rem 1.1rem; color: #e2dfd7; cursor: pointer; list-style: none; font-size: .73rem; }
  .index-filters summary::-webkit-details-marker { display: none; }
  .index-filters summary::after { content: '+'; margin-left: .6rem; color: var(--accent); }
  .index-filters[open] summary::after { content: '−'; }
  .filter-count { margin-left: auto; color: var(--muted); font: .65rem ui-monospace, Consolas, monospace; }
  .index-filters fieldset { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .2rem .65rem; margin: .45rem 1.1rem .6rem; padding: 0; border: 0; }
  .index-filters legend { margin-bottom: .35rem; color: var(--muted); font: .62rem ui-monospace, Consolas, monospace; text-transform: uppercase; letter-spacing: .08em; }
  .index-filters label { display: flex; align-items: center; gap: .35rem; min-height: 1.75rem; color: #d1d0ca; font-size: .69rem; }
  .index-filters input { width: 1rem; height: 1rem; margin: 0; accent-color: var(--accent); }
  .reset-filters { grid-column: 1 / -1; justify-self: start; min-height: 2rem; margin: 0 1.1rem .65rem; padding: .25rem .45rem; border: 1px solid #606662; color: var(--ink); background: transparent; font-size: .68rem; }
  .result-ledger { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: .7rem; padding: .72rem 1.1rem; border-bottom: 1px solid var(--line); color: var(--muted); font-size: .65rem; }
  .result-total { color: var(--ink); font: 500 1.15rem/1 ui-monospace, Consolas, monospace; font-variant-numeric: tabular-nums; }
  .ledger-rule { height: 1px; background: var(--line); }
  .precision-counts { color: #c2c3bc; font: .59rem/1.55 ui-monospace, Consolas, monospace; font-variant-numeric: tabular-nums; text-align: right; }
  .record-reading { position: relative; padding: .8rem 1.1rem .9rem; border-bottom: 1px solid var(--line); background: #252a28; }
  .reading-topline { display: flex; align-items: center; justify-content: space-between; color: var(--accent); font: .61rem ui-monospace, Consolas, monospace; letter-spacing: .1em; text-transform: uppercase; }
  .reading-topline button { min-height: 1.8rem; padding: 0 .45rem; border: 1px solid #69706a; color: var(--ink); background: transparent; font-size: 1rem; }
  .record-type { display: block; margin-top: .4rem; color: var(--muted); font: .62rem ui-monospace, Consolas, monospace; text-transform: uppercase; }
  .record-reading h3 { margin: .2rem 0; font-size: 1.05rem; font-weight: 500; }
  .record-place { margin: 0; color: #d2d0c8; font-size: .75rem; }
  .record-disclosure { margin: .6rem 0 0; padding-top: .55rem; border-top: 1px solid #454c48; color: #c0c1ba; font-size: .68rem; line-height: 1.45; }
  .list-heading { display: flex; justify-content: space-between; padding: .58rem 1.1rem; color: var(--muted); font: .59rem ui-monospace, Consolas, monospace; letter-spacing: .08em; text-transform: uppercase; }
  .index-rail :global(.record-list) { overflow: auto; min-height: 0; flex: 1; border: 0; background: transparent; scrollbar-color: #606762 #1c2020; }
  .index-rail :global(.record-list[hidden]) { display: none; }
  .index-rail :global(.record-list h2) { display: none; }
  .index-rail :global(.record-list ol) { margin: 0; padding: 0; list-style: none; }
  .index-rail :global(.record-list li) { border-top: 1px solid var(--line-soft); border-bottom: 0; }
  .index-rail :global(.record-list button) { display: grid; gap: .23rem; width: 100%; min-height: 3.5rem; padding: .6rem 1.1rem .65rem; border: 0; border-left: 2px solid transparent; color: var(--ink); background: transparent; text-align: left; }
  .index-rail :global(.record-list button:hover) { background: #242927; }
  .index-rail :global(.record-list button.active) { border-left-color: var(--accent); background: #292e2b; }
  .index-rail :global(.record-list strong) { overflow: hidden; font-size: .77rem; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
  .index-rail :global(.record-list small) { display: block; margin: 0; color: #b4b7b0; font: .63rem ui-monospace, Consolas, monospace; }
  .empty-index { margin: 0; padding: 1.1rem; color: #c8c7c0; font-size: .75rem; }
  .rail-footer { display: flex; justify-content: space-between; gap: .5rem; padding: .55rem 1.1rem; border-top: 1px solid var(--line); color: var(--muted); font: .57rem ui-monospace, Consolas, monospace; }
  .index-return { display: none; }
  .map-column :global(.map-surface) { min-height: 0; height: 100%; border: 1px solid #414845; background-color: #222927; background-image: linear-gradient(#313a36 1px, transparent 1px), linear-gradient(90deg, #313a36 1px, transparent 1px); background-size: 7.5% 11%; }
  .map-column :global(.attribution) { font: .58rem ui-monospace, Consolas, monospace; }
  .map-column :global(.precision-legend) { font: .62rem ui-monospace, Consolas, monospace; }
  :global(.index-view button:focus-visible), .search-field input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  @media (max-width: 48rem) {
    .index-view { display: block; min-height: 0; height: calc(100dvh - 7rem); overflow: hidden; }
    .map-column { grid-template-rows: auto minmax(0, 1fr) auto; height: 100%; padding: .65rem; }
    .map-caption { padding: .1rem .1rem .5rem; }
    .map-footnote { align-items: flex-start; flex-direction: column; gap: .15rem; }
    .map-column :global(.map-surface) { min-height: 0; }
    .index-rail { position: absolute; z-index: 8; inset: 0 auto 0 0; width: min(26rem, 100%); max-height: none; border-right: 1px solid #747a74; border-left: 0; box-shadow: 1.25rem 0 3rem #0008; transform: translateX(-105%); transition: transform 180ms ease; }
    .index-rail.sheet-open { transform: translateX(0); }
    .mobile-dismiss { display: inline-block; min-width: 2.5rem; min-height: 2.5rem; border: 1px solid #606662; color: var(--ink); background: transparent; font-size: 1.1rem; }
    .index-return { position: absolute; z-index: 4; top: 3.1rem; left: .75rem; display: block; min-height: 2.5rem; padding: .35rem .65rem; border: 1px solid #777e78; color: var(--ink); background: #171a1a; font-size: .72rem; }
    .index-rail.sheet-open ~ .index-return { visibility: hidden; }
  }

  @media (max-width: 20rem) {
    .map-caption > span:last-child { max-width: 9rem; text-align: right; }
    .index-filters fieldset { grid-template-columns: minmax(0, 1fr); }
    .rail-footer { flex-wrap: wrap; }
  }

  @media (prefers-reduced-motion: reduce) {
    .index-rail { transition: none; }
  }
</style>
