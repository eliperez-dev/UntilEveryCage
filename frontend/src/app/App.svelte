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
  let search = ''; let region = 'all'; let category = 'all';
  let filters: FilterState = initialFilters;
  let showMap = false; let showExport = false; let showGuidance = false;
  let localMode = false;
  let localStatus: 'idle' | 'loading' | 'ready' | 'error' | 'no-release' = 'idle';
  let detailStatus: 'idle' | 'loading' | 'error' = 'idle';
  let localError = ''; let exportError = ''; let exportBusy = false;
  let loaded: readonly Location[] = []; let release = 'synthetic-2026.09';
  let ruleset: string | undefined; let manifestSha256: string | undefined;
  let repo = new LocalLocationRepository(); let csvRepo = new LocalCsvExportRepository();
  $: filters = { search, region, category };
  $: source = localMode ? loaded : (profile === 'community' ? locations.slice(0, 1) : locations);
  $: visibleLocations = filterLocations(source, filters);
  $: exportPreview = previewExport(makeExportModel(visibleLocations, profile, release));
  $: eligibleExport = localMode && profile === 'curated' && localStatus === 'ready' && Boolean(release);
  $: profileLabel = profile === 'curated' ? 'Curated release' : 'Community claims';

  const syncRoute = async () => {
    const route = parseRoute(window.location.hash);
    if (route.kind === 'location' && localMode) {
      detailStatus = 'loading';
      try { const result = await repo.detail(route.facilityId, profile === 'community' ? 'community' : 'official'); selected = result.location; release = result.releaseId; detailStatus = 'idle'; }
      catch (error) { selected = undefined; detailStatus = 'error'; localError = error instanceof Error ? error.message : 'The local detail response was rejected safely.'; }
    } else if (route.kind === 'location') selected = source.find((item) => item.id === route.facilityId) ?? selected;
    else if (route.kind === 'home') selected = localMode ? loaded[0] : source[0];
  };
  const loadLocal = async () => {
    localStatus = 'loading'; localError = ''; manifestSha256 = undefined;
    try { const result = await repo.list(profile === 'community' ? 'community' : 'official'); loaded = result.locations; selected = result.locations[0]; release = result.releaseId; localStatus = 'ready'; await syncRoute(); }
    catch (error) { const kind = error && typeof error === 'object' && 'kind' in error ? (error as { kind: string }).kind : 'error'; localStatus = kind === 'no-release' ? 'no-release' : 'error'; localError = error instanceof Error ? error.message : 'Local V2 response was rejected safely.'; loaded = []; selected = undefined; }
  };
  const downloadCsv = async () => {
    if (!eligibleExport || exportBusy) return; exportBusy = true; exportError = '';
    try { const result = await csvRepo.download('official'); release = result.releaseId; manifestSha256 = result.manifestSha256; const url = URL.createObjectURL(new Blob([result.body], { type: 'text/csv;charset=utf-8' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `uec-v2-${result.releaseId}.csv`; anchor.click(); URL.revokeObjectURL(url); }
    catch (error) { const status = error && typeof error === 'object' && 'status' in error ? (error as { status: number }).status : undefined; exportError = status === 400 ? 'Choose an explicit supported profile before exporting.' : status === 404 ? 'No eligible promoted release with a manifest is available.' : status === 429 ? 'Export is temporarily rate-limited; try again later.' : error instanceof Error ? error.message : 'The CSV export could not be prepared safely.'; }
    finally { exportBusy = false; }
  };
  const select = (id: string) => { selected = source.find((item) => item.id === id) ?? selected; window.location.hash = `/locations/${id}?profile=${profile}`; };
  const profileChanged = () => { if (localMode) void loadLocal(); };
  onMount(() => { const params = new URLSearchParams(window.location.search); localMode = params.get('mode') === 'local-v2'; if (localMode) { try { const api = params.get('api') ?? undefined; repo = new LocalLocationRepository(globalThis.fetch, api); csvRepo = new LocalCsvExportRepository(globalThis.fetch, api ?? ''); } catch (error) { localStatus = 'error'; localError = error instanceof Error ? error.message : 'Local API origin was rejected safely.'; } } if (localMode && localStatus !== 'error') void loadLocal(); else if (!localMode) void syncRoute(); const onHashChange = () => void syncRoute(); window.addEventListener('hashchange', onHashChange); return () => window.removeEventListener('hashchange', onHashChange); });
</script>

<svelte:head><title>Until Every Cage · evidence desk</title></svelte:head>
<main>
  <header class="top"><a class="wordmark" href="/v2-preview/#/">UNTIL EVERY CAGE <span>V2 / FIELD NOTE</span></a><nav aria-label="Site"><a href="/ethics.html">Ethics &amp; safeguards ↗</a></nav></header>
  <section class="intro"><p class="eyebrow">EVIDENCE DESK · {localMode ? 'LOCAL V2 API' : 'SYNTHETIC PREVIEW'}</p><h1>See what a record can—and cannot—tell us.</h1><p class="lede">Start with the source profile, narrow the visible evidence, then inspect what a record can—and cannot—tell us.</p></section>
  <section class="research-bar" aria-labelledby="research-heading"><div><p class="eyebrow">01 / DISCOVER</p><h2 id="research-heading">Choose the evidence lane</h2><p>Profiles stay separate. A community claim is never silently promoted into a curated result.</p></div><div class="toolbar"><label>Profile<select bind:value={profile} onchange={profileChanged}><option value="curated">Curated release</option><option value="community">Community claims</option></select></label><label>Search locations<input aria-label="Search locations" bind:value={search} placeholder="Name, region, category" /></label><label>Region<select bind:value={region}><option value="all">All regions</option><option value="North Coast">North Coast</option></select></label><label>Category<select bind:value={category}><option value="all">All categories</option><option value="dairy">Dairy</option><option value="slaughter">Slaughter</option></select></label></div></section>
  {#if profile === 'community'}<div class="warning" role="note"><strong>Unreviewed community claim</strong><span>Not verified by Until Every Cage. Review this profile before relying on it.</span></div>{/if}
  {#if localMode && localStatus === 'loading'}<div class="state" role="status" aria-live="polite">Loading the {profileLabel.toLowerCase()}…</div>{:else if localMode && (localStatus === 'error' || localStatus === 'no-release')}<div class="state error" role="alert"><h2>{localStatus === 'no-release' ? 'No promoted release' : 'Could not load local V2 data'}</h2><p>{localError}</p><button onclick={loadLocal}>Try again</button></div>{:else if localMode && detailStatus === 'loading'}<div class="state" role="status" aria-live="polite">Loading the selected local record…</div>{:else if localMode && detailStatus === 'error'}<div class="state error" role="alert"><h2>Could not load local record</h2><p>{localError}</p></div>{:else}
    <section class="results-head" aria-labelledby="results-heading"><div><p class="eyebrow">02 / FILTER &amp; COMPARE</p><h2 id="results-heading">Results <span>{visibleLocations.length}</span></h2></div><p class="scope">{localMode ? 'Current eligible response' : 'Fictional demonstration data'} · {profileLabel}</p></section>
    <div class="content"><aside aria-label="Location results"><div class="list-head"><span>VISIBLE RECORDS</span><strong>{visibleLocations.length}</strong></div>{#each visibleLocations as location}<button class:active={selected?.id === location.id} aria-current={selected?.id === location.id ? 'true' : undefined} onclick={() => select(location.id)}><span class="dot"></span><span><strong>{location.name}</strong><small>{location.region} · {location.category}</small></span></button>{:else}<p class="empty">No records match these filters in this profile.</p>{/each}</aside><article aria-labelledby="detail-heading">{#if selected}<p class="eyebrow">03 / RECORD DETAIL</p><h2 id="detail-heading">{selected.name}</h2><p class="region">{selected.region} · {selected.category}</p><div class="facts"><div><span>OBSERVED</span><strong>{selected.observed}</strong></div><div><span>MAP STATUS</span><strong>{selected.lat === null ? 'No publishable map location' : 'Approximate display point'}</strong></div></div><div class="panel"><p class="eyebrow">READ WITH CARE</p><p>This is an observation in a particular release, not a guarantee of current operation. Source origin, factual review, privacy screening, and project approval are separate signals.</p></div>{/if}</article></div>
    {#if selected}<p class="record-id">RECORD / {selected.id}</p>{/if}
  {/if}
  {#if localMode && localStatus === 'ready'}<ReleaseContext profile={profile === 'curated' ? 'official' : 'community'} releaseId={release} ruleset={ruleset} manifestSha256={manifestSha256}/><ExportControl enabled={eligibleExport} busy={exportBusy} error={exportError} onExport={downloadCsv}/>{/if}
  <section class="guidance"><button class="guidance-toggle" aria-expanded={showGuidance} onclick={() => showGuidance = !showGuidance}><span><span class="eyebrow">04 / NEXT ACTION</span><strong>Something looks wrong or unsafe?</strong></span><span>{showGuidance ? 'Hide guidance' : 'Correction &amp; suppression guidance'}</span></button>{#if showGuidance}<div class="guidance-body"><p>Do not infer closure, identity, or permission from a map point. For a correction, privacy concern, or suppression request, preserve the record ID and contact the project maintainer through the reporting channel on the ethics page. Do not include sensitive personal details in a public issue.</p><a href="/ethics.html#reporting">Read reporting guidance ↗</a></div>{/if}</section>
  <div class="phase-controls"><button onclick={() => showMap = !showMap}>{showMap ? 'Hide map' : 'Show map'}</button><button onclick={() => showExport = !showExport}>Preview export</button></div>{#if showMap}<MapView items={visibleLocations} selectedId={selected?.id ?? null}/>{/if}{#if showExport}<section class="export-preview"><p class="eyebrow">IN-MEMORY EXPORT PREVIEW</p><strong>{profile} · {release}</strong><p>Loaded results only. This preview is not a live or complete export.</p><pre>{exportPreview}</pre></section>{/if}<footer><span>{localMode ? 'Local V2 mode · no fixture fallback' : 'Method preview · no live requests'}</span></footer>
</main>
