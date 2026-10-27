<script lang="ts">
  import { onDestroy } from 'svelte';
  import { language, tr } from './language';
  import { LocalLocationRepository, type LocalProfile } from '../api/LocalLocationRepository';
  import type { DerivedSourceVolumeRange, Location } from '../domain/location';
  import { mapHrefFromParams, safeMapHref, serializeRoute } from './routeState';
  import { precisionPresentation } from '../features/locations/precisionPresentation';
  import { publicReleaseLabel } from '../features/locations/releasePresentation';
  import RecordConnections from './RecordConnections.svelte';
  import CategoryBadge from '../features/locations/CategoryBadge.svelte';
  import ClassificationSummary from '../features/locations/ClassificationSummary.svelte';
  import { affirmativeSourceEntries } from '../features/locations/classificationSummary';
  import LocationPreview from './LocationPreview.svelte';
  import { locationPreviewZoom } from '../features/locations/locationPreview';
  let copyFeedback = $state<'copied' | 'failed' | ''>('');
  let copyResetTimer: ReturnType<typeof setTimeout> | undefined;
  let copyAttempt = 0;
  onDestroy(() => { copyAttempt += 1; if (copyResetTimer) clearTimeout(copyResetTimer); });
  let { id, profile = 'official', releaseId, returnMapHref = '#/map', onrelease }: { id: string; profile?: LocalProfile; releaseId?: string | undefined; returnMapHref?: string; onrelease?: (label: string | null) => void } = $props();
  const repository = new LocalLocationRepository();
  let record = $state<Location | null>(null);
  let currentRelease = $state('');
  let busy = $state(true);
  let error = $state('');
  let retry = $state(0);
  $effect(() => {
    void retry;
    const controller = new AbortController(); record = null; busy = true; error = '';
    void repository.detail(id, profile, controller.signal, releaseId).then(result => { if (!controller.signal.aborted) { record = result.location; currentRelease = result.releaseId; onrelease?.(result.releaseId); } }).catch(cause => { if (!controller.signal.aborted) error = cause && typeof cause === 'object' && 'kind' in cause && cause.kind === 'restricted' ? 'This record is unavailable in the selected public release.' : 'This record could not be loaded. Try again.'; }).finally(() => { if (!controller.signal.aborted) busy = false; });
    return () => controller.abort();
  });
  const precision = $derived(precisionPresentation(record?.evidence?.displayPrecision));
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
  const slaughterRanges = (ranges: readonly DerivedSourceVolumeRange[] | undefined) => ranges?.filter(range => range.unit === 'head' && range.period === 'trailing_360_days') ?? [];
  const processingRanges = (ranges: readonly DerivedSourceVolumeRange[] | undefined) => ranges?.filter(range => range.unit === 'pounds' && range.period === 'month') ?? [];
  const annualSpeciesCount = (count: number) => new Intl.NumberFormat($language).format(count);
  const recordLink = $derived(`${window.location.origin}${window.location.pathname}${serializeRoute({kind:'record',facilityId:id,profile,...(currentRelease ? {releaseId:currentRelease} : {}),returnMapHref})}`);
  const openMapHref = $derived(record && record.lat !== null && record.lon !== null ? (() => {
    const params = new URLSearchParams((safeMapHref(returnMapHref) ?? '#/map').split('?')[1] ?? '');
    params.set('lat', String(record.lat)); params.set('lon', String(record.lon));
    params.set('z', String(locationPreviewZoom(record.evidence?.displayPrecision)));
    params.set('selected', record.id);
    return mapHrefFromParams(params, currentRelease || releaseId, record.id);
  })() : null);
  async function copyRecordLink() {
    const attempt = ++copyAttempt;
    if (copyResetTimer) clearTimeout(copyResetTimer);
    let copied = true;
    try { await navigator.clipboard.writeText(recordLink); }
    catch { copied = false; }
    if (attempt !== copyAttempt) return;
    copyFeedback = copied ? 'copied' : 'failed';
    copyResetTimer = setTimeout(() => { if (attempt === copyAttempt) copyFeedback = ''; copyResetTimer = undefined; }, copied ? 1500 : 2500);
  }
</script>
<svelte:head><title>{record?.name ?? tr('Record', $language)} · Until Every Cage</title></svelte:head>
<section class="public-record" aria-label={tr('Public record', $language)}>
  {#if profile === 'community'}<p class="warning"><strong>{tr("Unreviewed community claim: not verified by Until Every Cage.", $language)}</strong> {tr("Privacy screening is not factual review or project approval. Community counts are separate.", $language)}</p>{/if}
  {#if busy}<p role="status">{tr('Loading record…', $language)}</p>{:else if error}<h1>{tr("Record unavailable", $language)}</h1><p role="alert">{tr(error, $language)}</p><button type="button" onclick={() => retry += 1}>{tr("Retry", $language)}</button><p><a href="#/database">{tr("Browse records", $language)}</a></p>{:else if record}<h1>{record.name} <button class="share" type="button" aria-label={tr('Copy facility link', $language)} title={tr('Copy facility link', $language)} onclick={copyRecordLink}><svg aria-hidden="true" viewBox="0 0 24 24">{#if copyFeedback === 'copied'}<path d="m5 12 4 4L19 6"/>{:else if copyFeedback === 'failed'}<path d="M6 6l12 12M18 6 6 18"/>{:else}<path d="M10 13a5 5 0 0 0 7.1 0l3-3A5 5 0 0 0 13 2.9l-1.7 1.7m2.7 6.4a5 5 0 0 0-7.1 0l-3 3A5 5 0 0 0 11 21.1l1.7-1.7"/>{/if}</svg></button><span class="sr-only" role="status" aria-live="polite">{copyFeedback === 'copied' ? tr('Link copied', $language) : copyFeedback === 'failed' ? tr('Could not copy facility link', $language) : ''}</span></h1>
    <section class="classification-overview" aria-labelledby="activities-heading">
      <h2 id="activities-heading" class="sr-only">{tr('Activities and classification', $language)}</h2>
      <div class="record-category"><CategoryBadge {record} /></div>
      <ClassificationSummary {record} />
    </section>
    <section aria-labelledby="location-heading">
      <h2 id="location-heading">{tr('Location', $language)}</h2>
      <dl>
        <div><dt>{tr('Locality', $language)}</dt><dd>{[record.region, record.countryCode].filter(Boolean).join(', ')}</dd></div>
        {#if record.lat !== null && record.lon !== null}<div><dt>{tr('Coordinates', $language)}</dt><dd>{coordinate(record.lat)}, {coordinate(record.lon)}</dd></div>{/if}
        <div><dt>{tr('Precision', $language)}</dt><dd>{tr(precision, $language)}</dd></div>
        {#if locationMethod(record)}<div><dt>{tr('Location method', $language)}</dt><dd>{locationMethod(record)}</dd></div>{/if}
        {#if record.evidence?.geometryProvenance?.provider}<div><dt>{tr('Geocoding provider', $language)}</dt><dd>{record.evidence.geometryProvenance.provider}</dd></div>{/if}
        {#if geocodingConfidence(record) !== null || record.evidence?.geometryProvenance?.confidence_band}<div><dt>{tr('Geocoding confidence', $language)}</dt><dd>{#if geocodingConfidence(record) !== null}{geocodingConfidence(record)} ({tr('provider score', $language)}){/if}{#if record.evidence?.geometryProvenance?.confidence_band}{geocodingConfidence(record) !== null ? ' · ' : ''}{translatedGenerated(record.evidence.geometryProvenance.confidence_band)}{/if}</dd></div>{/if}
      </dl>
      {#if openMapHref}<p class="map-action"><a href={openMapHref}><svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/></svg>{tr('Open in Map', $language)}</a></p>{/if}
    </section>
    {#if record.lat !== null && record.lon !== null}<LocationPreview latitude={record.lat} longitude={record.lon} precision={record.evidence?.displayPrecision ?? 'unmapped'} category={record.taxonomy?.primaryCategories[0] ?? record.category} />{/if}
    {#if record.sourceFacts}
      <section class="source-facts" aria-labelledby="source-facts-heading">
        <h2 id="source-facts-heading">{tr('Source facts', $language)}</h2>
        <dl>
          {#if record.sourceFacts.alternateNames?.length}<div><dt>{tr('Also known as', $language)}</dt><dd>{record.sourceFacts.alternateNames.join(' · ')}</dd></div>{/if}
          {#if record.sourceFacts.establishmentId}<div><dt>{tr('Establishment ID', $language)}</dt><dd>{record.sourceFacts.establishmentId}</dd></div>{/if}
          {#if record.sourceFacts.establishmentNumber}<div><dt>{tr('Establishment number', $language)}</dt><dd>{record.sourceFacts.establishmentNumber}</dd></div>{/if}
          {#if record.sourceFacts.grantDate}<div><dt>{tr('Grant date', $language)}</dt><dd>{record.sourceFacts.grantDate}</dd></div>{/if}
          {#if affirmativeEntries(record.sourceFacts.speciesSlaughtered).length}<div><dt>{tr('Species slaughtered', $language)}</dt><dd>{affirmativeEntries(record.sourceFacts.speciesSlaughtered).map(([key, value]) => `${sourceFlagLabel(key)}${typeof value === 'string' ? `: ${sourceFlag(value)}` : ''}`).join(', ')}</dd></div>{/if}
          {#if slaughterRanges(record.sourceFacts.derivedSourceVolumeRanges).length}<div><dt>{tr('Estimated animals slaughtered (last 360 days)', $language)}</dt><dd>{slaughterRanges(record.sourceFacts.derivedSourceVolumeRanges).map(range => formattedRangeLocalized(range) ? `${formattedRangeLocalized(range)} ${tr('animals', $language)}` : null).filter(Boolean).join(', ')}</dd></div>{/if}
          {#if processingRanges(record.sourceFacts.derivedSourceVolumeRanges).length}<div><dt>{tr('Estimated product volume (pounds/month)', $language)}</dt><dd>{processingRanges(record.sourceFacts.derivedSourceVolumeRanges).map(range => formattedRangeLocalized(range) ? `${formattedRangeLocalized(range)} ${tr('pounds/month', $language)}` : null).filter(Boolean).join(', ')}</dd></div>{/if}
          {#if record.sourceFacts.aphisAnnualReports?.length}{#each record.sourceFacts.aphisAnnualReports as report (report.fiscalYear)}<div><dt>{tr('FY', $language)}{report.fiscalYear} {tr('reported animals', $language)}</dt><dd><ul>{#each report.speciesCounts as species (species.species)}<li>{sourceFlagLabel(species.species)}: {annualSpeciesCount(species.count)}</li>{/each}</ul><a href={report.sourceUrl} target="_blank" rel="noopener noreferrer">{tr('Source report', $language)}</a></dd></div>{/each}{/if}
        </dl>
      </section>
    {/if}
    <RecordConnections facilityId={record.id} releaseId={currentRelease} {profile} sourceId={record.sourceId} sourceFacts={record.sourceFacts} />
    <section aria-labelledby="source-heading">
      <h2 id="source-heading">{tr('Source and review', $language)}</h2>
      <dl><div><dt>{tr('Source', $language)}</dt><dd>{record.source} {#if record.evidence?.sourceUrl}<a href={record.evidence.sourceUrl} target="_blank" rel="noreferrer">{tr('Open source', $language)}</a>{/if}</dd></div><div><dt>{tr('Source origin', $language)}</dt><dd>{record.evidence?.sourceType === 'user_submitted' ? tr('Community-submitted', $language) : record.evidence?.sourceType === 'secondary' ? tr('Secondary source', $language) : tr('Government-sourced', $language)}</dd></div>{#if record.observed !== 'unknown'}<div><dt>{tr('Observed', $language)}</dt><dd>{record.observed}</dd></div>{/if}{#if record.evidence?.retrievedAt}<div><dt>{tr('Retrieved', $language)}</dt><dd>{record.evidence.retrievedAt}</dd></div>{/if}<div><dt>{tr('Publication', $language)}</dt><dd>{tr(profile === 'official' ? 'Curated records' : profile === 'community' ? 'Community submissions' : 'Secondary sources', $language)} · {publicReleaseLabel(currentRelease)}</dd></div></dl>
    </section>
    <nav aria-label={tr('Record contribution actions', $language)}>{#each [['evidence','Add evidence'],['correction','Suggest a correction'],['privacy-removal','Privacy or removal']] as [type,label]}<a href={`#/contribute/${type}?target=${encodeURIComponent(record.id)}`}>{tr(label ?? '', $language)}</a>{/each}</nav>
  {/if}
</section>
<style>
  .public-record { width: min(100% - 3rem, 46rem); margin: auto; padding: 1.5rem 0 2rem; color: #edf0e9; font: .9rem/1.5 system-ui, sans-serif; }
  h1 { margin: 0 0 .75rem; font: 500 2rem/1.2 Georgia, serif; overflow-wrap: anywhere; }
  h2 { margin: 1.5rem 0 0; font: 600 1.05rem/1.3 Georgia, serif; }
  p { color: #c6d0c5; }
  .map-action a { display:inline-flex;align-items:center;gap:.5rem;min-height:2.75rem; }.map-action svg { width:1rem;height:1rem;flex:none;fill:none;stroke:currentColor;stroke-width:1.5; }
  .record-category { margin: .25rem 0; }
  dl { margin: 1.25rem 0; }
  .source-facts dl { margin: .4rem 0; }
  dl div { display: grid; grid-template-columns: 9rem minmax(0, 1fr); gap: 1rem; padding: .55rem 0; border-bottom: 1px solid #3c4640; }
  dt { font-weight: 600; }
  dd { margin: 0; overflow-wrap: anywhere; color: #c6d0c5; }
  ul { margin: 0; padding-left: 1.1rem; }
  nav { display: flex; flex-wrap: wrap; gap: .6rem 1rem; margin-top: 1.25rem; }
  a { color: #dce8d9; text-underline-offset: .2em; }
  button { min-height: 2.25rem; padding: .4rem .6rem; background: #252f28; border: 1px solid #657466; color: #edf0e9; font: inherit; }
  .share { display: inline-grid; place-items: center; vertical-align: middle; min-height: 2rem; width: 2rem; padding: .3rem; }
  .share svg { width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
  .sr-only { position: absolute; width: 1px; height: 1px; clip: rect(0, 0, 0, 0); overflow: hidden; white-space: nowrap; }
  .warning { padding: .75rem; border-left: 3px solid #cf9a66; background: #282723; color: #eee4ce; }
  a:focus-visible, button:focus-visible { outline: 2px solid #eee7d6; outline-offset: 3px; }
  @media (max-width: 40rem) { .public-record { width: calc(100% - 2rem); } h1 { font-size: 1.65rem; } dl div { grid-template-columns: 1fr; gap: .15rem; } }
</style>
