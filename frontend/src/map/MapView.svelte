<script lang="ts">
  import { onMount } from 'svelte';
  import type { Location } from '../domain/location';
  import { clusterFeatures, projectLocations } from './mapProjection';
  import { LeafletMapAdapter } from './LeafletMapAdapter';
  export let items: readonly Location[] = [];
  export let selectedId: string | null = null;
  export let onSelect: ((id: string) => void) | undefined = undefined;
  export let synthetic = true;
  let container: HTMLDivElement;
  let adapter: LeafletMapAdapter | null = null;
  $: features = projectLocations(items);
  $: displayItems = clusterFeatures(features);
  $: clusterCount = displayItems.filter(item => 'count' in item).length;
  $: hasUnreviewedClaims = items.some(item => item.evidence?.publicationProfile === 'community' && item.evidence.factualReviewStatus === 'unreviewed');
  onMount(() => {
    let disposed = false;
    const map = new LeafletMapAdapter();
    adapter = map;
    map.mount(container, onSelect).then(() => { if (!disposed) map.update(displayItems, selectedId); });
    return () => { disposed = true; map.destroy(); adapter = null; };
  });
  $: adapter?.update(displayItems, selectedId);
</script>

<div class="map-wrap">{#if hasUnreviewedClaims}<p class="map-warning">Unreviewed community claims — not verified by Until Every Cage</p>{/if}<div class="map" bind:this={container} role="img" aria-label={synthetic ? 'Synthetic location map showing facility records, not animal counts' : 'Location map showing facility records, not animal counts'}></div><p>Facility pins and clusters only, not animal counts. The results list is the accessible equivalent. Blank local background · {features.length} display points · {clusterCount} clusters · no external tiles</p></div>
<style>.map-wrap{background:#ded8cc;border:1px solid #cfc4b2}.map{height:260px}.map-wrap p{margin:0;padding:10px;color:#4f5c69;font-size:.78rem}.map-wrap :global(.uec-cluster){width:34px!important;height:34px!important;margin-left:-17px!important;margin-top:-17px!important;border-radius:50%;background:#a34927;border:2px solid #f8f4ed;color:#fff;text-align:center;font:700 13px/30px ui-sans-serif,system-ui,sans-serif}.map-wrap :global(.uec-city-point){width:16px!important;height:16px!important;margin-left:-8px!important;margin-top:-8px!important;border-radius:50%;background:#f3eee5;border:3px dotted #a34927}.map-wrap :global(.uec-city-point span){display:block;width:100%;height:100%}</style>
