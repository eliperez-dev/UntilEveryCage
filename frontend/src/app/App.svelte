<script lang="ts">
  import { onMount } from 'svelte';
  import { locations } from '../fixtures/locations';
  import type { Location } from '../domain/location';
  import type { Profile } from '../domain/publication';
  import { parseRoute } from './routeState';
  import { filterLocations, initialFilters, type FilterState } from '../features/locations/filterState';
  import MapView from '../map/MapView.svelte';
  import { makeExportModel } from '../export/exportModel';
  import { previewExport } from '../export/previewExport';
  import { LocalLocationRepository } from '../api/LocalLocationRepository';
  import { LocalCsvExportRepository } from '../api/LocalCsvExportRepository';
  import ReleaseContext from '../ui/ReleaseContext.svelte';
  import ExportControl from '../ui/ExportControl.svelte';

  let profile: Profile = 'curated';
  let selected: Location | undefined = locations[0];
  let search = '';
  let region = 'all';
  let filters: FilterState = initialFilters;
  let showMap = false;
  let showExport = false;
  let localMode = false;
  let localStatus: 'idle' | 'loading' | 'ready' | 'error' | 'no-release' = 'idle';
  let detailStatus: 'idle' | 'loading' | 'error' = 'idle';
  let localError = '';
  let exportError = '';
  let exportBusy = false;
  let loaded: readonly Location[] = [];
  let release = 'synthetic-2026.09';
  let ruleset: string | undefined;
  let manifestSha256: string | undefined;
  let repo = new LocalLocationRepository();
  let csvRepo = new LocalCsvExportRepository();
  $: filters = { search, region, category: 'all' };
  $: source = localMode ? loaded : (profile === 'community' ? locations.slice(0, 1) : locations);
  $: visibleLocations = filterLocations(source, filters);
  $: exportPreview = previewExport(makeExportModel(visibleLocations, profile, release));
  $: eligibleExport = localMode && profile === 'curated' && localStatus === 'ready' && Boolean(release);

  const syncRoute = async () => {
    const route = parseRoute(window.location.hash);
    if (route.kind === 'location' && localMode) {
      detailStatus = 'loading';
      try {
        const result = await repo.detail(route.facilityId, profile === 'community' ? 'community' : 'official');
        selected = result.location; release = result.releaseId; detailStatus = 'idle';
      } catch (error) {
        selected = undefined; detailStatus = 'error'; localError = error instanceof Error ? error.message : 'The local detail response was rejected safely.';
      }
    } else if (route.kind === 'location') selected = source.find((item) => item.id === route.facilityId) ?? selected;
    else if (route.kind === 'home') selected = localMode ? loaded[0] : source[0];
  };

  const loadLocal = async () => {
    localStatus = 'loading'; localError = '';
    try {
      const result = await repo.list(profile === 'community' ? 'community' : 'official');
      loaded = result.locations; selected = result.locations[0]; release = result.releaseId; localStatus = 'ready';
      await syncRoute();
    } catch (error) {
      const kind = error && typeof error === 'object' && 'kind' in error ? (error as { kind: string }).kind : 'error';
      localStatus = kind === 'no-release' ? 'no-release' : 'error'; localError = error instanceof Error ? error.message : 'Local V2 response was rejected safely.'; loaded = []; selected = undefined;
    }
  };

  const downloadCsv = async () => {
    if (!eligibleExport || exportBusy) return;
    exportBusy = true; exportError = '';
    try {
      const result = await csvRepo.download('official');
      release = result.releaseId; manifestSha256 = result.manifestSha256;
      const url = URL.createObjectURL(new Blob([result.body], { type: 'text/csv;charset=utf-8' }));
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `uec-v2-${result.releaseId}.csv`; anchor.click(); URL.revokeObjectURL(url);
    } catch (error) {
      const status = error && typeof error === 'object' && 'status' in error ? (error as { status: number }).status : undefined;
      exportError = status === 400 ? 'Choose an explicit supported profile before exporting.' : status === 404 ? 'No eligible promoted release with a manifest is available.' : status === 429 ? 'Export is temporarily rate-limited; try again later.' : error instanceof Error ? error.message : 'The CSV export could not be prepared safely.';
    } finally { exportBusy = false; }
  };

  const select = (id: string) => { selected = source.find((item) => item.id === id) ?? selected; window.location.hash = `/locations/${id}?profile=${profile}`; };
  onMount(() => {
    const params = new URLSearchParams(window.location.search); localMode = params.get('mode') === 'local-v2';
    if (localMode) { try { repo = new LocalLocationRepository(globalThis.fetch, params.get('api') ?? undefined); csvRepo = new LocalCsvExportRepository(globalThis.fetch, params.get('api') ?? ''); } catch (error) { localStatus = 'error'; localError = error instanceof Error ? error.message : 'Local API origin was rejected safely.'; } }
    if (localMode && localStatus !== 'error') void loadLocal(); else if (!localMode) void syncRoute();
    const onHashChange = () => void syncRoute(); window.addEventListener('hashchange', onHashChange); return () => window.removeEventListener('hashchange', onHashChange);
  });
</script>

<svelte:head><title>Until Every Cage · evidence desk</title></svelte:head>
<main><header class="top"><a class="wordmark" href="/v2-preview/#/">UNTIL EVERY CAGE <span>V2 / FIELD NOTE</span></a><a href="/ethics.html">Ethics &amp; safeguards ↗</a></header>
<section class="intro"><p class="eyebrow">EVIDENCE DESK · {localMode ? 'LOCAL V2 API' : 'SYNTHETIC PREVIEW'}</p><h1>See what a record can—and cannot—tell us.</h1><p class="lede">{localMode ? 'Explicit local integration mode. No fixture or V1 fallback is used.' : 'A quiet, inspectable view of fictional locations.'}</p></section>
<section class="toolbar" aria-label="Preview controls"><label>Profile<select bind:value={profile}><option value="curated">Curated release</option><option value="community">Community claims</option></select></label><label>Search locations<input aria-label="Search locations" bind:value={search} placeholder="Name, region, category" /></label></section>
{#if profile === 'community'}<div class="warning" role="note"><strong>Unreviewed community claim</strong><span>Not verified by Until Every Cage.</span></div>{/if}
{#if localMode && localStatus === 'loading'}<div class="state">Loading the local V2 release…</div>{:else if localMode && (localStatus === 'error' || localStatus === 'no-release')}<div class="state error" role="alert"><h2>{localStatus === 'no-release' ? 'No promoted release' : 'Could not load local V2 data'}</h2><p>{localError}</p></div>{:else if localMode && detailStatus === 'loading'}<div class="state">Loading the selected local record…</div>{:else if localMode && detailStatus === 'error'}<div class="state error" role="alert"><h2>Could not load local record</h2><p>{localError}</p></div>{:else}<div class="content"><aside><div class="list-head"><span>VISIBLE RECORDS</span><strong>{visibleLocations.length}</strong></div>{#each visibleLocations as location}<button class:active={selected?.id === location.id} onclick={() => select(location.id)}><span class="dot"></span><span><strong>{location.name}</strong><small>{location.region} · {location.category}</small></span></button>{:else}<p>No records match these filters.</p>{/each}</aside><article>{#if selected}<p class="eyebrow">RECORD / {selected.id}</p><h2>{selected.name}</h2><p class="region">{selected.region} · {selected.category}</p><div class="facts"><div><span>OBSERVED</span><strong>{selected.observed}</strong></div><div><span>MAP STATUS</span><strong>{selected.lat === null ? 'Not available' : 'Approximate display point'}</strong></div></div>{/if}</article></div>{/if}
{#if localMode && localStatus === 'ready'}<ReleaseContext profile={profile === 'curated' ? 'official' : 'community'} releaseId={release} ruleset={ruleset} manifestSha256={manifestSha256}/><ExportControl enabled={eligibleExport} busy={exportBusy} error={exportError} onExport={downloadCsv}/>{/if}
<div class="phase-controls"><button onclick={() => showMap = !showMap}>{showMap ? 'Hide map' : 'Show map'}</button><button onclick={() => showExport = !showExport}>Preview export</button></div>{#if showMap}<MapView items={visibleLocations} selectedId={selected?.id ?? null}/>{/if}{#if showExport}<section class="export-preview"><p class="eyebrow">IN-MEMORY EXPORT PREVIEW</p><strong>{profile} · {release}</strong><p>Loaded results only. This preview is not a live or complete export.</p><pre>{exportPreview}</pre></section>{/if}<footer><span>{localMode ? 'Local V2 mode · no fixture fallback' : 'Method preview · no live requests'}</span></footer></main>
