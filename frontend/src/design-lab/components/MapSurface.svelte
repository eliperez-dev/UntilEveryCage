<script lang="ts">
  import type { LabRecord, LabState, Viewport } from '../contract';
  import PrecisionLegend from './PrecisionLegend.svelte';

  let { records, state, onselect, oncluster, onbasemap, onviewport }: {
    records: readonly LabRecord[];
    state: LabState;
    onselect(id: string): void;
    oncluster(id: string | null): void;
    onbasemap(value: 'vector' | 'satellite'): void;
    onviewport(value: Viewport): void;
  } = $props();

  const mapped = $derived(records.filter(record => record.latitude !== null && record.longitude !== null));
  const clusterMembers = $derived(mapped.filter(record => record.locality === 'Aarhus').slice(0, 4));
  const clusterExact = $derived(clusterMembers.filter(record => record.precision === 'exact').length);
  const clusterApproximate = $derived(clusterMembers.filter(record => record.precision === 'city' || record.precision === 'coarse').length);
  const clusteredIds = $derived(new Set(state.expandedCluster ? [] : clusterMembers.map(record => record.id)));
  const position = (record: LabRecord) => ({
    left: `${50 + ((record.longitude! - state.viewport.centerLon) / 360) * state.viewport.zoom * 100}%`,
    top: `${50 - ((record.latitude! - state.viewport.centerLat) / 180) * state.viewport.zoom * 100}%`,
  });

  function moveViewport(latDelta: number, lonDelta: number, zoomDelta = 0) {
    onviewport({
      centerLat: Math.max(-90, Math.min(90, state.viewport.centerLat + latDelta)),
      centerLon: Math.max(-180, Math.min(180, state.viewport.centerLon + lonDelta)),
      zoom: Math.max(1, Math.min(18, state.viewport.zoom + zoomDelta)),
    });
  }
</script>

<section class="map-surface" aria-label="Provisional map showing synthetic facility records">
  <div class="cartography" aria-hidden="true"><span>AMERICAS</span><span>EUROPE / AFRICA</span><span>ASIA / PACIFIC</span></div>
  {#if clusterMembers.length > 1 && !state.expandedCluster}
    <button class="marker cluster" style:left={position(clusterMembers[0]!).left} style:top={position(clusterMembers[0]!).top} onclick={() => oncluster('aarhus')} aria-label={`Cluster of ${clusterMembers.length} records near Aarhus: ${clusterExact} exact and ${clusterApproximate} approximate; activate to expand`}>{clusterMembers.length}</button>
  {/if}
  {#if state.expandedCluster}
    <aside class="cluster-summary" aria-live="polite"><strong>Aarhus cluster · {clusterMembers.length} synthetic records</strong><span>{clusterExact} exact · {clusterApproximate} approximate</span><button type="button" onclick={() => oncluster(null)}>Collapse cluster</button></aside>
  {/if}
  {#each mapped.filter(record => !clusteredIds.has(record.id)) as record (record.id)}
    <button class:active={record.id === state.selectedId} class="marker {record.precision}" style:left={position(record).left} style:top={position(record).top} onclick={() => onselect(record.id)} aria-label={`${record.name}; ${record.precision} location`}><span>{record.precision === 'exact' ? '•' : record.precision === 'city' ? '◎' : '≈'}</span></button>
  {/each}
  <div class="viewport-control" role="group" aria-label="Provisional map viewport controls">
    <button type="button" aria-label="Pan map north" onclick={() => moveViewport(10, 0)}>↑</button>
    <button type="button" aria-label="Pan map west" onclick={() => moveViewport(0, -20)}>←</button>
    <button type="button" aria-label="Pan map south" onclick={() => moveViewport(-10, 0)}>↓</button>
    <button type="button" aria-label="Pan map east" onclick={() => moveViewport(0, 20)}>→</button>
    <button type="button" aria-label="Zoom in" onclick={() => moveViewport(0, 0, 1)}>+</button>
    <button type="button" aria-label="Zoom out" onclick={() => moveViewport(0, 0, -1)}>−</button>
  </div>
  <div class="basemap-control" role="group" aria-label="Basemap">
    <button type="button" aria-pressed={state.basemap === 'vector'} onclick={() => onbasemap('vector')}>Vector</button>
    <button type="button" aria-pressed={state.basemap === 'satellite'} onclick={() => onbasemap('satellite')}>Satellite</button>
  </div>
  {#if state.basemap === 'satellite'}<p class="satellite-note" role="status">Satellite imagery unavailable — a licensed provider has not been selected.</p>{/if}
  <PrecisionLegend />
  <small class="attribution">Provisional neutral field · no external tile requests</small>
</section>
