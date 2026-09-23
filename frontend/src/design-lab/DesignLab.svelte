<script lang="ts">
  import { onMount } from 'svelte';
  import type { Direction, LabAction, LabState, Scenario } from './contract';
  import { DIRECTIONS, SCENARIOS } from './contract';
  import { labRecords, LAB_SENTINEL } from './fixtures';
  import { decodeLabHash, encodeLabHash, reduceLabState } from './state';
  import { createLabViewModel } from './viewModel';
  import Atlas from './variants/atlas/Atlas.svelte';
  import Index from './variants/index/Index.svelte';
  import Field from './variants/field/Field.svelte';

  let state: LabState = $state(decodeLabHash(typeof location === 'undefined' ? '' : location.hash));
  let model = $derived(createLabViewModel(labRecords, state));

  function dispatch(action: LabAction) {
    state = reduceLabState(state, action);
    history.replaceState(null, '', encodeLabHash(state));
  }

  onMount(() => {
    const sync = () => state = decodeLabHash(location.hash);
    addEventListener('hashchange', sync);
    return () => removeEventListener('hashchange', sync);
  });
</script>

<svelte:head><title>Map design lab — Until Every Cage</title></svelte:head>
<div class="lab" data-review-sentinel={LAB_SENTINEL} data-direction={state.direction} data-scenario={state.scenario}>
  <header class="lab-header">
    <a class="lab-wordmark" href={`#/map?f1a=${state.direction}&scenario=${state.scenario}`}>Until Every Cage</a>
    <strong>MAP DESIGN LAB</strong>
    <nav aria-label="Main navigation"><a href={`#/map?f1a=${state.direction}&scenario=${state.scenario}`}>Map</a><a href="#/database">Database</a></nav>
    <span>Synthetic development data · not a release</span>
    <label>Direction<select aria-label="Direction" value={state.direction} onchange={e => dispatch({ type: 'direction', value: e.currentTarget.value as Direction })}>{#each DIRECTIONS as direction}<option value={direction}>{direction}</option>{/each}</select></label>
    <label>Scenario<select aria-label="Scenario" value={state.scenario} onchange={e => dispatch({ type: 'scenario', value: e.currentTarget.value as Scenario })}>{#each SCENARIOS as scenario}<option value={scenario}>{scenario}</option>{/each}</select></label>
  </header>
  <main class="lab-main" aria-label="Design direction preview">
    <h1 class="sr-only">Map design review</h1>
    {#if state.direction === 'atlas'}
      <Atlas {state} records={model.listRecords} {dispatch} />
    {:else if state.direction === 'index'}
      <Index {state} records={model.listRecords} {dispatch} />
    {:else}
      <Field {state} records={model.listRecords} {dispatch} />
    {/if}
  </main>
</div>

<style>
  .lab { min-height: 100vh; overflow-x: hidden; overflow-x: clip; }
  .lab-header { flex-wrap: wrap; }
  .lab-header > span { margin-left: auto; }
  .lab-header > label { display: flex; align-items: center; gap: .4rem; color: #c8c8c2; }
  .lab-header select { min-height: 2rem; padding: .25rem .45rem; color: inherit; background: #151718; border: 1px solid #777; text-transform: capitalize; }
  .lab-main { min-height: 0; padding: 0; }
  .lab-main > .sr-only { position: absolute; }
  .lab[data-direction="field"] { position: fixed; z-index: 40; inset: 0; min-height: 0; }
  .lab[data-direction="field"] .lab-header { display: none; }
  .lab[data-direction="field"] .lab-main { height: 100%; }
  @media (max-width: 44rem) {
    .lab-header { gap: .5rem; }
    .lab-header > span { width: 100%; margin: 0; }
    .lab-header > label { flex: 1 1 7rem; }
    .lab-header select { min-width: 0; flex: 1; }
  }
  @media (max-width: 20rem) {
    .lab-header { gap: .35rem; padding: .4rem; }
    .lab-header > * { min-width: 0; max-width: 100%; }
    .lab-header > label { flex: 1 1 0; }
    .lab-header select { width: 100%; padding-inline: .2rem; }
  }
</style>
