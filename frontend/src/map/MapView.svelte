<script lang="ts">
  import { onMount } from 'svelte';
  import type { Location } from '../domain/location';
  import { projectLocations } from './mapProjection';
  import { LeafletMapAdapter } from './LeafletMapAdapter';
  export let items: readonly Location[] = [];
  export let selectedId: string | null = null;
  let container: HTMLDivElement;
  let adapter: LeafletMapAdapter | null = null;
  $: features = projectLocations(items);
  onMount(() => {
    let disposed = false;
    const map = new LeafletMapAdapter();
    adapter = map;
    map.mount(container).then(() => { if (!disposed) map.update(features, selectedId); });
    return () => { disposed = true; map.destroy(); adapter = null; };
  });
  $: adapter?.update(features, selectedId);
</script>

<div class="map-wrap"><div class="map" bind:this={container} aria-label="Synthetic location map"></div><p>Blank local background · {features.length} display points · no external tiles</p></div>
<style>.map-wrap{background:#ded8cc;border:1px solid #cfc4b2}.map{height:260px}.map-wrap p{margin:0;padding:10px;color:#4f5c69;font-size:.78rem}</style>
