<script lang="ts">
  import type { DirectionViewProps, Precision } from '../../contract';
  import { createLabViewModel } from '../../viewModel';
  import MapSurface from '../../components/MapSurface.svelte';
  import RecordList from '../../components/RecordList.svelte';

  let { state, records, dispatch }: DirectionViewProps = $props();
  const model = $derived(createLabViewModel(records, state));
  const categories = ['Poultry', 'Pig', 'Dairy', 'Processing', 'Laboratory', 'Aquaculture'];
  const precisions: readonly Precision[] = ['exact', 'city', 'coarse', 'unmapped'];
  const activeFilterCount = $derived(state.filters.categories.length + state.filters.precisions.length);

  function toggleCategory(category: string, checked: boolean) {
    const categories = checked ? [...state.filters.categories, category] : state.filters.categories.filter(item => item !== category);
    dispatch({ type: 'filters', value: { ...state.filters, categories } });
  }
  function togglePrecision(precision: Precision, checked: boolean) {
    const values = checked ? [...state.filters.precisions, precision] : state.filters.precisions.filter(item => item !== precision);
    dispatch({ type: 'filters', value: { ...state.filters, precisions: values } });
  }
</script>

<section class="lab atlas" aria-label="Atlas map review">
  <div class="atlas-toolbar">
    <form class="atlas-search" role="search" onsubmit={event => event.preventDefault()}>
      <label for="atlas-global-search"><span class="search-scope">GLOBAL SEARCH</span> Search name, category, country, or place</label>
      <div class="search-input-wrap"><span class="search-mark" aria-hidden="true">⌕</span><input id="atlas-global-search" type="search" autocomplete="off" placeholder="Try Aarhus or Poultry" value={state.query} oninput={event => dispatch({ type: 'query', value: event.currentTarget.value })} /><kbd aria-hidden="true">/</kbd></div>
    </form>
    <div class="toolbar-meta" aria-label="Map context"><span class="context-kicker">ATLAS / 01</span><span class="record-total">{model.listRecords.length.toString().padStart(2, '0')} <small>RECORDS</small></span></div>
  </div>

  <div class="atlas-stage">
    <div class="map-frame">
      <div class="map-heading" aria-hidden="true"><span class="map-heading-index">FIELD MAP</span><span class="map-heading-rule"></span><span>{state.viewport.zoom.toFixed(1)}× · {state.viewport.centerLat.toFixed(1)}° / {state.viewport.centerLon.toFixed(1)}°</span></div>
      {#if model.isLoading}
        <div class="atlas-state" role="status"><span class="state-mark">···</span><strong>Assembling synthetic records</strong><small>Map positions are temporarily unavailable.</small></div>
      {:else if model.hasError}
        <div class="atlas-state" role="alert"><span class="state-mark">!</span><strong>Map records unavailable</strong><small>The review fixture failed. No live source was queried.</small></div>
      {:else}
        <MapSurface records={model.mapRecords} {state} onselect={id => dispatch({ type: 'select', value: id })} onaggregate={ids => dispatch({ type: 'aggregate', value: ids })} onbasemap={value => dispatch({ type: 'basemap', value })} onviewport={value => dispatch({ type: 'viewport', value })} />
      {/if}
      {#if model.isEmpty && !model.isLoading && !model.hasError}<div class="empty-note" role="status"><strong>No matching records</strong><span>Adjust global search or precision filters.</span></div>{/if}
    </div>

    <aside class:closed={!state.listOpen} class="results-sheet" aria-label="Synchronized results and filters">
      <div class="sheet-topline"><span class="sheet-index">01 — RESULTS</span><button class="icon-control sheet-close" type="button" aria-label="Close results rail" onclick={() => dispatch({ type: 'list', value: false })}>×</button></div>
      <div class="results-heading"><h2>In view</h2><span class="results-count">{model.listRecords.length.toString().padStart(2, '0')}</span></div>
      <p class="results-caption">Global search results · synthetic review set</p>
      <details class="filter-disclosure" open={activeFilterCount > 0}>
        <summary><span>Refine records</span><span class="filter-count">{activeFilterCount ? `${activeFilterCount} active` : 'FILTERS +'}</span></summary>
        <div class="filter-groups">
          <fieldset><legend>Category</legend>{#each categories as category}<label><input type="checkbox" checked={state.filters.categories.includes(category)} onchange={event => toggleCategory(category, event.currentTarget.checked)} /><span>{category}</span></label>{/each}</fieldset>
          <fieldset><legend>Location precision</legend>{#each precisions as precision}<label><input type="checkbox" checked={state.filters.precisions.includes(precision)} onchange={event => togglePrecision(precision, event.currentTarget.checked)} /><span>{precision === 'exact' ? 'Exact site' : precision === 'city' ? 'City level' : precision === 'coarse' ? 'Coarse area' : 'Unmapped'}</span></label>{/each}</fieldset>
        </div>
        {#if activeFilterCount || state.query}<button class="reset-control" type="button" onclick={() => dispatch({ type: 'reset-filters' })}>Clear search and filters</button>{/if}
      </details>
      <div class="rail-divider"><span>SEMANTIC INDEX</span><span>{model.listRecords.length.toString().padStart(2, '0')}</span></div>
      {#if model.isLoading}<p class="rail-message" role="status">Loading the synthetic record index…</p>{:else if model.hasError}<p class="rail-message" role="alert">The synchronized list is unavailable.</p>{:else}<RecordList records={model.listRecords} selectedId={state.selectedId} onselect={id => dispatch({ type: 'select', value: id })} />{/if}
      <div class="rail-footnote"><span aria-hidden="true">◌</span> {model.unmappedCount} records have no mapped location</div>
    </aside>
    {#if !state.listOpen}<button class="reopen-results" type="button" aria-expanded="false" onclick={() => dispatch({ type: 'list', value: true })}><span class="reopen-symbol" aria-hidden="true">≡</span><span>Open results <small>{model.listRecords.length.toString().padStart(2, '0')}</small></span></button>{/if}

    {#if model.selectedRecord}
      <aside class="detail-sheet" aria-labelledby="atlas-record-title" aria-live="polite">
        <div class="detail-topline"><span>RECORD NOTE / SYNTHETIC</span><button class="icon-control" type="button" aria-label="Close record detail" onclick={() => dispatch({ type: 'select', value: null })}>×</button></div>
        <p class="detail-category">{model.selectedRecord.category} <span>·</span> {model.selectedRecord.precision === 'exact' ? 'Exact site' : model.selectedRecord.precision === 'city' ? 'City-level area' : model.selectedRecord.precision === 'coarse' ? 'Coarse area' : 'No mapped location'}</p>
        <h2 id="atlas-record-title">{model.selectedRecord.name}</h2><p class="detail-place">{model.selectedRecord.locality}<span>, </span>{model.selectedRecord.country}</p>
        <dl class="detail-facts"><div><dt>Record</dt><dd>{model.selectedRecord.id}</dd></div><div><dt>Spatial status</dt><dd>{model.selectedRecord.precision === 'exact' ? 'Exact point' : model.selectedRecord.precision === 'city' ? 'City area' : model.selectedRecord.precision === 'coarse' ? 'Coarse area' : 'Unmapped'}</dd></div>{#if model.selectedRecord.precision === 'unmapped'}<div><dt>Map position</dt><dd>Not supplied</dd></div>{/if}</dl>
        <p class="synthetic-disclaimer">This is a synthetic interface fixture. It makes no factual claim about a real place or operator.</p>
      </aside>
    {/if}
  </div>
  <footer class="atlas-footer"><span class="synthetic-flag"><i aria-hidden="true"></i> Synthetic data · not a release</span><span class="map-credit">Neutral provisional field <b>·</b> no external map requests</span></footer>
</section>

<style>
  .atlas {
    --atlas-ink: #eee9de; --atlas-dim: #aaa99f; --atlas-line: #4c514d; --atlas-panel: #171a19;
    --atlas-signal: #d2ad71; --atlas-cool: #a8c3b7; min-height: calc(100svh - 8rem); padding: 0 1.25rem 1rem;
    color: var(--atlas-ink); background: #151817; font-family: "Aptos", "Segoe UI", sans-serif;
  }
  .atlas-toolbar { position: relative; z-index: 5; display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; min-height: 5rem; padding: .85rem 0 .65rem; }
  .atlas-search { width: min(29rem, calc(100% - 11rem)); padding: .55rem .7rem .65rem; background: #111413f5; border: 1px solid #535955; box-shadow: 0 .65rem 2rem #090b0a55; }
  .atlas-search label { display: block; margin-bottom: .35rem; color: #c9c7bd; font-size: .72rem; }
  .search-scope { margin-right: .55rem; color: var(--atlas-signal); font: .58rem/1 ui-monospace, monospace; letter-spacing: .12em; }
  .search-input-wrap { display: flex; align-items: center; gap: .6rem; }
  .search-mark { color: var(--atlas-signal); font: 1.2rem/1 Georgia, serif; }
  .atlas-search input { min-width: 0; width: 100%; padding: .25rem 0; color: var(--atlas-ink); background: transparent; border: 0; font: 1rem/1.3 Georgia, "Times New Roman", serif; }
  .atlas-search input::placeholder { color: #8e938d; }
  .atlas-search kbd { min-width: 1.4rem; color: #b4b6ae; text-align: center; border: 1px solid #4b504c; font: .7rem/1.2 ui-monospace, monospace; }
  .toolbar-meta { display: grid; gap: .38rem; justify-items: end; padding: .2rem .1rem; color: #bdbeb5; font: .62rem/1.2 ui-monospace, monospace; letter-spacing: .12em; }
  .context-kicker { color: #999d96; } .record-total { color: var(--atlas-ink); font-size: .9rem; } .record-total small { color: var(--atlas-dim); font-size: .58rem; }
  .atlas-stage { position: relative; min-height: min(76vh, 55rem); border: 1px solid #505650; background: #242a27; isolation: isolate; }
  .map-frame { position: absolute; inset: 0; overflow: hidden; }
  .map-heading { position: absolute; z-index: 3; top: .8rem; left: 50%; display: flex; align-items: center; gap: .65rem; translate: -50% 0; color: #a8aea7; white-space: nowrap; font: .62rem/1 ui-monospace, monospace; letter-spacing: .08em; pointer-events: none; }
  .map-heading-index { color: #e1ded3; } .map-heading-rule { width: 2.4rem; height: 1px; background: #778077; }
  .atlas :global(.map-surface) { position: absolute; inset: 0; min-height: 0; background-color: #242a27; background-image: radial-gradient(ellipse at 53% 42%, #35413b 0%, #29312d 37%, #232925 75%), linear-gradient(#6571671b 1px, transparent 1px), linear-gradient(90deg, #6571671b 1px, transparent 1px); background-size: auto, 8% 12%, 8% 12%; background-position: center; }
  .atlas :global(.cartography) { inset: 18% 8%; align-items: flex-start; color: #7e8980; opacity: .82; font-size: .58rem; letter-spacing: .16em; }
  .atlas :global(.cartography span:nth-child(2)) { margin-top: 9%; } .atlas :global(.cartography span:nth-child(3)) { margin-top: 3%; }
  .atlas :global(.marker) { display: grid; place-items: center; border-color: #f0e9db; background: #b66049; box-shadow: 0 0 0 4px #b6604930; }
  .atlas :global(.marker.exact) { border-radius: 50% 50% 50% 0; rotate: -45deg; } .atlas :global(.marker.exact span) { rotate: 45deg; }
  .atlas :global(.marker.city) { border-color: #dfbc7f; color: #f1d59d; box-shadow: 0 0 0 5px #dfbc7f1c, 0 0 0 10px #dfbc7f0d; }
  .atlas :global(.marker.coarse) { background: #718d8060; border-color: #b4cfc1; color: #e0ebe3; box-shadow: 0 0 0 8px #718d8020; }
  .atlas :global(.marker.active) { outline-color: #fff7e6; outline-offset: 4px; }
  .atlas :global(.marker.cluster) { border-radius: 50%; background: #e4ddcd; color: #17201a; box-shadow: 0 0 0 6px #e4ddcd35; }
  .atlas :global(.viewport-control) { top: auto; right: .8rem; bottom: 3.15rem; left: auto; grid-template-columns: repeat(3, 2.35rem); gap: 0; border: 1px solid #686f69; box-shadow: 0 .5rem 1rem #10131044; }
  .atlas :global(.viewport-control button) { display: grid; place-items: center; min-height: 2.35rem; padding: 0; border: 0; border-right: 1px solid #454c47; border-bottom: 1px solid #454c47; background: #181d1beb; color: #e5e2d8; }
  .atlas :global(.viewport-control button:nth-child(3n)) { border-right: 0; }
  .atlas :global(.basemap-control) { top: .75rem; right: .75rem; } .atlas :global(.basemap-control button) { min-height: 2.15rem; padding: .4rem .7rem; background: #181d1beb; border-color: #69706a; font: .66rem ui-monospace, monospace; }
  .atlas :global(.basemap-control button[aria-pressed="true"]) { color: #171b18; background: #ded8ca; }
  .atlas :global(.satellite-note) { top: 3.2rem; right: .75rem; color: #eee9df; border: 1px solid #73796f; }
  .atlas :global(.precision-legend) { right: .8rem; bottom: 2rem; left: auto; gap: .42rem; padding: .65rem .75rem; color: #e2e1d8; background: #171c19ed; border: 1px solid #59605a; font: .61rem/1.25 ui-monospace, monospace; }
  .atlas :global(.glyph) { width: .75rem; height: .75rem; flex: 0 0 auto; border-color: #e5ded1; background: #b66049; }
  .atlas :global(.glyph.city) { background: transparent; border-color: #dfbc7f; } .atlas :global(.glyph.coarse) { background: #718d8060; border-color: #b4cfc1; }
  .atlas :global(.glyph.unmapped) { background: transparent; border-color: transparent; border-bottom-color: #c9cbc4; }
  .atlas :global(.attribution) { right: auto; bottom: .4rem; left: .8rem; color: #d1d2c9; font: .57rem ui-monospace, monospace; }
  .atlas :global(.cluster-summary) { top: 4rem; left: 50%; translate: -50% 0; color: var(--atlas-ink); background: #171c19f2; border-color: #96988e; }
  .results-sheet { position: absolute; z-index: 4; top: .75rem; bottom: .75rem; left: .75rem; display: flex; width: min(18.25rem, 34%); flex-direction: column; overflow: hidden; background: #171a19f5; border: 1px solid #575d57; box-shadow: .8rem .5rem 2rem #10131044; transition: translate .22s ease, opacity .22s ease; }
  .results-sheet.closed { translate: calc(-100% - 1.5rem) 0; opacity: 0; pointer-events: none; }
  .sheet-topline, .detail-topline { display: flex; align-items: center; justify-content: space-between; gap: .8rem; min-height: 2.5rem; padding: .35rem .65rem; border-bottom: 1px solid #444a45; }
  .sheet-index, .detail-topline > span { color: #b8b7ad; font: .58rem ui-monospace, monospace; letter-spacing: .14em; }
  .icon-control { display: inline-grid; place-items: center; min-width: 2rem; min-height: 2rem; padding: 0; color: #e9e5d9; background: transparent; border: 1px solid #686e68; font: 1.25rem/1 Georgia, serif; }
  .results-heading { display: flex; align-items: baseline; justify-content: space-between; padding: .7rem .75rem 0; }
  .results-heading h2 { margin: 0; color: #ede9df; font: 1.28rem/1.1 Georgia, "Times New Roman", serif; } .results-count { color: var(--atlas-signal); font: .95rem ui-monospace, monospace; }
  .results-caption { margin: .3rem .75rem .65rem; color: #aaa99f; font: .64rem/1.4 ui-monospace, monospace; }
  .filter-disclosure { padding: 0 .65rem; } .filter-disclosure summary { display: flex; align-items: center; justify-content: space-between; min-height: 2.2rem; padding: 0 .1rem; color: #e2e0d5; border-top: 1px solid #404641; border-bottom: 1px solid #404641; cursor: pointer; font: .72rem ui-monospace, monospace; list-style: none; }
  .filter-disclosure summary::-webkit-details-marker { display: none; } .filter-disclosure summary::after { content: "＋"; color: var(--atlas-signal); } .filter-disclosure[open] summary::after { content: "−"; }
  .filter-count { margin-left: auto; margin-right: .6rem; color: #b8b7ad; font-size: .6rem; }
  .filter-groups { display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; padding: .65rem 0; }
  .filter-groups fieldset { min-width: 0; margin: 0; padding: 0; border: 0; } .filter-groups legend { margin-bottom: .35rem; color: #c3c2b9; font: .58rem ui-monospace, monospace; letter-spacing: .04em; }
  .filter-groups label { display: flex; align-items: center; gap: .3rem; min-height: 1.55rem; color: #d4d2c8; font-size: .65rem; }
  .filter-groups input { width: .85rem; min-width: .85rem; height: .85rem; margin: 0; accent-color: #c4a36b; }
  .reset-control { min-height: 1.9rem; margin: 0 0 .55rem; padding: .3rem .45rem; color: #dedbd0; background: #202421; border: 1px solid #606760; font: .65rem ui-monospace, monospace; }
  .rail-divider { display: flex; justify-content: space-between; margin-top: .25rem; padding: .55rem .75rem .4rem; color: #a9aba2; border-top: 1px solid #414742; font: .56rem ui-monospace, monospace; letter-spacing: .12em; }
  .results-sheet :global(.record-list) { min-height: 0; flex: 1 1 auto; overflow: auto; background: transparent; border: 0; }
  .results-sheet :global(.record-list h2) { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
  .results-sheet :global(.record-list li) { border-color: #373d39; }
  .results-sheet :global(.record-list button) { min-height: 3.15rem; padding: .58rem .75rem; color: #e5e2d8; }
  .results-sheet :global(.record-list button:hover), .results-sheet :global(.record-list button.active) { background: #2a302b; }
  .results-sheet :global(.record-list button.active) { box-shadow: inset 2px 0 var(--atlas-signal); }
  .results-sheet :global(.record-list strong) { display: block; overflow: hidden; font: .78rem/1.35 Georgia, "Times New Roman", serif; text-overflow: ellipsis; white-space: nowrap; }
  .results-sheet :global(.record-list small) { overflow: hidden; color: #b6b8af; font: .57rem/1.4 ui-monospace, monospace; text-overflow: ellipsis; white-space: nowrap; }
  .rail-message { margin: 0; padding: .8rem; color: #d2d0c6; font-size: .75rem; }
  .rail-footnote { display: flex; align-items: center; gap: .4rem; min-height: 2.2rem; padding: .35rem .65rem; color: #c3c5bd; background: #1e2320; border-top: 1px solid #454b46; font: .59rem/1.3 ui-monospace, monospace; }
  .rail-footnote span { color: var(--atlas-cool); }
  .reopen-results { position: absolute; z-index: 4; top: 1rem; left: 1rem; display: flex; align-items: center; gap: .6rem; min-height: 2.7rem; padding: .4rem .7rem; color: #eee9df; background: #171a19f5; border: 1px solid #626960; box-shadow: 0 .4rem 1.2rem #10131044; text-align: left; }
  .reopen-symbol { color: var(--atlas-signal); font-size: 1.15rem; } .reopen-results span:last-child { font: .7rem ui-monospace, monospace; } .reopen-results small { margin-left: .45rem; color: #c9ad7b; }
  .detail-sheet { position: absolute; z-index: 6; top: .75rem; right: .75rem; bottom: .75rem; width: min(24rem, 43%); overflow: auto; background: #171b19f6; border: 1px solid #636a63; box-shadow: -.8rem .5rem 2rem #10131055; animation: sheet-in .2s ease-out both; }
  .detail-topline { min-height: 2.8rem; } .detail-category { margin: 1.2rem 1rem .55rem; color: var(--atlas-signal); font: .62rem ui-monospace, monospace; letter-spacing: .08em; text-transform: uppercase; }
  .detail-category span { padding: 0 .2rem; color: #8d918a; } .detail-sheet h2 { margin: 0 1rem .45rem; color: #f2eee4; font: clamp(1.55rem, 2vw, 2.15rem)/1.08 Georgia, "Times New Roman", serif; font-weight: 400; }
  .detail-place { margin: 0 1rem 1.35rem; color: #c3c4bb; font-size: .82rem; }
  .detail-facts { margin: 0; border-top: 1px solid #444a45; } .detail-facts div { display: grid; grid-template-columns: 8rem 1fr; gap: .6rem; padding: .68rem 1rem; border-bottom: 1px solid #383e3a; }
  .detail-facts dt { color: #a6aaa1; font: .62rem ui-monospace, monospace; } .detail-facts dd { margin: 0; color: #e2e0d7; font: .7rem ui-monospace, monospace; overflow-wrap: anywhere; }
  .synthetic-disclaimer { margin: 1.15rem 1rem; padding: .75rem; color: #cccac0; background: #202521; border-left: 2px solid var(--atlas-signal); font-size: .7rem; line-height: 1.55; }
  .atlas-state, .empty-note { position: absolute; z-index: 3; top: 50%; left: 50%; display: grid; gap: .45rem; width: min(21rem, calc(100% - 2rem)); padding: 1.1rem; translate: -50% -50%; color: #ece8de; background: #171b19ef; border: 1px solid #6a716a; text-align: center; }
  .atlas-state strong, .empty-note strong { font: 1.05rem Georgia, "Times New Roman", serif; } .atlas-state small, .empty-note span { color: #bdc0b7; font-size: .7rem; }
  .state-mark { color: var(--atlas-signal); font: 1.3rem ui-monospace, monospace; }
  .empty-note { top: auto; bottom: 7rem; left: 50%; width: auto; translate: -50% 0; padding: .55rem .8rem; }
  .atlas-footer { display: flex; align-items: center; justify-content: space-between; gap: 1rem; min-height: 2rem; color: #b4b7ae; font: .59rem ui-monospace, monospace; }
  .synthetic-flag { display: inline-flex; align-items: center; gap: .4rem; color: #d7c9a8; } .synthetic-flag i { width: .4rem; height: .4rem; background: var(--atlas-signal); border-radius: 50%; box-shadow: 0 0 0 3px #d2ad7125; }
  .map-credit b { padding: 0 .25rem; color: var(--atlas-signal); }
  .atlas :global(button), .atlas :global(summary), .atlas :global(input) { font-family: inherit; } .atlas :global(button) { border-radius: 0; }
  .atlas :global(button:hover) { filter: brightness(1.12); }
  .atlas :global(button:focus-visible), .atlas :global(summary:focus-visible), .atlas :global(input:focus-visible) { outline: 2px solid #f2d6a5; outline-offset: 3px; }
  @keyframes sheet-in { from { opacity: 0; translate: .5rem 0; } to { opacity: 1; translate: 0 0; } }
  @media (max-width: 48rem) {
    .atlas { min-height: calc(100svh - 8rem); padding: 0 .65rem .5rem; } .atlas-toolbar { min-height: 4.25rem; padding: .6rem 0; }
    .atlas-search { width: min(29rem, calc(100% - 7rem)); } .atlas-search label { font-size: .65rem; } .toolbar-meta { font-size: .55rem; }
    .atlas-stage { min-height: min(78vh, 52rem); } .results-sheet { top: auto; right: .5rem; bottom: .5rem; left: .5rem; width: auto; height: min(39vh, 20rem); border-bottom: 0; transition: translate .22s ease, opacity .22s ease; }
    .results-sheet.closed { translate: 0 calc(100% + .75rem); } .sheet-close { display: none; }
    .filter-disclosure:not([open]) + .rail-divider { margin-top: .15rem; } .filter-groups { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .reopen-results { top: auto; bottom: .85rem; left: .75rem; } .detail-sheet { top: auto; right: .5rem; bottom: .5rem; left: .5rem; width: auto; max-height: min(55vh, 26rem); }
    .atlas :global(.precision-legend) { right: .55rem; bottom: .55rem; max-width: 9rem; } .atlas :global(.viewport-control) { right: .55rem; bottom: 8.7rem; }
    .atlas :global(.attribution) { bottom: .15rem; left: .55rem; max-width: 8rem; font-size: .5rem; } .atlas :global(.basemap-control) { top: .55rem; right: .55rem; }
    .atlas :global(.map-heading) { top: .75rem; left: .55rem; translate: 0 0; } .atlas :global(.map-heading > :last-child) { display: none; }
    .map-credit { max-width: 55%; text-align: right; }
  }
  @media (max-width: 30rem) {
    .atlas { padding-right: .45rem; padding-left: .45rem; } .atlas-search { width: calc(100% - 6.4rem); }
    .atlas-search label { display: grid; gap: .25rem; } .atlas-search input { font-size: .9rem; }
    .toolbar-meta { max-width: 6rem; } .context-kicker { font-size: .48rem; }
    .atlas-stage { min-height: calc(100svh - 12rem); } .results-sheet { right: .35rem; left: .35rem; height: min(43vh, 21rem); }
    .detail-sheet { right: .35rem; left: .35rem; max-height: 64vh; }
    .atlas :global(.precision-legend) { right: .4rem; bottom: .4rem; gap: .3rem; padding: .45rem; font-size: .52rem; }
    .atlas :global(.precision-legend span) { gap: .3rem; } .atlas :global(.viewport-control) { right: .4rem; bottom: 7.5rem; grid-template-columns: repeat(3, 2rem); }
    .atlas :global(.viewport-control button) { min-height: 2rem; } .atlas :global(.basemap-control button) { min-height: 1.9rem; padding: .3rem .45rem; font-size: .58rem; }
    .filter-groups label { font-size: .61rem; } .atlas-footer { font-size: .52rem; }
  }
  @media (prefers-reduced-motion: reduce) { .atlas *, .atlas *::before, .atlas *::after { scroll-behavior: auto !important; animation: none !important; transition: none !important; } }
</style>
