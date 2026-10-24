<script lang="ts">
  import { LocalLocationRepository, type LocalProfile } from '../api/LocalLocationRepository';
  import type { DerivedSourceVolumeRange, Location } from '../domain/location';
  import { serializeRoute } from './routeState';
  import { precisionPresentation } from '../features/locations/precisionPresentation';
  import { publicReleaseLabel } from '../features/locations/releasePresentation';
  import RecordConnections from './RecordConnections.svelte';
  import { categoryPresentation } from '../features/locations/categoryPresentation';
  import { sourceClassificationLabels } from '../features/locations/sourceClassification';
  import LocationPreview from './LocationPreview.svelte';
  let copyFeedback = $state('');
  let { id, profile = 'official', releaseId, onrelease }: { id: string; profile?: LocalProfile; releaseId?: string | undefined; onrelease?: (label: string | null) => void } = $props();
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
  const category = (location: Location) => location.taxonomy?.primaryCategories.map(key => categoryPresentation(key).label).join(', ') || (location.category === 'unclassified' ? 'Category not provided' : humanLabel(location.category));
  const flagActivities = (location: Location) => affirmativeEntries(location.sourceFacts?.processingActivities).map(([key, value]) => `${sourceFlagLabel(key)}${typeof value === 'string' && !/^(?:yes|true|1)$/i.test(value.trim()) ? `: ${sourceFlag(value)}` : ''}`);
  const activityLabels = (location: Location) => [...new Set([
    ...(location.taxonomy?.leafActivities.map(activity => humanLabel(activity.label)) ?? []), ...flagActivities(location),
  ])];
  const isSummaryActivity = (location: Location, label: string) => location.taxonomy?.primaryCategories.some(key => categoryPresentation(key).label.toLocaleLowerCase() === label.toLocaleLowerCase()) ||
    (location.taxonomy?.primaryCategories.includes('processing_and_preparation') && label.toLocaleLowerCase() === 'processing' && activityLabels(location).some(other => other.toLocaleLowerCase() !== 'processing'));
  const detailActivity = (location: Location) => activityLabels(location).filter(label => !isSummaryActivity(location, label)).join(', ');
  const sourceClassifications = (location: Location) => sourceClassificationLabels(
    [location.sourceFacts?.nativeActivityLabel, location.sourceFacts?.nativeActivityCode],
    location.taxonomy?.assignments ?? [],
    activityLabels(location),
  );
  const geocodingConfidence = (location: Location) => {
    const raw = location.evidence?.geometryProvenance?.confidence;
    const score = raw?.trim() ? Number(raw) : NaN;
    return Number.isFinite(score) && score >= 0 && score <= 1 ? score : null;
  };
  const coordinate = (value: number) => String(Number(value.toFixed(6)));
  const locationMethod = (location: Location) => {
    const method = location.evidence?.geometryProvenance?.method;
    return method && !/^(?:source[_ -])?(?:method[_ -])?unknown$/i.test(method) ? humanLabel(method) : null;
  };
  const sourceFlag = (value: string | boolean) => value === true ? 'Yes' : typeof value === 'string' ? humanLabel(value) : null;
  const sourceFlagLabel = (key: string) => humanLabel(key);
  const affirmativeEntries = (flags: Readonly<Record<string, string | boolean>> | undefined) => flags ? Object.entries(flags).filter(([, value]) => value !== false).sort(([left], [right]) => left.localeCompare(right)) : [];
  const formattedRange = (range: DerivedSourceVolumeRange) => {
    const number = (value: number) => new Intl.NumberFormat('en-US').format(value);
    if (range.bounds === 'exclusive_upper' && range.upper !== null) return `Less than ${number(range.upper)}`;
    if (range.bounds === 'inclusive_lower_unbounded' && range.lower !== null) return `${number(range.lower)} or more`;
    if (range.bounds === 'inclusive_lower_exclusive_upper' && range.lower !== null && range.upper !== null) return `${number(range.lower)} to less than ${number(range.upper)}`;
    return null;
  };
  const slaughterRanges = (ranges: readonly DerivedSourceVolumeRange[] | undefined) => ranges?.filter(range => range.unit === 'head' && range.period === 'trailing_360_days') ?? [];
  const processingRanges = (ranges: readonly DerivedSourceVolumeRange[] | undefined) => ranges?.filter(range => range.unit === 'pounds' && range.period === 'month') ?? [];
  const annualSpeciesCount = (count: number) => new Intl.NumberFormat('en-US').format(count);
  const recordLink = $derived(`${window.location.origin}${window.location.pathname}${serializeRoute({kind:'record',facilityId:id,profile,...(currentRelease ? {releaseId:currentRelease} : {})})}`);
  async function copyRecordLink() { try { await navigator.clipboard.writeText(recordLink); copyFeedback = 'Facility link copied.'; } catch { copyFeedback = 'Could not copy facility link.'; } }
</script>
<svelte:head><title>{record?.name ?? 'Record'} · Until Every Cage</title></svelte:head>
<section class="public-record" aria-label="Public record">
  {#if profile === 'community'}<p class="warning"><strong>Unreviewed community claim: not verified by Until Every Cage.</strong> Privacy screening is not factual review or project approval. Community counts are separate.</p>{/if}
  {#if busy}<p role="status">Loading record…</p>{:else if error}<h1>Record unavailable</h1><p role="alert">{error}</p><button type="button" onclick={() => retry += 1}>Retry</button><p><a href="#/database">Browse records</a></p>{:else if record}<h1>{record.name} <button class="share" type="button" aria-label="Copy facility link" title="Copy facility link" onclick={copyRecordLink}><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.1 0l3-3A5 5 0 0 0 13 2.9l-1.7 1.7m2.7 6.4a5 5 0 0 0-7.1 0l-3 3A5 5 0 0 0 11 21.1l1.7-1.7"/></svg></button><span class="sr-only" role="status" aria-live="polite">{copyFeedback}</span></h1><p>{category(record)}</p>
    {#if detailActivity(record)}<dl><div><dt>Activities</dt><dd>{detailActivity(record)}</dd></div></dl>{/if}
    {#if sourceClassifications(record).length}<p class="classification">{sourceClassifications(record).join(' · ')}</p>{/if}
    {#if record.lat !== null && record.lon !== null}<LocationPreview latitude={record.lat} longitude={record.lon} precision={record.evidence?.displayPrecision ?? 'unmapped'} category={record.taxonomy?.primaryCategories[0] ?? record.category} />{/if}
    <section aria-labelledby="location-heading">
      <h2 id="location-heading">Location</h2>
      <dl>
        <div><dt>Locality</dt><dd>{[record.region, record.countryCode].filter(Boolean).join(', ')}</dd></div>
        {#if record.lat !== null && record.lon !== null}<div><dt>Coordinates</dt><dd>{coordinate(record.lat)}, {coordinate(record.lon)}</dd></div>{/if}
        <div><dt>Precision</dt><dd>{precision}</dd></div>
        {#if locationMethod(record)}<div><dt>Location method</dt><dd>{locationMethod(record)}</dd></div>{/if}
        {#if record.evidence?.geometryProvenance?.provider}<div><dt>Geocoding provider</dt><dd>{record.evidence.geometryProvenance.provider}</dd></div>{/if}
        {#if geocodingConfidence(record) !== null || record.evidence?.geometryProvenance?.confidence_band}<div><dt>Geocoding confidence</dt><dd>{#if geocodingConfidence(record) !== null}{geocodingConfidence(record)} (provider score){/if}{#if record.evidence?.geometryProvenance?.confidence_band}{geocodingConfidence(record) !== null ? ' · ' : ''}{humanLabel(record.evidence.geometryProvenance.confidence_band)}{/if}</dd></div>{/if}
      </dl>
    </section>
    {#if record.sourceFacts}
      <section class="source-facts" aria-labelledby="source-facts-heading">
        <h2 id="source-facts-heading">Source facts</h2>
        <dl>
          {#if record.sourceFacts.alternateNames?.length}<div><dt>Also known as</dt><dd>{record.sourceFacts.alternateNames.join(' · ')}</dd></div>{/if}
          {#if record.sourceFacts.establishmentId}<div><dt>Establishment ID</dt><dd>{record.sourceFacts.establishmentId}</dd></div>{/if}
          {#if record.sourceFacts.establishmentNumber}<div><dt>Establishment number</dt><dd>{record.sourceFacts.establishmentNumber}</dd></div>{/if}
          {#if record.sourceFacts.grantDate}<div><dt>Grant date</dt><dd>{record.sourceFacts.grantDate}</dd></div>{/if}
          {#if affirmativeEntries(record.sourceFacts.speciesSlaughtered).length}<div><dt>Species slaughtered</dt><dd>{affirmativeEntries(record.sourceFacts.speciesSlaughtered).map(([key, value]) => `${sourceFlagLabel(key)}${typeof value === 'string' ? `: ${sourceFlag(value)}` : ''}`).join(', ')}</dd></div>{/if}
          {#if slaughterRanges(record.sourceFacts.derivedSourceVolumeRanges).length}<div><dt>Estimated animals slaughtered (last 360 days)</dt><dd>{slaughterRanges(record.sourceFacts.derivedSourceVolumeRanges).map(range => formattedRange(range) ? `${formattedRange(range)} animals` : null).filter(Boolean).join(', ')}</dd></div>{/if}
          {#if processingRanges(record.sourceFacts.derivedSourceVolumeRanges).length}<div><dt>Estimated product volume (pounds/month)</dt><dd>{processingRanges(record.sourceFacts.derivedSourceVolumeRanges).map(range => formattedRange(range) ? `${formattedRange(range)} pounds/month` : null).filter(Boolean).join(', ')}</dd></div>{/if}
          {#if record.sourceFacts.aphisAnnualReports?.length}{#each record.sourceFacts.aphisAnnualReports as report (report.fiscalYear)}<div><dt>FY{report.fiscalYear} reported animals</dt><dd><ul>{#each report.speciesCounts as species (species.species)}<li>{sourceFlagLabel(species.species)}: {annualSpeciesCount(species.count)}</li>{/each}</ul><a href={report.sourceUrl} target="_blank" rel="noopener noreferrer">Source report</a></dd></div>{/each}{/if}
        </dl>
      </section>
    {/if}
    <RecordConnections facilityId={record.id} releaseId={currentRelease} {profile} sourceId={record.sourceId} sourceFacts={record.sourceFacts} />
    <section aria-labelledby="source-heading">
      <h2 id="source-heading">Source and review</h2>
      <dl><div><dt>Source</dt><dd>{record.source} {#if record.evidence?.sourceUrl}<a href={record.evidence.sourceUrl} target="_blank" rel="noreferrer">Open source</a>{/if}</dd></div><div><dt>Source origin</dt><dd>{record.evidence?.sourceType === 'user_submitted' ? 'Community-submitted' : record.evidence?.sourceType === 'secondary' ? 'Secondary source' : 'Government-sourced'}</dd></div>{#if record.observed !== 'unknown'}<div><dt>Observed</dt><dd>{record.observed}</dd></div>{/if}{#if record.evidence?.retrievedAt}<div><dt>Retrieved</dt><dd>{record.evidence.retrievedAt}</dd></div>{/if}<div><dt>Publication</dt><dd>{profile === 'official' ? 'Curated records' : profile === 'community' ? 'Community submissions' : 'Secondary sources'} · {publicReleaseLabel(currentRelease)}</dd></div></dl>
    </section>
    <nav aria-label="Record contribution actions">{#each [['evidence','Add evidence'],['correction','Suggest a correction'],['privacy-removal','Privacy or removal']] as [type,label]}<a href={`#/contribute/${type}?target=${encodeURIComponent(record.id)}`}>{label}</a>{/each}</nav>
  {/if}
</section>
<style>
  .public-record { width: min(100% - 3rem, 46rem); margin: auto; padding: 1.5rem 0 2rem; color: #edf0e9; font: .9rem/1.5 system-ui, sans-serif; }
  h1 { margin: 0 0 .75rem; font: 500 2rem/1.2 Georgia, serif; overflow-wrap: anywhere; }
  h2 { margin: 1.5rem 0 0; font: 600 1.05rem/1.3 Georgia, serif; }
  p { color: #c6d0c5; }
  .classification { margin: .35rem 0; }
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
