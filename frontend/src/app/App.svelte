<script lang="ts">
  import { onMount, tick } from 'svelte';
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
  import { FilterMetadataRepository, type FilterMetadata } from '../api/FilterMetadataRepository';
  import ReleaseContext from '../ui/ReleaseContext.svelte';
  import ExportControl from '../ui/ExportControl.svelte';
  import ScaleNarrative from '../features/scale/ScaleNarrative.svelte';
  import { canOpenDevPreview, DEV_PREVIEW_LABEL, TEST_RELEASE_LABEL, devPreviewExportLabel, canMountPublicExport } from '../features/devPreview/devPreviewContract';
  import type { DevCandidate } from '../api/DevCandidatePreviewRepository';
  import { TestReleaseRepository } from '../api/TestReleaseRepository';
  import { TestReleaseCsvExportRepository } from '../api/TestReleaseCsvExportRepository';
  import DevReviewPanel from '../features/devPreview/DevReviewPanel.svelte';

  let profile: Profile = 'curated';
  let selected: Location | undefined = locations[0];
  let search = ''; let region = 'all'; let category = 'all';
  let sourceType = 'all'; let displayPrecision = 'all'; let lifecycleStatus = 'all';
  let filters: FilterState = initialFilters;
  let showMap = false; let showExport = false; let showGuidance = false;
  let localMode = false;
  let devPreviewMode = false;
  let testReleaseMode = false;
  let previewToken = '';
  let previewStatus: 'idle' | 'loading' | 'ready' | 'error' | 'blocked' = 'idle';
  let previewError = '';
  let previewRows: readonly Location[] = [];
  let testCsvBusy = false;
  let testCsvError = '';
  let localStatus: 'idle' | 'loading' | 'ready' | 'error' | 'no-release' = 'idle';
  let detailStatus: 'idle' | 'loading' | 'error' = 'idle';
  let localError = ''; let exportError = ''; let exportBusy = false;
  let loaded: readonly Location[] = []; let release = 'synthetic-2026.09';
  let ruleset: string | undefined; let manifestSha256: string | undefined;
  let repo = new LocalLocationRepository(); let csvRepo = new LocalCsvExportRepository();
  let metadata: FilterMetadata | undefined; let metadataStatus: 'idle' | 'loading' | 'ready' | 'error' = 'idle';
  let nextCursor: string | null = null; let coverageNote = ''; let coverageScope = ''; let countSemantics = '';
  let paging = false;
  let listGeneration = 0; let detailGeneration = 0;
  let listAbort: AbortController | undefined; let detailAbort: AbortController | undefined;
  let detailRequestKey = '';
  let activeListKey = '';
  let detailErrorHeading: HTMLHeadingElement;
  $: filters = { search, region, category };
  $: source = devPreviewMode ? previewRows : localMode ? loaded : (profile === 'community' ? locations.slice(0, 1) : locations);
  $: visibleLocations = filterLocations(source, filters);
  $: exportPreview = devPreviewExportLabel(devPreviewMode) ?? previewExport(makeExportModel(visibleLocations, profile, release));
  $: eligibleExport = !devPreviewMode && localMode && profile === 'curated' && localStatus === 'ready' && Boolean(release);
  $: profileLabel = profile === 'curated' ? 'Curated release' : 'Community claims';
  let lastRemoteQuery = '';
  // Search is intentionally excluded: the API has no q contract, so it filters
  // only the loaded page while controlled dimensions refetch a new snapshot.
  $: remoteQuery = `${profile}|${region}|${category}|${sourceType}|${displayPrecision}|${lifecycleStatus}`;
  const currentRemoteQuery = () => `${profile}|${region}|${category}|${sourceType}|${displayPrecision}|${lifecycleStatus}|${search}`;
  $: if (localMode && (localStatus === 'ready' || localStatus === 'loading') && remoteQuery !== lastRemoteQuery) { pushFilterUrl(); void loadLocal(); }

  const pushFilterUrl = () => {
    const url = new URL(window.location.href);
    for (const key of ['country_code', 'category', 'source_type', 'display_precision', 'lifecycle_status', 'q']) url.searchParams.delete(key);
    if (region !== 'all') url.searchParams.set('country_code', region);
    if (category !== 'all') url.searchParams.set('category', category);
    if (sourceType !== 'all') url.searchParams.set('source_type', sourceType);
    if (displayPrecision !== 'all') url.searchParams.set('display_precision', displayPrecision);
    if (lifecycleStatus !== 'all') url.searchParams.set('lifecycle_status', lifecycleStatus);
    if (search.trim()) url.searchParams.set('q', search.trim());
    history.pushState(null, '', url);
  };

  const invalidateDetail = () => { detailGeneration += 1; detailAbort?.abort(); detailAbort = undefined; detailStatus = 'idle'; };

  const syncRoute = async () => {
    const route = parseRoute(window.location.hash);
    if (route.kind === 'location' && localMode) {
      const requestKey = `${route.facilityId}|${route.profile}|${profile}`;
      if (detailRequestKey === requestKey && detailStatus === 'loading') return;
      detailRequestKey = requestKey;
      invalidateDetail();
      const generation = detailGeneration;
      const requestedProfile = profile === 'community' ? 'community' : 'official';
      const controller = new AbortController(); detailAbort = controller;
      detailStatus = 'loading';
      try { const result = await repo.detail(route.facilityId, requestedProfile, controller.signal); const currentRoute = parseRoute(window.location.hash); if (generation !== detailGeneration || currentRoute.kind !== 'location' || currentRoute.facilityId !== route.facilityId || currentRoute.profile !== route.profile || profile !== route.profile) return; if (result.releaseId !== release) throw new Error('Local V2 detail belongs to a different release.'); selected = result.location; detailStatus = 'idle'; }
      catch (error) { if (generation !== detailGeneration) return; selected = undefined; detailStatus = 'error'; localError = error instanceof Error ? error.message : 'The local detail response was rejected safely.'; await tick(); detailErrorHeading?.focus(); }
    } else if (route.kind === 'location') selected = source.find((item) => item.id === route.facilityId) ?? selected;
    else if (route.kind === 'home') { detailRequestKey = ''; invalidateDetail(); selected = localMode ? loaded[0] : source[0]; }
  };
  const loadLocal = async (cursor?: string, append = false) => {
    const queryKey = currentRemoteQuery();
    if (!append && activeListKey === queryKey) return;
    if (!append) activeListKey = queryKey;
    listGeneration += 1; const generation = listGeneration;
    listAbort?.abort(); const controller = new AbortController(); listAbort = controller;
    lastRemoteQuery = queryKey;
    if (!append) { invalidateDetail(); localStatus = 'loading'; localError = ''; manifestSha256 = undefined; loaded = []; selected = undefined; nextCursor = null; coverageNote = ''; coverageScope = ''; countSemantics = ''; } else paging = true;
    try { const result = await repo.list(profile === 'community' ? 'community' : 'official', { country_code: region === 'all' ? undefined : region, category: category === 'all' ? undefined : category, source_type: sourceType === 'all' ? undefined : sourceType, display_precision: displayPrecision === 'all' ? undefined : displayPrecision, lifecycle_status: lifecycleStatus === 'all' ? undefined : lifecycleStatus, cursor }, controller.signal); if (generation !== listGeneration) return; loaded = append ? [...loaded, ...result.locations] : result.locations; if (!selected) selected = result.locations[0]; release = result.releaseId; ruleset = result.ruleset; nextCursor = result.nextCursor; coverageNote = result.coverageNote; coverageScope = result.coverageScope ?? ''; countSemantics = result.countSemantics ?? ''; localStatus = 'ready'; paging = false; if (!append) await syncRoute(); }
    catch (error) { paging = false; if (!append) activeListKey = ''; if (generation !== listGeneration) return; const kind = error && typeof error === 'object' && 'kind' in error ? (error as { kind: string }).kind : 'error'; localStatus = kind === 'no-release' ? 'no-release' : 'error'; localError = error instanceof Error ? error.message : 'Local V2 response was rejected safely.'; loaded = []; selected = undefined; }
  };
  const downloadCsv = async () => {
    if (devPreviewMode || !eligibleExport || exportBusy) return; exportBusy = true; exportError = '';
    try { const result = await csvRepo.download('official'); release = result.releaseId; manifestSha256 = result.manifestSha256; const url = URL.createObjectURL(new Blob([result.body], { type: 'text/csv;charset=utf-8' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `uec-v2-${result.releaseId}.csv`; anchor.click(); URL.revokeObjectURL(url); }
    catch (error) { const status = error && typeof error === 'object' && 'status' in error ? (error as { status: number }).status : undefined; exportError = status === 400 ? 'Choose an explicit supported profile before exporting.' : status === 404 ? 'No eligible promoted release with a manifest is available.' : status === 429 ? 'Export is temporarily rate-limited; try again later.' : error instanceof Error ? error.message : 'The CSV export could not be prepared safely.'; }
    finally { exportBusy = false; }
  };
  const select = (id: string) => { selected = source.find((item) => item.id === id) ?? selected; window.location.hash = `/locations/${id}?profile=${profile}`; };
  const profileChanged = () => { history.pushState(null, '', `#/?profile=${profile}`); if (localMode) void loadLocal(); else void syncRoute(); };
  const loadDevPreview = async () => {
    if (!canOpenDevPreview(import.meta.env.DEV, devPreviewMode ? 'dev-candidates' : null)) { previewStatus = 'blocked'; previewError = 'Private candidate preview is unavailable in production builds.'; return; }
    if (!previewToken.trim()) { previewStatus = 'error'; previewError = 'Enter the operator token for this development session.'; return; }
    previewStatus = 'loading'; previewError = '';
    try { if (testReleaseMode) previewRows = (await new TestReleaseRepository().list(profile === 'community' ? 'community' : 'official', previewToken)).locations; else { const { DevCandidatePreviewRepository } = await import('../api/DevCandidatePreviewRepository'); previewRows = await new DevCandidatePreviewRepository().list(previewToken); } previewStatus = 'ready'; selected = previewRows[0]; }
    catch (error) { previewStatus = 'error'; previewError = error instanceof Error ? error.message : 'Private candidate preview was rejected safely.'; previewRows = []; selected = undefined; }
  };
  const downloadTestCsv = async () => { if (!testReleaseMode || previewStatus !== 'ready' || testCsvBusy) return; testCsvBusy = true; testCsvError = ''; try { const result = await new TestReleaseCsvExportRepository().download(profile === 'community' ? 'community' : 'official', previewToken); const url = URL.createObjectURL(new Blob([result.body], { type: 'text/csv;charset=utf-8' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `uec-test-release-${result.releaseId}.csv`; anchor.click(); URL.revokeObjectURL(url); } catch (error) { testCsvError = error instanceof Error ? error.message : 'Private test-release CSV was rejected safely.'; } finally { testCsvBusy = false; } };
  const clearFilters = () => { search = ''; region = 'all'; category = 'all'; sourceType = 'all'; displayPrecision = 'all'; lifecycleStatus = 'all'; };
  const searchChanged = () => { if (localMode) { const url = new URL(window.location.href); if (search.trim()) url.searchParams.set('q', search.trim()); else url.searchParams.delete('q'); history.replaceState(null, '', url); } };
  onMount(() => {
    const params = new URLSearchParams(window.location.search);
    localMode = params.get('mode') === 'local-v2';
    testReleaseMode = params.get('preview') === 'test-release';
    devPreviewMode = testReleaseMode || params.get('preview') === 'dev-candidates';
    const route = parseRoute(window.location.hash);
    if (route.kind !== 'not-found') profile = route.profile;
    if (localMode) {
      search = params.get('q') ?? ''; region = params.get('country_code') ?? 'all'; category = params.get('category') ?? 'all'; sourceType = params.get('source_type') ?? 'all'; displayPrecision = params.get('display_precision') ?? 'all'; lifecycleStatus = params.get('lifecycle_status') ?? 'all';
      try { const api = params.get('api') ?? undefined; repo = new LocalLocationRepository(globalThis.fetch, api); csvRepo = new LocalCsvExportRepository(globalThis.fetch, api ?? ''); metadataStatus = 'loading'; void new FilterMetadataRepository(globalThis.fetch, api ?? '').get().then((value) => { metadata = value; metadataStatus = 'ready'; }).catch(() => { metadataStatus = 'error'; }); } catch (error) { localStatus = 'error'; localError = error instanceof Error ? error.message : 'Local API origin was rejected safely.'; }
    }
    if (devPreviewMode) { previewStatus = import.meta.env.DEV ? 'idle' : 'blocked'; if (!import.meta.env.DEV) previewError = 'Private candidate preview is unavailable in production builds.'; }
    else if (localMode && localStatus !== 'error') void loadLocal(); else if (!localMode) void syncRoute();
    const onHashChange = () => { const next = parseRoute(window.location.hash); if (next.kind !== 'not-found' && next.profile !== profile) { profile = next.profile; if (localMode) void loadLocal(); else void syncRoute(); } else void syncRoute(); };
    const onPopState = () => { const current = new URLSearchParams(window.location.search); if (localMode) { search = current.get('q') ?? ''; region = current.get('country_code') ?? 'all'; category = current.get('category') ?? 'all'; sourceType = current.get('source_type') ?? 'all'; displayPrecision = current.get('display_precision') ?? 'all'; lifecycleStatus = current.get('lifecycle_status') ?? 'all'; } onHashChange(); };
    window.addEventListener('hashchange', onHashChange); window.addEventListener('popstate', onPopState);
    return () => { listAbort?.abort(); detailAbort?.abort(); window.removeEventListener('hashchange', onHashChange); window.removeEventListener('popstate', onPopState); };
  });
</script>

<svelte:head><title>Until Every Cage · evidence desk</title></svelte:head>
<main class:dev-preview={devPreviewMode}>
  <header class="top"><a class="wordmark" href="/v2-preview/#/">UNTIL EVERY CAGE <span>V2 / FIELD NOTE</span></a><nav aria-label="Site"><a href="/ethics.html">Ethics &amp; safeguards ↗</a></nav></header>
  <section class="intro"><p class="eyebrow">EVIDENCE DESK · {devPreviewMode ? 'PRIVATE CANDIDATE PREVIEW' : localMode ? 'LOCAL V2 API' : 'SYNTHETIC PREVIEW'}</p><h1>See what a record can—and cannot—tell us.</h1><p class="lede">Start with the source profile, narrow the visible evidence, then inspect what a record can—and cannot—tell us.</p></section>
  {#if devPreviewMode}<section class="warning" role="alert"><strong>{testReleaseMode ? TEST_RELEASE_LABEL : DEV_PREVIEW_LABEL}</strong><span>Loopback development only. Candidate rows are not part of a promoted release and this view is not a publication decision.</span>{#if previewStatus !== 'blocked'}<label>Operator token (memory only)<input type="password" autocomplete="off" bind:value={previewToken} aria-describedby="preview-token-note" /></label><small id="preview-token-note">The token is sent only in the request header and is not persisted.</small><button onclick={() => void loadDevPreview()} disabled={previewStatus === 'loading'}>{previewStatus === 'loading' ? 'Loading private preview…' : testReleaseMode ? 'Load test release' : 'Load private candidates'}</button>{/if}{#if previewError}<p role="status">{previewError}</p>{/if}</section>{/if}
  {#if devPreviewMode}<DevReviewPanel candidate={selected as DevCandidate | undefined} />{/if}
  {#if testReleaseMode && previewStatus === 'ready'}<section class="warning" aria-label="Test-only export"><strong>TEST-ONLY CSV — NOT PROJECT-APPROVED OR PUBLISHED</strong><span>Complete bounded test-release rows only; this action never uses the public export route.</span><button onclick={() => void downloadTestCsv()} disabled={testCsvBusy}>{testCsvBusy ? 'Preparing test-only CSV…' : 'Download test-only CSV'}</button>{#if testCsvError}<p role="alert">{testCsvError}</p>{/if}</section>{/if}
  {#if !devPreviewMode || previewStatus === 'ready'}
  <ScaleNarrative />
  <section class="research-bar" aria-labelledby="research-heading"><div><p class="eyebrow">01 / DISCOVER</p><h2 id="research-heading">Choose the evidence lane</h2><p>Profiles stay separate. A community claim is never silently promoted into a curated result.</p></div><div class="toolbar"><label>Profile<select bind:value={profile} onchange={profileChanged}><option value="curated">Curated release</option><option value="community">Community claims</option></select></label><label>Search locations<input aria-label="Search locations" bind:value={search} oninput={searchChanged} placeholder="Name, region, category" /></label><label>Country<select aria-label="Country" bind:value={region}><option value="all">All countries</option>{#if metadata}{#each metadata.dimensions.country_code.values as value}<option value={value}>{value}</option>{/each}{/if}</select></label><label>Category<select aria-label="Category" bind:value={category}><option value="all">All categories</option>{#if metadata}{#each metadata.dimensions.category.values as value}<option value={value}>{value}</option>{/each}{/if}</select></label><label>Source origin<select aria-label="Source origin" bind:value={sourceType}><option value="all">All source origins</option>{#if metadata}{#each metadata.dimensions.source_type.values as value}<option value={value}>{value}</option>{/each}{/if}</select></label><label>Map precision<select aria-label="Map precision" bind:value={displayPrecision}><option value="all">All map precision</option>{#if metadata}{#each metadata.dimensions.display_precision.values as value}<option value={value}>{value}</option>{/each}{/if}</select></label><label>Lifecycle<select aria-label="Lifecycle status" bind:value={lifecycleStatus}><option value="all">All lifecycle states</option>{#if metadata}{#each metadata.dimensions.lifecycle_status.values as value}<option value={value}>{value}</option>{/each}{/if}</select></label></div>{#if localMode && metadataStatus === 'loading'}<p class="metadata-status" role="status">Loading available filter values…</p>{:else if localMode && metadataStatus === 'error'}<p class="metadata-status error" role="status" aria-live="polite">Filter metadata is unavailable; only unscoped discovery is shown.</p>{/if}</section>
  <div class="filter-context" aria-live="polite"><span>{search || region !== 'all' || category !== 'all' || sourceType !== 'all' || displayPrecision !== 'all' || lifecycleStatus !== 'all' ? `Filters applied: ${[search && `name “${search}”`, region !== 'all' && region, category !== 'all' && category, sourceType !== 'all' && sourceType, displayPrecision !== 'all' && displayPrecision, lifecycleStatus !== 'all' && lifecycleStatus].filter(Boolean).join(' · ')}` : 'No additional filters applied'}</span><button onclick={clearFilters} disabled={!search && region === 'all' && category === 'all' && sourceType === 'all' && displayPrecision === 'all' && lifecycleStatus === 'all'}>Clear filters</button></div>
  {#if profile === 'community'}<div class="warning" role="note"><strong>Community claims</strong><span>Unreviewed community claims: Not verified by Until Every Cage. Check each record’s factual review status before relying on it.</span></div>{/if}
  {#if localMode && localStatus === 'loading'}<div class="state" role="status" aria-live="polite">Loading the {profileLabel.toLowerCase()}…</div>{:else if localMode && (localStatus === 'error' || localStatus === 'no-release')}<div class="state error" role="alert"><h2>{localStatus === 'no-release' ? 'No promoted release' : 'Could not load local V2 data'}</h2><p>{localError}</p><button onclick={() => void loadLocal()}>Try again</button></div>{:else if localMode && detailStatus === 'loading'}<div class="state" role="status" aria-live="polite">Loading the selected local record…</div>{:else if localMode && detailStatus === 'error'}<div class="state error" role="alert"><h2 tabindex="-1" bind:this={detailErrorHeading}>Could not load local record</h2><p>{localError}</p><button onclick={() => void syncRoute()}>Try record again</button><button onclick={() => { window.location.hash = `/?profile=${profile}`; }}>Back to results</button></div>{:else}
    <section class="results-head" aria-labelledby="results-heading"><div><p class="eyebrow">02 / FILTER &amp; COMPARE</p><h2 id="results-heading">Results <span>{visibleLocations.length}{localMode && nextCursor ? ' on first page' : ''}</span></h2></div><p class="scope">{localMode ? 'Current eligible response' : 'Fictional demonstration data'} · {profileLabel}</p></section>
    <!-- The count is a facility-page observation, never an animal denominator or global total. -->
    {#if localMode}<section class="count-context" aria-label="Count and coverage context"><div><span>VISIBLE FACILITY RECORDS</span><strong>{visibleLocations.length}{nextCursor ? '+' : ''}</strong></div><div><span>DENOMINATOR</span><strong>Not available</strong></div><p>{countSemantics || 'Counts refer to eligible public facility projection rows, not animals or a story-wide total.'} Scope: {coverageScope || 'selected promoted release public facilities'}. {nextCursor ? 'This is a partial page.' : 'This response has no further page.'} Legacy status is not inferred: the current V2 record contract has no legacy field.</p></section>{/if}
    {#if localMode}<p class="page-context" role="status">{coverageNote} {nextCursor ? 'Only the first page is loaded. Search and filters below may miss later records; counts and map points are partial.' : 'All records in this response are loaded; search applies to those records.'}</p>{/if}
    <div class="content"><aside aria-label="Location results"><div class="list-head"><span>VISIBLE RECORDS</span><strong>{visibleLocations.length}{localMode && nextCursor ? '+' : ''}</strong></div>{#each visibleLocations as location}<button class:active={selected?.id === location.id} aria-current={selected?.id === location.id ? 'true' : undefined} onclick={() => select(location.id)}><span class="dot"></span><span><strong>{location.name}</strong><small>{location.region} · {location.category}</small>{#if location.evidence}<small>{location.evidence.sourceType === 'user_submitted' ? 'Community-submitted' : location.evidence.sourceType === 'official' ? 'Government-sourced' : 'Secondary-sourced'} · {location.evidence.factualReviewStatus === 'unreviewed' ? 'Factually unreviewed' : 'Factually reviewed'} · Project {location.evidence.projectApproval}</small>{#if location.evidence.publicationProfile === 'community' && location.evidence.factualReviewStatus === 'unreviewed'}<small class="claim-warning">{location.evidence.publicationWarning ?? 'Unreviewed community claim — not verified by Until Every Cage'}</small>{/if}{/if}</span></button>{:else}<p class="empty">{localMode && nextCursor ? 'No records match these filters on the loaded page. Later pages may contain matches.' : 'No records match these filters in this profile.'}</p>{/each}{#if localMode && nextCursor}<button class="next-page" aria-label="Load next results page" onclick={() => void loadLocal(nextCursor ?? undefined, true)} disabled={paging}>{paging ? 'Loading next page…' : 'Load next page'}</button>{/if}</aside><article aria-labelledby="detail-heading">{#if selected}<p class="eyebrow">03 / RECORD DETAIL</p><h2 id="detail-heading">{selected.name}</h2><p class="region">{selected.region} · {selected.category}</p>{#if selected.evidence?.publicationProfile === 'community' && selected.evidence.factualReviewStatus === 'unreviewed'}<p class="claim-warning">{selected.evidence.publicationWarning ?? 'Unreviewed community claim — not verified by Until Every Cage'}</p>{/if}<div class="facts"><div><span>OBSERVED</span><strong>{selected.observed}</strong></div><div><span>MAP STATUS</span><strong>{selected.lat === null ? 'No publishable map location' : selected.evidence?.displayPrecision === 'exact' ? 'Exact display point' : 'Approximate display point'}</strong></div></div>{#if selected.evidence}<dl class="evidence"><div><dt>Source origin</dt><dd>{selected.evidence.sourceType === 'user_submitted' ? 'Community-submitted' : selected.evidence.sourceType === 'official' ? 'Government-sourced' : 'Secondary-sourced'}</dd></div><div><dt>Factual review</dt><dd>{selected.evidence.factualReviewStatus}{selected.evidence.reviewerRole ? ` · ${selected.evidence.reviewerRole}` : ' · reviewer role unavailable'}</dd></div><div><dt>Privacy screening</dt><dd>{selected.evidence.privacyScreeningStatus}</dd></div><div><dt>Project approval</dt><dd>{selected.evidence.projectApproval}</dd></div><div><dt>Published profile</dt><dd>{selected.evidence.publicationProfile} · release {release}</dd></div><div><dt>Source</dt><dd><a href={selected.evidence.sourceUrl} target="_blank" rel="noopener noreferrer">{selected.source}</a> · {selected.evidence.sourceId}</dd></div><div><dt>Retrieved</dt><dd>{selected.evidence.retrievedAt}</dd></div></dl>{/if}<div class="panel"><p class="eyebrow">READ WITH CARE</p><p>This is an observation in a particular release, not a guarantee of current operation. Source origin, factual review, privacy screening, and project approval are separate signals.</p></div>{/if}</article></div>
    {#if selected}<p class="record-id">RECORD / {selected.id}</p>{/if}
  {/if}
  {#if localMode && localStatus === 'ready'}<ReleaseContext profile={profile === 'curated' ? 'official' : 'community'} releaseId={release} ruleset={ruleset} manifestSha256={manifestSha256}/>{#if canMountPublicExport(devPreviewMode)}<ExportControl enabled={eligibleExport} busy={exportBusy} error={exportError} onExport={downloadCsv}/>{/if}{/if}
  <section class="guidance"><button class="guidance-toggle" aria-expanded={showGuidance} onclick={() => showGuidance = !showGuidance}><span><span class="eyebrow">04 / NEXT ACTION</span><strong>Something looks wrong or unsafe?</strong></span><span>{showGuidance ? 'Hide guidance' : 'Correction &amp; suppression guidance'}</span></button>{#if showGuidance}<div class="guidance-body"><p>Do not infer closure, identity, or permission from a map point. For a correction, privacy concern, or suppression request, preserve the record ID and contact the project maintainer through the reporting channel on the ethics page. Do not include sensitive personal details in a public issue.</p><a href="/ethics.html#reporting">Read reporting guidance ↗</a></div>{/if}</section>
  {#if !devPreviewMode}<div class="phase-controls"><button onclick={() => showMap = !showMap}>{showMap ? 'Hide map' : 'Show map'}</button><button onclick={() => showExport = !showExport}>Preview export</button></div>{#if showMap}<MapView items={visibleLocations} selectedId={selected?.id ?? null}/>{/if}{#if showExport}<section class="export-preview"><p class="eyebrow">IN-MEMORY EXPORT PREVIEW</p><strong>{profile} · {release}</strong><p>Loaded results only. This preview is not a live or complete export.</p><pre>{exportPreview}</pre></section>{/if}{/if}<footer><span>{localMode ? 'Local V2 mode · no fixture fallback' : 'Method preview · no live requests'}</span></footer>
  {/if}
</main>
