<script lang="ts">
  import { onMount } from 'svelte';
  import type { LabAction, LabState } from './contract';
  import { labRecords, LAB_SENTINEL } from './fixtures';
  import { decodeLabHash, encodeLabHash, reduceLabState } from './state';
  import { createLabViewModel } from './viewModel';
  import Field from './variants/field/Field.svelte';
  let state: LabState = $state(decodeLabHash(typeof location === 'undefined' ? '' : location.hash));
  let model = $derived(createLabViewModel(labRecords, state));
  function dispatch(action: LabAction) { state = reduceLabState(state, action); history.replaceState(null, '', encodeLabHash(state)); }
  onMount(() => { const sync = () => state = decodeLabHash(location.hash); addEventListener('hashchange', sync); return () => removeEventListener('hashchange', sync); });
</script>
<svelte:head><title>Until Every Cage — Map</title></svelte:head>
<div class="lab" data-review-sentinel={LAB_SENTINEL} data-direction="field" data-scenario={state.scenario}><main aria-label="Map preview"><h1 class="sr-only">Investigative map</h1><Field {state} records={model.listRecords} {dispatch}/></main></div>
<style>.lab,main{height:100dvh;overflow:hidden}.sr-only{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}</style>
