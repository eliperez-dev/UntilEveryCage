<script lang="ts">
  import { onMount } from 'svelte';
  import type { Direction, LabAction, LabState, Scenario } from './contract';
  import { DIRECTIONS, SCENARIOS } from './contract';
  import { labRecords, LAB_SENTINEL } from './fixtures';
  import { decodeLabHash, encodeLabHash, reduceLabState } from './state';
  import { createLabViewModel } from './viewModel';
  import MapSurface from './components/MapSurface.svelte';
  import RecordList from './components/RecordList.svelte';

  let state: LabState = $state(decodeLabHash(typeof location === 'undefined' ? '' : location.hash));
  let model = $derived(createLabViewModel(labRecords, state));
  const categories = ['Poultry', 'Pig', 'Dairy', 'Processing', 'Laboratory', 'Aquaculture'];
  const precisions = ['exact', 'city', 'coarse', 'unmapped'] as const;

  function dispatch(action: LabAction) {
    state = reduceLabState(state, action);
    history.replaceState(null, '', encodeLabHash(state));
  }
  function toggleCategory(category: string, checked: boolean) {
    const categories = checked ? [...state.filters.categories, category] : state.filters.categories.filter(item => item !== category);
    dispatch({ type: 'filters', value: { ...state.filters, categories } });
  }
  function togglePrecision(precision: typeof precisions[number], checked: boolean) {
    const values = checked ? [...state.filters.precisions, precision] : state.filters.precisions.filter(item => item !== precision);
    dispatch({ type: 'filters', value: { ...state.filters, precisions: values } });
  }

  onMount(() => {
    const sync = () => state = decodeLabHash(location.hash);
    addEventListener('hashchange', sync);
    return () => removeEventListener('hashchange', sync);
  });
</script>

<svelte:head><title>Map design lab — Until Every Cage</title></svelte:head>
<div class="lab" data-review-sentinel={LAB_SENTINEL} data-scenario={state.scenario}>
  <header class="lab-header">
    <a class="lab-wordmark" href="#/map?f1a=atlas">Until Every Cage</a>
    <strong>MAP DESIGN LAB</strong>
    <nav aria-label="Main navigation"><a href="#/map?f1a=atlas">Map</a><a href="#/database">Database</a></nav>
    <span>Synthetic development data · not a release</span>
  </header>
  <aside class="review-controls" aria-label="Design review controls">
    <label>Direction<select value={state.direction} onchange={e => dispatch({ type: 'direction', value: e.currentTarget.value as Direction })}>{#each DIRECTIONS as direction}<option value={direction}>{direction}</option>{/each}</select></label>
    <label>Scenario<select value={state.scenario} onchange={e => dispatch({ type: 'scenario', value: e.currentTarget.value as Scenario })}>{#each SCENARIOS as scenario}<option value={scenario}>{scenario}</option>{/each}</select></label>
  </aside>
  <main class="lab-main">
    <h1 class="sr-only">Map</h1>
    <form role="search" onsubmit={e => e.preventDefault()}>
      <label for="global-search">Search synthetic records by name, category, country, or place</label>
      <input id="global-search" type="search" value={state.query} oninput={e => dispatch({ type: 'query', value: e.currentTarget.value })} />
    </form>
    <details class="lab-filters">
      <summary>Filters <span>{state.filters.categories.length + state.filters.precisions.length} active</span></summary>
      <fieldset><legend>Category</legend>{#each categories as category}<label><input type="checkbox" checked={state.filters.categories.includes(category)} onchange={e => toggleCategory(category, e.currentTarget.checked)} />{category}</label>{/each}</fieldset>
      <fieldset><legend>Location precision</legend>{#each precisions as precision}<label><input type="checkbox" checked={state.filters.precisions.includes(precision)} onchange={e => togglePrecision(precision, e.currentTarget.checked)} />{precision}</label>{/each}</fieldset>
      <button type="button" onclick={() => dispatch({ type: 'reset-filters' })}>Reset search and filters</button>
    </details>
    {#if model.isLoading}
      <p class="lab-state" role="status">Loading synthetic records…</p>
    {:else if model.hasError}
      <div class="lab-state" role="alert"><strong>Records unavailable</strong><p>The test failure is contained. No live fallback was attempted.</p></div>
    {:else}
      <button class="list-toggle" type="button" aria-expanded={state.listOpen} aria-controls="record-list" onclick={() => dispatch({ type: 'list', value: !state.listOpen })}>{state.listOpen ? 'Hide' : 'Show'} synchronized list</button>
      <div class="workspace">
        <MapSurface records={model.mapRecords} {state} onselect={id => dispatch({ type: 'select', value: id })} oncluster={value => dispatch({ type: 'cluster', value })} onbasemap={value => dispatch({ type: 'basemap', value })} onviewport={value => dispatch({ type: 'viewport', value })} />
        <RecordList records={model.listRecords} selectedId={state.selectedId} hidden={!state.listOpen} onselect={id => dispatch({ type: 'select', value: id })} />
      </div>
    {/if}
    {#if model.isEmpty && !model.isLoading && !model.hasError}<p class="lab-state" role="status">No eligible synthetic records match these search and filter settings.</p>{/if}
    {#if model.selectedRecord}
      <aside class="record-preview" aria-labelledby="record-title">
        <button aria-label="Close record preview" onclick={() => dispatch({ type: 'select', value: null })}>×</button>
        <p>{model.selectedRecord.category} · {model.selectedRecord.precision} location</p>
        <h2 id="record-title">{model.selectedRecord.name}</h2>
        <p>{model.selectedRecord.locality}, {model.selectedRecord.country}</p>
        <small>Synthetic record for interface review. It makes no factual claim.</small>
      </aside>
    {/if}
  </main>
</div>
