<script lang="ts">
  import { language, tr } from './language';
  import { LocalLocationRepository, type LocalProfile } from '../api/LocalLocationRepository';
  import { isAphisRelevant } from '../api/AphisReportsRepository';
  import type { DerivedSourceVolumeRange, Location } from '../domain/location';
  import { mapHrefFromParams, safeMapHref } from './routeState';
  import { precisionPresentation } from '../features/locations/precisionPresentation';
  import AphisReports from './AphisReports.svelte';
  import RecordConnections from './RecordConnections.svelte';
  import CategoryBadge from '../features/locations/CategoryBadge.svelte';
  import ClassificationSummary from '../features/locations/ClassificationSummary.svelte';
  import { affirmativeSourceEntries } from '../features/locations/classificationSummary';
  import LocationPreview from './LocationPreview.svelte';
  import { locationPreviewZoom } from '../features/locations/locationPreview';
  import { recordNamePresentation } from '../features/locations/recordNamePresentation';
  import { externalMapLink } from '../features/locations/externalMapLink';
  let { id, profile = 'official', releaseId, returnMapHref = '#/map', onrelease }: { id: string; profile?: LocalProfile; releaseId?: string | undefined; returnMapHref?: string; onrelease?: (label: string | null) => void } = $props();
  const repository = new LocalLocationRepository();
  let record = $state<Location | null>(null);
  let currentRelease = $state('');
  let busy = $state(true);
  let error = $state('');
  let retry = $state(0);
  const tabItems = [
    { id: 'reports', label: 'Reports' },
    { id: 'connections', label: 'Connections' },
    { id: 'details', label: 'Details' },
  ] as const;
  type TabId = typeof tabItems[number]['id'];
  let chosenTab = $state<TabId>();
  let showConnections = $state(false);
  const hasReports = $derived(isAphisRelevant(record?.sourceId, record?.sourceFacts));
  const tabs = $derived(tabItems.filter(tab => (tab.id !== 'reports' || hasReports) && (tab.id !== 'connections' || showConnections)));
  const activeTab = $derived(tabs.some(tab => tab.id === chosenTab) ? chosenTab : hasReports ? 'reports' : 'details');
  const countryNames = $derived(new Intl.DisplayNames($language, { type: 'region' }));
  const locality = $derived.by(() => {
    const region = record?.region?.trim();
    const code = record?.countryCode?.toUpperCase();
    const country = code && /^[A-Z]{2}$/.test(code) ? countryNames.of(code) ?? code : code;
    if (!region || region.toUpperCase() === code || region === country) return country ?? '';
    return [region, country].filter(Boolean).join(', ');
  });
  $effect(() => {
    void retry;
    const controller = new AbortController(); record = null; busy = true; error = '';
    chosenTab = undefined;
    showConnections = false;
    currentRelease = '';
    void repository.detail(id, profile, controller.signal, releaseId).then(result => { if (!controller.signal.aborted) { record = result.location; currentRelease = result.releaseId; onrelease?.(result.releaseId); } }).catch(cause => { if (!controller.signal.aborted) error = cause && typeof cause === 'object' && 'kind' in cause && cause.kind === 'restricted' ? 'This record is unavailable in the selected public release.' : 'This record could not be loaded. Try again.'; }).finally(() => { if (!controller.signal.aborted) busy = false; });
    return () => controller.abort();
  });
  function handleTabKey(event: KeyboardEvent, index: number) {
    const last = tabs.length - 1;
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? last :
      event.key === 'ArrowLeft' ? (index + last) % tabs.length :
      event.key === 'ArrowRight' ? (index + 1) % tabs.length : null;
    if (next === null) return;
    const tab = tabs[next];
    if (!tab) return;
    event.preventDefault();
    chosenTab = tab.id;
    document.getElementById(`record-tab-${tab.id}`)?.focus();
  }
  const precision = $derived(precisionPresentation(record?.evidence?.displayPrecision));
  const directSourceUrl = $derived(safeHttps(record?.evidence?.sourceUrl));
  const humanLabel = (value: string) => value.replaceAll(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/\b(nrte|rte)\b/gi, acronym => acronym.toUpperCase()).replace(/^./, letter => letter.toLocaleUpperCase());
  const translatedGenerated = (value: string) => tr(humanLabel(value), $language);
  const geocodingConfidence = (location: Location) => {
    const raw = location.evidence?.geometryProvenance?.confidence;
    const score = raw?.trim() ? Number(raw) : NaN;
    return Number.isFinite(score) && score >= 0 && score <= 1 ? score : null;
  };
  const coordinate = (value: number) => String(Number(value.toFixed(6)));
  const locationMethod = (location: Location) => {
    const method = location.evidence?.geometryProvenance?.method;
    return method && !/^(?:source[_ -])?(?:method[_ -])?unknown$/i.test(method) ? translatedGenerated(method) : null;
  };
  const externalMapHref = $derived(profile === 'official' ? externalMapLink({
    latitude: record?.lat, longitude: record?.lon, precision: record?.evidence?.displayPrecision,
    coordinatePrecision: record?.evidence?.geometryProvenance?.source_precision,
    sourceLocationRole: record?.evidence?.sourceLocationRole,
  }) : null);
  function safeHttps(raw: string | null | undefined): string | null {
    if (!raw) return null;
    try { const url = new URL(raw); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; }
    catch { return null; }
  }
  const sourceFlag = (value: string | boolean) => value === true ? tr('Yes', $language) : typeof value === 'string' ? translatedGenerated(value) : null;
  const sourceFlagLabel = (key: string) => translatedGenerated(key);
  const affirmativeEntries = affirmativeSourceEntries;
  const formattedRangeLocalized = (range: DerivedSourceVolumeRange) => {
    const number = (value: number) => new Intl.NumberFormat($language).format(value);
    if (range.bounds === 'exclusive_upper' && range.upper !== null) return `${tr('Less than', $language)} ${number(range.upper)}`;
    if (range.bounds === 'inclusive_lower_unbounded' && range.lower !== null) return `${number(range.lower)} ${tr('or more', $language)}`;
    if (range.bounds === 'inclusive_lower_exclusive_upper' && range.lower !== null && range.upper !== null) return `${number(range.lower)} ${tr('to less than', $language)} ${number(range.upper)}`;
    return null;
  };
  const slaughterRanges = (ranges: readonly DerivedSourceVolumeRange[] | undefined) => ranges?.filter(range => range.unit === 'head' && range.period === 'trailing_360_days' && range.verificationState === 'source_codebook_verified') ?? [];
  const slaughterRangeText = $derived(slaughterRanges(record?.sourceFacts?.derivedSourceVolumeRanges).map(range => formattedRangeLocalized(range) ? `${formattedRangeLocalized(range)} ${tr('animals', $language)}` : null).filter(Boolean).join(', '));
  const slaughterCodebooks = $derived([...new Set(slaughterRanges(record?.sourceFacts?.derivedSourceVolumeRanges).map(range => safeHttps(range.sourceCodebookUrl)).filter((url): url is string => url !== null))]);
  const processingRanges = (ranges: readonly DerivedSourceVolumeRange[] | undefined) => ranges?.filter(range => range.unit === 'pounds' && range.period === 'month') ?? [];
  const sourceFacts = $derived(record?.sourceFacts);
  const slaughteredSpecies = $derived(affirmativeEntries(sourceFacts?.speciesSlaughtered));
  const processingRangeText = $derived(processingRanges(sourceFacts?.derivedSourceVolumeRanges).map(formattedRangeLocalized).filter(Boolean).map(range => `${range} ${tr('pounds/month', $language)}`).join(', '));
  const hasSourceFactRows = $derived(Boolean(sourceFacts?.alternateNames?.length || sourceFacts?.establishmentId || sourceFacts?.establishmentNumber || sourceFacts?.grantDate || slaughteredSpecies.length || processingRangeText));
  const annualSpeciesCount = (count: number) => new Intl.NumberFormat($language).format(count);
  const mapContext = $derived((safeMapHref(returnMapHref) ?? '#/map').split('?')[1]);
  const openMapHref = $derived(record && record.lat !== null && record.lon !== null ? (() => {
    const params = new URLSearchParams(mapContext);
    params.set('lat', String(record.lat)); params.set('lon', String(record.lon));
    params.set('z', String(locationPreviewZoom(record.evidence?.displayPrecision)));
    return mapHrefFromParams(params, currentRelease || releaseId, record.id);
  })() : null);
  const backMapHref = $derived.by(() => {
    const params = new URLSearchParams(mapContext);
    if (params.has('overlap')) return mapHrefFromParams(params, currentRelease || releaseId);
    if (!params.has('lat') && !params.has('lon') && !params.has('z') && openMapHref) return openMapHref;
    return mapHrefFromParams(params, currentRelease || releaseId, record?.id);
  });
</script>
<svelte:head><title>{record ? recordNamePresentation(record, label => tr(label, $language)) : tr('Record', $language)} · Until Every Cage</title></svelte:head>
<section class="public-record" aria-label={tr('Public record', $language)}>
  <a class="back-to-map" href={backMapHref}><span aria-hidden="true">←</span> {tr('Back to map', $language)}</a>
  {#if profile === 'community'}<p class="warning"><strong>{tr("Unreviewed community claim: not verified by Until Every Cage.", $language)}</strong> {tr("Privacy screening is not factual review or project approval. Community counts are separate.", $language)}</p>{/if}
  {#if busy}<p role="status">{tr('Loading record…', $language)}</p>{:else if error}<h1>{tr("Record unavailable", $language)}</h1><p role="alert">{tr(error, $language)}</p><button type="button" onclick={() => retry += 1}>{tr("Retry", $language)}</button><p><a href="#/database">{tr("Browse records", $language)}</a></p>{:else if record}
    <h1>{recordNamePresentation(record, label => tr(label, $language))}</h1>
    <p class="record-locality">{locality || tr('Location unavailable', $language)}</p>
    <section class="classification-overview" aria-labelledby="activities-heading">
      <h2 id="activities-heading" class="sr-only">{tr('Classification', $language)}</h2>
      <div class="record-category"><CategoryBadge {record} /></div>
      <ClassificationSummary {record} presentation="summary" />
      {#if slaughterRangeText}<p class="slaughter-estimate">{tr('Estimated animals slaughtered (last 360 days)', $language)} · {slaughterRangeText}</p>{/if}
    </section>
    {#if openMapHref && record.lat !== null && record.lon !== null}<LocationPreview latitude={record.lat} longitude={record.lon} precision={record.evidence?.displayPrecision ?? 'unmapped'} category={record.taxonomy?.primaryCategories[0] ?? record.category} href={openMapHref} satellite />{/if}

    <div class="record-tabs" role="tablist" aria-label={tr('Record sections', $language)}>
      {#each tabs as tab, index (tab.id)}
        <button type="button" role="tab" id={`record-tab-${tab.id}`} aria-controls={`record-panel-${tab.id}`} aria-selected={activeTab === tab.id} tabindex={activeTab === tab.id ? 0 : -1} onclick={() => chosenTab = tab.id} onkeydown={event => handleTabKey(event, index)}>{tr(tab.label, $language)}</button>
      {/each}
    </div>
    {#if hasReports}
      <div class="record-tab-content" role="tabpanel" id="record-panel-reports" aria-labelledby="record-tab-reports" tabindex="0" hidden={activeTab !== 'reports'}>
        <AphisReports facilityId={record.id} releaseId={currentRelease} {profile} sourceId={record.sourceId} {sourceFacts}>
          {#if sourceFacts?.aphisAnnualReports?.length || sourceFacts?.aphisDatedInspections?.length}
            <details class="report-facts">
              <summary>{tr('Report details', $language)}</summary>
              <dl>
                {#each sourceFacts.aphisAnnualReports ?? [] as report (report.fiscalYear)}
                  {@const href = safeHttps(report.sourceUrl)}
                  <div><dt>{tr('FY', $language)}{report.fiscalYear} {tr('reported animals', $language)}</dt><dd><ul>{#each report.speciesCounts as species (species.species)}<li>{sourceFlagLabel(species.species)}: {annualSpeciesCount(species.count)}</li>{/each}</ul>{#if href}<a href={href} target="_blank" rel="noopener noreferrer">{tr('Source report', $language)}</a>{/if}</dd></div>
                {/each}
                {#each sourceFacts.aphisDatedInspections ?? [] as inspection (inspection.inspectionDate)}
                  {@const href = safeHttps(inspection.sourceUrl)}
                  <div><dt>{tr('APHIS inspection', $language)}</dt><dd>{inspection.inspectionDate}{#if href} <a href={href} target="_blank" rel="noopener noreferrer">{tr('Source record', $language)}</a>{/if}</dd></div>
                {/each}
              </dl>
            </details>
          {/if}
        </AphisReports>
      </div>
    {/if}
    <div class="record-tab-content" role="tabpanel" id="record-panel-connections" aria-labelledby={showConnections ? 'record-tab-connections' : undefined} tabindex="0" hidden={activeTab !== 'connections'}>
      <RecordConnections facilityId={record.id} releaseId={currentRelease} {profile}
        onstatechange={({ available, loading }) => { if (available || !loading) showConnections = available; }} />
    </div>
    <div class="record-tab-content" role="tabpanel" id="record-panel-details" aria-labelledby="record-tab-details" tabindex="0" hidden={activeTab !== 'details'}>
      <details class="source-disclosure" open>
        <summary id="location-heading">{tr('Location', $language)}</summary>
        <dl>
          <div><dt>{tr('Locality', $language)}</dt><dd>{locality || tr('Location unavailable', $language)}</dd></div>
          <div><dt>{tr('Precision', $language)}</dt><dd>{tr(precision, $language)}</dd></div>
          {#if record.evidence?.sourceLocationRole === 'aphis_mailing_locality'}<div><dt>{tr('Location role', $language)}</dt><dd>{tr('APHIS mailing locality: approximate locality, not an operating-site location', $language)}</dd></div>{/if}
        </dl>
        {#if record.lat !== null && record.lon !== null || locationMethod(record) || record.evidence?.geometryProvenance?.provider || geocodingConfidence(record) !== null || record.evidence?.geometryProvenance?.confidence_band}
          <details class="location-details" open><summary>{tr('Location details', $language)}</summary><dl>
            {#if record.lat !== null && record.lon !== null}<div><dt>{tr('Coordinates', $language)}</dt><dd>{coordinate(record.lat)}, {coordinate(record.lon)}</dd></div>{/if}
            {#if locationMethod(record)}<div><dt>{tr('Location method', $language)}</dt><dd>{locationMethod(record)}</dd></div>{/if}
            {#if record.evidence?.geometryProvenance?.provider}<div><dt>{tr('Geocoding provider', $language)}</dt><dd>{record.evidence.geometryProvenance.provider}</dd></div>{/if}
            {#if geocodingConfidence(record) !== null || record.evidence?.geometryProvenance?.confidence_band}<div><dt>{tr('Geocoding confidence', $language)}</dt><dd>{#if geocodingConfidence(record) !== null}{geocodingConfidence(record)} ({tr('provider score', $language)}){/if}{#if record.evidence?.geometryProvenance?.confidence_band}{geocodingConfidence(record) !== null ? ' · ' : ''}{translatedGenerated(record.evidence.geometryProvenance.confidence_band)}{/if}</dd></div>{/if}
          </dl></details>
        {/if}
        {#if externalMapHref}<p class="map-action"><a href={externalMapHref} target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">{tr('Open in maps', $language)}</a></p>{/if}
      </details>
      <div class="classification-disclosure"><ClassificationSummary {record} presentation="details" detailsOpen showReferences={false} /></div>
      {#if hasSourceFactRows || slaughterCodebooks.length}
        <details class="source-disclosure source-facts" open>
          <summary>{tr('Source facts', $language)}</summary>
          {#if hasSourceFactRows}
            <dl>
              {#if sourceFacts?.alternateNames?.length}<div><dt>{tr('Also known as', $language)}</dt><dd>{sourceFacts.alternateNames.join(' · ')}</dd></div>{/if}
              {#if sourceFacts?.establishmentId}<div><dt>{tr('Establishment ID', $language)}</dt><dd>{sourceFacts.establishmentId}</dd></div>{/if}
              {#if sourceFacts?.establishmentNumber}<div><dt>{tr('Establishment number', $language)}</dt><dd>{sourceFacts.establishmentNumber}</dd></div>{/if}
              {#if sourceFacts?.grantDate}<div><dt>{tr('Grant date', $language)}</dt><dd>{sourceFacts.grantDate}</dd></div>{/if}
              {#if slaughteredSpecies.length}<div><dt>{tr('Species slaughtered', $language)}</dt><dd>{slaughteredSpecies.map(([key, value]) => `${sourceFlagLabel(key)}${typeof value === 'string' ? `: ${sourceFlag(value)}` : ''}`).join(', ')}</dd></div>{/if}
              {#if processingRangeText}<div><dt>{tr('Estimated product volume (pounds/month)', $language)}</dt><dd>{processingRangeText}</dd></div>{/if}
            </dl>
          {/if}
          {#if slaughterCodebooks.length}
            <p class="codebook-links">{#each slaughterCodebooks as href, index (href)}<a {href} target="_blank" rel="noopener noreferrer">{tr('Source codebook', $language)}{slaughterCodebooks.length > 1 ? ` ${index + 1}` : ''}</a>{/each}</p>
          {/if}
        </details>
      {/if}
      <details class="source-disclosure" open>
        <summary>{tr('Source and review', $language)}</summary>
        {#if record.source || directSourceUrl}<p class="compact-source">{#if directSourceUrl}<a class="direct-source" href={directSourceUrl} target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"><span>{record.source || tr('Source', $language)}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6m0-6L10 14M10 4H4v16h16v-6"/></svg><span class="sr-only"> ({tr('opens in a new tab', $language)})</span></a>{:else if record.source}<span>{record.source}</span>{/if}</p>{/if}
        <dl>
          <div><dt>{tr('Source', $language)}</dt><dd>{record.source} {#if directSourceUrl}<a href={directSourceUrl} target="_blank" rel="noopener noreferrer">{tr('Open source', $language)}</a>{/if}</dd></div>
          <div><dt>{tr('Source origin', $language)}</dt><dd>{record.evidence?.sourceType === 'user_submitted' ? tr('Community-submitted', $language) : record.evidence?.sourceType === 'secondary' ? tr('Secondary source', $language) : tr('Government-sourced', $language)}</dd></div>
        </dl>
      </details>
    </div>
    <nav aria-label={tr('Record contribution actions', $language)}>{#each [['evidence','Add evidence'],['correction','Suggest a correction'],['privacy-removal','Privacy or removal']] as [type,label]}<a href={`#/contribute/${type}?target=${encodeURIComponent(record.id)}`}>{tr(label ?? '', $language)}</a>{/each}</nav>
  {/if}
</section>
<style>
  .slaughter-estimate { margin: .3rem 0 .5rem; line-height: 1.55; }
  .public-record { width: min(100% - 3rem, 46rem); margin: auto; padding: .65rem 0 2rem; color: var(--ink); font: .9375rem/1.5 var(--ui-font); }
  .back-to-map { display: inline-flex; align-items: center; min-height: 2.75rem; gap: .45rem; margin-bottom: .35rem; font-size: .875rem; }
  .back-to-map span { text-decoration: none; }
  h1 { margin: 0 0 .25rem; font-size: clamp(1.5rem, 4vw, 1.875rem); font-weight: 650; line-height: 1.2; overflow-wrap: anywhere; }
  .record-locality { margin: .15rem 0 .85rem; }
  .classification-overview { margin: 0 0 1rem; }
  .record-tabs { display: flex; border-bottom: 1px solid var(--line); }
  .record-tabs button { position: relative; min-height: 3rem; padding: .55rem 1.1rem; border: 0; border-bottom: 2px solid transparent; background: none; color: var(--ink-muted); overflow-wrap: anywhere; cursor: pointer; }
  .record-tabs button:hover { color: var(--ink); }
  .record-tabs button[aria-selected="true"] { border-bottom-color: var(--focus); color: var(--ink); font-weight: 650; }
  .record-tabs button:focus-visible { outline-offset: -3px; }
  .record-tab-content { padding-top: .75rem; }
  .record-tab-content[hidden] { display: none; }
  .record-tab-content:focus-visible { outline: 2px solid var(--focus); outline-offset: 3px; }
  .record-tab-content :global(.aphis-reports), .record-tab-content :global(.connections) { margin: 0; padding: 0; border-top: 0; }
  p { color: var(--ink-secondary); }
  .compact-source { display:flex;flex-wrap:wrap;align-items:center;column-gap:.3rem;color:var(--ink-muted);margin:0 0 .75rem;font-size:.8125rem;overflow-wrap:anywhere; }
  .direct-source { display:inline-flex;align-items:center;gap:.35rem;min-width:0;max-width:100%;min-height:44px;padding:.25rem 0; }
  .direct-source > span:first-child { min-width:0;overflow-wrap:anywhere; }
  .direct-source svg { width:.9rem;height:.9rem;flex:none;fill:none;stroke:currentColor;stroke-width:1.5; }
  .source-disclosure, .classification-disclosure { border-bottom:1px solid var(--line); }
  .classification-disclosure :global(summary) { width: auto; margin: 0; font-size: .875rem; }
  details > summary { min-height:2.75rem;padding:.65rem 0;cursor:pointer;font-size:.875rem; }
  details > dl { margin:0 0 .7rem; }
  .codebook-links { display:flex;flex-wrap:wrap;gap:0 1rem;margin:0; }
  .codebook-links a { display:inline-flex;align-items:center;min-height:2.75rem; }
  .map-action { margin:0; }.map-action a { display:inline-flex;align-items:center;min-height:2.75rem; }
  .record-category { margin: .25rem 0; }
  dl { margin: .25rem 0; }
  dl div { display: grid; grid-template-columns: 9rem minmax(0, 1fr); gap: .75rem; padding: .3rem 0; }
  dt { font-weight: 600; }
  dd { margin: 0; overflow-wrap: anywhere; color: var(--ink-secondary); }
  ul { margin: 0; padding-left: 1.1rem; }
  nav { display: flex; flex-wrap: wrap; gap: .6rem 1rem; margin-top: 1.25rem; }
  a { color: var(--link); text-underline-offset: .2em; }
  button { min-height: 2.75rem; padding: .4rem .6rem; background: var(--panel); border: 1px solid var(--line); color: var(--ink); font: inherit; }
  .sr-only { position: absolute; width: 1px; height: 1px; clip: rect(0, 0, 0, 0); overflow: hidden; white-space: nowrap; }
  .warning { padding: .75rem; border-left: 3px solid var(--focus); background: var(--panel); color: var(--ink); }
  a:focus-visible, button:focus-visible, summary:focus-visible { outline: 2px solid var(--focus); outline-offset: 3px; }
  @media (max-width: 40rem) { .public-record { width: calc(100% - 2rem); } .record-tabs button { flex: 1 1 0; min-width: 0; padding-inline: .3rem; } dl div { grid-template-columns: 1fr; gap: .15rem; } }
</style>
