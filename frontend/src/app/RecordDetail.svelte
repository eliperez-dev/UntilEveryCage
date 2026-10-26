<script lang="ts">
  import { onDestroy } from 'svelte';
  import { language, tr } from './language';
  import RecordConnections from './RecordConnections.svelte';
  import LocationPreview from './LocationPreview.svelte';
  import { serializeRoute } from './routeState';
  import type { LabRecord } from '../design-lab/contract';
  import CategoryBadge from '../features/locations/CategoryBadge.svelte';
  import ClassificationSummary from '../features/locations/ClassificationSummary.svelte';
  import { affirmativeSourceEntries } from '../features/locations/classificationSummary';
  import type { TaxonomyClassification } from '../domain/taxonomy';
  import type { DerivedSourceVolumeRange, LocationSourceFacts } from '../domain/location';

  /** Safe fields returned by the local private-preview detail projection. */
  export type RecordDetailRecord = Partial<Omit<LabRecord, 'name' | 'category'>> & {
    id?: string;
    candidateId?: string;
    candidate_id?: string;
    name?: string | null;
    displayName?: string | null;
    display_name?: string | null;
    category?: string | null;
    activityLabel?: string | null;
    activity_label?: string | null;
    activitySource?: string | null;
    activity_source?: string | null;
    sourceId?: string | null;
    source_id?: string | null;
    sourceName?: string | null;
    source_name?: string | null;
    safeSourceRecordId?: string | null;
    sourceRecordId?: string | null;
    source_record_id?: string | null;
    sourceUrl?: string | null;
    sourceLocationRole?: 'aphis_mailing_locality' | null;
    source_location_role?: 'aphis_mailing_locality' | null;
    source_url?: string | null;
    sourceRecordUrl?: string | null;
    source_record_url?: string | null;
    retrievedAt?: string | null;
    retrieved_at?: string | null;
    observedAt?: string | null;
    observed_at?: string | null;
    evidenceSummary?: string | null;
    evidence_summary?: string | null;
    locality?: string | null;
    country?: string | null;
    precision?: LabRecord['precision'] | null;
    latitude?: number | null;
    longitude?: number | null;
    reviewStatus?: string | null;
    coordinateReviewStatus?: string | null;
    coordinate_review_status?: string | null;
    factualReviewStatus?: string | null;
    factual_review_status?: string | null;
    privacyScreeningStatus?: string | null;
    privacy_screening_status?: string | null;
    publicationStatus?: string | null;
    publication_status?: string | null;
    projectApproval?: string | boolean | null;
    previewLabel?: string | null;
    coordinatePrecision?: string | null;
    coordinateProvenance?: string | null;
    coordinate_provenance?: string | null;
    defaultMapScope?: boolean | null;
    default_map_scope?: boolean | null;
    mapScopeReason?: string | null;
    map_scope_reason?: string | null;
    displayPrecision?: string | null;
    display_precision?: string | null;
    taxonomy?: TaxonomyClassification | null;
    sourceFacts?: LocationSourceFacts;
  };

  let {
    record,
    presentation = 'rail',
    publicRelease = false,
    publicReleaseId,
    fullRecordHref = null,
    onclose,
    oncategoryfilter,
    onsourcefilter,
  }: {
    record: LabRecord | RecordDetailRecord;
    presentation?: 'rail' | 'page';
    publicRelease?: boolean;
    publicReleaseId?: string | null;
    fullRecordHref?: string | null;
    onclose?: () => void;
    oncategoryfilter?: ((key: string) => void) | undefined;
    onsourcefilter?: ((sourceId: string) => void) | undefined;
  } = $props();
  let copyFeedback = $state<'copied' | 'failed' | ''>('');
  let copyResetTimer: ReturnType<typeof setTimeout> | undefined;
  let copyAttempt = 0;
  onDestroy(() => { copyAttempt += 1; if (copyResetTimer) clearTimeout(copyResetTimer); });


  const value = (...items: Array<string | null | undefined>) =>
    items.find((item) => typeof item === 'string' && item.trim())?.trim() ?? null;

  const id = $derived(
    value(
      record.id,
      'candidateId' in record ? record.candidateId : null,
      'candidate_id' in record ? record.candidate_id : null,
    ) ?? '',
  );
  const safeDisplayName = $derived(
    value(
      'displayName' in record ? record.displayName : null,
      'display_name' in record ? record.display_name : null,
    ),
  );
  const nameWithheld = $derived(
    ('displayName' in record || 'display_name' in record) && !safeDisplayName,
  );
  const name = $derived(nameWithheld
    ? 'Name not shown'
    : safeDisplayName ?? value(record.name) ?? 'Name not provided');
  const activity = $derived(
    value(
      'activityLabel' in record ? record.activityLabel : null,
      'activity_label' in record ? record.activity_label : null,
      record.category,
    ),
  );
  const taxonomy = $derived('taxonomy' in record ? record.taxonomy ?? null : null);
  const sourceId = $derived(
    value(record.sourceId, 'source_id' in record ? record.source_id : null),
  );
  const sourceName = $derived(
    value(
      'sourceName' in record ? record.sourceName : null,
      'source_name' in record ? record.source_name : null,
    ),
  );
  const sourceUrl = $derived(
    safeHttps(
      value(
        'sourceUrl' in record ? record.sourceUrl : null,
        'source_url' in record ? record.source_url : null,
      ),
    ),
  );
  const sourceRecordUrl = $derived(
    safeHttps(
      value(
        'sourceRecordUrl' in record ? record.sourceRecordUrl : null,
        'source_record_url' in record ? record.source_record_url : null,
      ),
    ),
  );
  const precision = $derived(
    value(
      record.precision,
      'displayPrecision' in record ? record.displayPrecision : null,
      'display_precision' in record ? record.display_precision : null,
    ) ?? 'unmapped',
  );
  const coordinateStatus = $derived(
    value(
      record.reviewStatus,
      'coordinateReviewStatus' in record ? record.coordinateReviewStatus : null,
      'coordinate_review_status' in record ? record.coordinate_review_status : null,
    ),
  );
  const coordinateProvenance = $derived(
    value(
      'coordinateProvenance' in record ? record.coordinateProvenance : null,
      'coordinate_provenance' in record ? record.coordinate_provenance : null,
    ),
  );
  const recordedCoordinateMethod = $derived(value(record.coordinateMethod, coordinateProvenance));
  const coordinateMethod = $derived(recordedCoordinateMethod && !/^(?:source[_ -])?(?:method[_ -])?unknown$/i.test(recordedCoordinateMethod) ? recordedCoordinateMethod : null);
  const coordinateProvider = $derived(value(record.coordinateProvider));
  const facilityAddress = $derived(value(record.facilityAddress));
  const hasCoordinates = $derived(typeof record.latitude === 'number' && Number.isFinite(record.latitude) && typeof record.longitude === 'number' && Number.isFinite(record.longitude));
  const coordinateConfidence = $derived(typeof record.coordinateConfidence === 'number' && Number.isFinite(record.coordinateConfidence) && record.coordinateConfidence >= 0 && record.coordinateConfidence <= 1 ? record.coordinateConfidence : null);
  const defaultMapScope = $derived(
    'defaultMapScope' in record ? record.defaultMapScope : 'default_map_scope' in record ? record.default_map_scope : null,
  );
  const mapScopeReason = $derived(
    value('mapScopeReason' in record ? record.mapScopeReason : null, 'map_scope_reason' in record ? record.map_scope_reason : null),
  );
  const publicationStatus = $derived(
    value(
      'publicationStatus' in record ? record.publicationStatus : null,
      'publication_status' in record ? record.publication_status : null,
    ),
  );
  const retrieved = $derived(
    value(
      'retrievedAt' in record ? record.retrievedAt : null,
      'retrieved_at' in record ? record.retrieved_at : null,
    ),
  );
  const observed = $derived(
    value(
      'observedAt' in record ? record.observedAt : null,
      'observed_at' in record ? record.observed_at : null,
    ),
  );
  const evidence = $derived(
    value(
      'evidenceSummary' in record ? record.evidenceSummary : null,
      'evidence_summary' in record ? record.evidence_summary : null,
    ),
  );
  const activitySource = $derived(
    value(
      'activitySource' in record ? record.activitySource : null,
      'activity_source' in record ? record.activity_source : null,
    ),
  );
  const sourceRecordId = $derived(
    value(
      'safeSourceRecordId' in record ? record.safeSourceRecordId : null,
      'sourceRecordId' in record ? record.sourceRecordId : null,
      'source_record_id' in record ? record.source_record_id : null,
    ),
  );
  const sourceLocationRole = $derived(value('sourceLocationRole' in record ? record.sourceLocationRole : null, 'source_location_role' in record ? record.source_location_role : null));
  const locationText = $derived(
    [value(record.locality), value(record.country)].filter(Boolean).join(', ') ||
      'Location unavailable',
  );
  const precisionLabel = $derived(
    (record.sourceId === 'us.fsis' || record.previewLabel?.startsWith('FSIS source-provided')) && record.coordinatePrecision === 'source-provided'
      ? tr('Source-provided coordinates', $language)
      : tr(precisionLabelFor(record.coordinatePrecision?.includes('provider_address') ? record.coordinatePrecision : precision), $language),
  );
  const sourceFacts = $derived('sourceFacts' in record ? record.sourceFacts : undefined);
  const speciesSlaughtered = $derived(compactSourceFacts(sourceFacts, 'speciesSlaughtered'));
  const classificationRecord = $derived({ category: activity, taxonomy, sourceId, sourceFacts, activitySource });

  function humanizeValue(raw: string | null): string | null {
    if (!raw) return null;

    // These are display labels only; keep the repository's canonical enum untouched.
    const words = raw.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/\b(nrte|rte)\b/gi, acronym => acronym.toUpperCase());
    return words ? words[0]!.toLocaleUpperCase() + words.slice(1) : null;
  }
  function displayGeneratedValue(raw: string | null): string | null {
    const label = humanizeValue(raw);
    return label ? tr(label, $language) : null;
  }
  function sourceFactLabel(raw: string): string {
    return humanizeValue(raw) ?? raw;
  }
  function sameLabel(left: string, right: string): boolean {
    return humanizeValue(left)?.toLocaleLowerCase() === humanizeValue(right)?.toLocaleLowerCase();
  }
  function coordinate(value: number | null | undefined): string {
    return typeof value === 'number' ? String(Number(value.toFixed(6))) : '';
  }
  function sourceFactLabels(facts: LocationSourceFacts | undefined, field: 'speciesSlaughtered' | 'processingActivities', localizeGenerated = true): string[] {
    const entries = facts?.[field]
      ? affirmativeSourceEntries(facts[field])
      : [];
    return entries.map(([name, included]) => {
      const label = field === 'processingActivities' ? (localizeGenerated ? displayGeneratedValue(name) : humanizeValue(name)) ?? name : sourceFactLabel(name);
      if (typeof included !== 'string' || !included.trim() || /^(?:yes|true|1)$/i.test(included.trim())) return label;
      return `${label}: ${field === 'processingActivities' && localizeGenerated ? displayGeneratedValue(included) ?? included : humanizeValue(included) ?? included}`;
    });
  }
  function compactSourceFacts(facts: LocationSourceFacts | undefined, field: 'speciesSlaughtered' | 'processingActivities'): string | null {
    return sourceFactLabels(facts, field).join(', ') || null;
  }
  function formattedRange(range: DerivedSourceVolumeRange): string | null {
    const number = (value: number) => new Intl.NumberFormat('en-US').format(value);
    if (range.bounds === 'exclusive_upper' && range.upper !== null) return `${tr('Less than', $language)} ${number(range.upper)}`;
    if (range.bounds === 'inclusive_lower_unbounded' && range.lower !== null) return `${number(range.lower)} ${tr('or more', $language)}`;
    if (range.bounds === 'inclusive_lower_exclusive_upper' && range.lower !== null && range.upper !== null) return `${number(range.lower)} ${tr('to less than', $language)} ${number(range.upper)}`;
    return null;
  }
  function annualSpeciesCount(count: number): string { return new Intl.NumberFormat('en-US').format(count); }
  const slaughterRanges = $derived(sourceFacts?.derivedSourceVolumeRanges?.filter(range => range.unit === 'head' && range.period === 'trailing_360_days') ?? []);
  const processingRanges = $derived(sourceFacts?.derivedSourceVolumeRanges?.filter(range => range.unit === 'pounds' && range.period === 'month') ?? []);
  const slaughterRangeText = $derived(slaughterRanges.map(formattedRange).filter((range): range is string => Boolean(range)).map(range => `${range} ${tr('animals', $language)}`).join(', '));
  const processingRangeText = $derived(processingRanges.map(formattedRange).filter((range): range is string => Boolean(range)).map(range => `${range} ${tr('pounds/month', $language)}`).join(', '));

  function safeHttps(raw: string | null): string | null {
    if (!raw) return null;
    try {
      const url = new URL(raw);
      // External evidence links are shown only for encrypted web URLs.
      return url.protocol === 'https:' ? url.href : null;
    } catch { return null; }
  }
  function precisionLabelFor(raw: string): string {
    if (raw === 'source_reported') {
      return 'Source-provided coordinates';
    }
    if (raw === 'approximate') {
      return 'Approximate location';
    }
    if (raw === 'source_provided_unverified') {
      return 'Source-provided coordinates';
    }
    if (raw === 'exact' || raw.includes('source_numeric')) {
      return 'Source coordinate · review status shown below';
    }
    if (raw === 'city' || raw.includes('city_reference')) {
      return 'Approximate location';
    }
    if (raw.includes('provider_locality') || raw.includes('provider_address')) return 'Approximate location';
    if (raw === 'coarse' || raw.includes('city_postal')) {
      return 'Approximate location';
    }
    if (raw === 'approximate' || raw.includes('approximate')) {
      return 'Approximate location';
    }
    return 'Unmapped · no map location supplied';
  }
  const facilityLink = $derived(`${window.location.origin}${window.location.pathname}${serializeRoute({ kind: 'record', facilityId: id, profile: 'official', ...(publicReleaseId ? { releaseId: publicReleaseId } : {}) })}`);
  async function copyFacilityLink() {
    const attempt = ++copyAttempt;
    if (copyResetTimer) clearTimeout(copyResetTimer);
    let copied = true;
    try { await navigator.clipboard.writeText(facilityLink); }
    catch { copied = false; }
    if (attempt !== copyAttempt) return;
    copyFeedback = copied ? 'copied' : 'failed';
    copyResetTimer = setTimeout(() => { if (attempt === copyAttempt) copyFeedback = ''; copyResetTimer = undefined; }, copied ? 1500 : 2500);
  }
</script>

<article
  class:page={presentation === 'page'}
  class="detail"
  aria-labelledby="record-title"
>
  {#if onclose}
    <button
      class="close"
      type="button"
      aria-label={tr('Close record detail', $language)}
      onclick={onclose}
    >{tr('Close', $language)}</button>
  {/if}
  <h1 id="record-title">{name}{#if presentation === 'page' || (presentation === 'rail' && publicRelease)} <button class="share" type="button" aria-label={tr('Copy facility link', $language)} title={tr('Copy facility link', $language)} onclick={copyFacilityLink}><svg aria-hidden="true" viewBox="0 0 24 24">{#if copyFeedback === 'copied'}<path d="m5 12 4 4L19 6"/>{:else if copyFeedback === 'failed'}<path d="M6 6l12 12M18 6 6 18"/>{:else}<path d="M10 13a5 5 0 0 0 7.1 0l3-3A5 5 0 0 0 13 2.9l-1.7 1.7m2.7 6.4a5 5 0 0 0-7.1 0l-3 3A5 5 0 0 0 11 21.1l1.7-1.7"/>{/if}</svg></button><span class="sr-only" role="status" aria-live="polite">{copyFeedback === 'copied' ? tr('Link copied', $language) : copyFeedback === 'failed' ? tr('Could not copy facility link', $language) : ''}</span>{/if}</h1>
  {#if presentation === 'rail' && fullRecordHref}<a class="open-facility" href={fullRecordHref}><span>{tr('Open facility page', $language)}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7M7 7h10v10"/></svg></a>{/if}
  <section class="classification-overview" aria-labelledby="taxonomy-heading">
    <h2 id="taxonomy-heading" class="sr-only">{tr('Activities and classification', $language)}</h2>
    <div class="record-category"><CategoryBadge record={classificationRecord} onfilter={oncategoryfilter} /></div>
    <ClassificationSummary record={classificationRecord} />
  </section>
  {#if presentation === 'page' && import.meta.env.VITE_COMMUNITY_PILOT === 'true' && id}
    <p class="contribution-actions">{#each [['evidence','Add evidence'],['correction','Suggest a correction'],['privacy-removal','Privacy or removal']] as [type, label]}<a class="evidence-link" href={`#/contribute/${type}?target=${encodeURIComponent(id)}&map=${encodeURIComponent('#/map?f1a=field')}`}>{tr(label ?? '', $language)}</a>{/each}</p>
  {/if}
  {#if nameWithheld}
    <dl class="identity"><div><dt>{tr('Name', $language)}</dt><dd>{tr('Name not shown, privacy review pending', $language)}</dd></div></dl>
  {/if}
  <section aria-labelledby="location-heading">
    <h2 id="location-heading">{tr('Location', $language)}</h2>
    <dl>
      {#if facilityAddress}<div><dt>{tr('Address', $language)}</dt><dd>{facilityAddress}</dd></div>{/if}
      <div><dt>{tr('Locality', $language)}</dt><dd>{locationText}</dd></div>
      {#if hasCoordinates}<div><dt>{tr('Coordinates', $language)}</dt><dd>{coordinate(record.latitude)}, {coordinate(record.longitude)}</dd></div>{/if}
      <div><dt>{tr('Precision', $language)}</dt><dd>{precisionLabel || tr(precision, $language)}</dd></div>
      {#if record.coordinatePrecision && !['source-provided', 'source_reported', 'source_provided_unverified'].includes(record.coordinatePrecision)}<div><dt>{tr('Source precision', $language)}</dt><dd>{displayGeneratedValue(record.coordinatePrecision)}</dd></div>{/if}
      {#if coordinateStatus && !sameLabel(coordinateStatus, 'source_confirmed')}<div><dt>{tr('Coordinate review', $language)}</dt><dd>{displayGeneratedValue(coordinateStatus)}</dd></div>{/if}
      {#if coordinateMethod}<div><dt>{tr('Location method', $language)}</dt><dd>{displayGeneratedValue(coordinateMethod)}</dd></div>{/if}
      {#if coordinateProvider}<div><dt>{tr('Geocoding provider', $language)}</dt><dd>{coordinateProvider}</dd></div>{/if}
      {#if coordinateConfidence !== null || record.coordinateConfidenceBand}<div><dt>{tr('Geocoding confidence', $language)}</dt><dd>{#if coordinateConfidence !== null}{coordinateConfidence} ({tr('provider score', $language)}){/if}{#if record.coordinateConfidenceBand}{coordinateConfidence !== null ? ' · ' : ''}{displayGeneratedValue(record.coordinateConfidenceBand)}{/if}</dd></div>{/if}
      {#if defaultMapScope === false}<div><dt>{tr('Map scope', $language)}</dt><dd>{tr('Outside the default map', $language)}{#if mapScopeReason} · {displayGeneratedValue(mapScopeReason)}{/if}</dd></div>{/if}
    </dl>
  </section>

  {#if presentation === 'page' && hasCoordinates}<LocationPreview latitude={record.latitude!} longitude={record.longitude!} precision={precision} category={taxonomy?.primaryCategories[0] ?? activity ?? 'unclassified'} />{/if}

  {#if sourceFacts}
    <section aria-labelledby="source-facts-heading">
      <h2 id="source-facts-heading">{tr('Source facts', $language)}</h2>
      <dl>
        {#if speciesSlaughtered}<div><dt>{tr('Species slaughtered', $language)}</dt><dd>{speciesSlaughtered}</dd></div>{/if}
        {#if slaughterRangeText}<div><dt>{tr('Estimated animals slaughtered (last 360 days)', $language)}</dt><dd>{slaughterRangeText}</dd></div>{/if}
        {#if processingRangeText}<div><dt>{tr('Estimated product volume (pounds/month)', $language)}</dt><dd>{processingRangeText}</dd></div>{/if}
        {#if sourceLocationRole === 'aphis_mailing_locality'}<div><dt>{tr('Location role', $language)}</dt><dd>{tr('APHIS mailing locality: approximate locality, not an operating-site location', $language)}</dd></div>{/if}
        {#if sourceFacts.alternateNames?.length}<div><dt>{tr('Also known as', $language)}</dt><dd>{sourceFacts.alternateNames.join(' · ')}</dd></div>{/if}
        {#if sourceFacts.establishmentId}<div><dt>{tr('Establishment ID', $language)}</dt><dd>{sourceFacts.establishmentId}</dd></div>{/if}
        {#if sourceFacts.establishmentNumber}<div><dt>{tr('Establishment number', $language)}</dt><dd>{sourceFacts.establishmentNumber}</dd></div>{/if}
        {#if sourceFacts.grantDate}<div><dt>{tr('Grant date', $language)}</dt><dd>{sourceFacts.grantDate}</dd></div>{/if}
        {#if sourceFacts.aphisAnnualReports?.length}{#each sourceFacts.aphisAnnualReports as report (report.fiscalYear)}<div><dt>{tr('FY ', $language)}{report.fiscalYear} {tr('reported animals', $language)}</dt><dd><ul>{#each report.speciesCounts as species (species.species)}<li>{sourceFactLabel(species.species)}: {annualSpeciesCount(species.count)}</li>{/each}</ul>{#if safeHttps(report.sourceUrl)}<a href={safeHttps(report.sourceUrl) ?? ''} target="_blank" rel="noopener noreferrer">{tr('Source report', $language)}</a>{/if}</dd></div>{/each}{/if}
        {#if sourceFacts.aphisDatedInspections?.length}{#each sourceFacts.aphisDatedInspections as inspection (inspection.inspectionDate)}<div><dt>{tr('APHIS inspection', $language)}</dt><dd>{inspection.inspectionDate}{#if safeHttps(inspection.sourceUrl)} <a href={safeHttps(inspection.sourceUrl) ?? ''} target="_blank" rel="noopener noreferrer">{tr('Source record', $language)}</a>{/if}</dd></div>{/each}{/if}
      </dl>
    </section>
  {/if}

  {#if publicRelease && publicReleaseId && id}
    <RecordConnections facilityId={id} releaseId={publicReleaseId} sourceId={sourceId ?? undefined} sourceFacts={sourceFacts} rail={presentation === 'rail'} />
  {/if}

  <section aria-labelledby="evidence-heading">
      <h2 id="evidence-heading">{tr('Source and review', $language)}</h2>
    <dl>
      {#if sourceName}<div><dt>{tr('Source', $language)}</dt><dd>{#if onsourcefilter && sourceId}<button class="filter-fact" type="button" onclick={() => onsourcefilter?.(sourceId)}>{sourceName}</button>{#if sourceUrl} <a class="source-reference" href={sourceUrl} target="_blank" rel="noopener noreferrer" aria-label={`${sourceName} (${tr('opens in a new tab', $language)})`}>↗</a>{/if}{:else if sourceUrl}<a href={sourceUrl} target="_blank" rel="noopener noreferrer">{sourceName}<span class="sr-only"> ({tr('opens in a new tab', $language)})</span></a>{:else}{sourceName}{/if}</dd></div>
      {:else if sourceId}<div><dt>{tr('Source ID', $language)}</dt><dd>{sourceId}</dd></div>{/if}
      {#if sourceRecordId}<div><dt>{tr('Source record', $language)}</dt><dd>{sourceRecordId}</dd></div>{/if}
      {#if sourceRecordUrl}<div><dt>{tr('Source record link', $language)}</dt><dd><a href={sourceRecordUrl} target="_blank" rel="noopener noreferrer">{tr('Open source record', $language)}<span class="sr-only"> ({tr('opens in a new tab', $language)})</span></a></dd></div>{/if}
      {#if observed}<div><dt>{tr('Observed', $language)}</dt><dd><time datetime={observed}>{observed}</time></dd></div>{/if}
      {#if retrieved}<div><dt>{tr('Retrieved', $language)}</dt><dd><time datetime={retrieved}>{retrieved}</time></dd></div>{/if}
      {#if publicationStatus}<div><dt>{tr('Publication', $language)}</dt><dd>{displayGeneratedValue(publicationStatus)}</dd></div>{/if}
    </dl>
    {#if evidence}<p class="evidence">{evidence}</p>{/if}
  </section>

  <footer>
    {#if presentation !== 'page'}<span class="record-id">Record ID · {id || 'Unavailable'}</span>{/if}
  </footer>
</article>

<style>
  .contribution-actions{display:flex;flex-wrap:wrap;gap:.5rem 1rem}
  .detail {
    --ink: #f1efe8;
    --muted: #aab0aa;
    --line: #414843;
    box-sizing: border-box;
    min-width: 0;
    /* The host rail owns scrolling so the detail panel does not create a nested scroll region. */
    overflow: visible;
    padding: 0.8rem;
    color: var(--ink);
    background: #171a18;
    font: 0.76rem/1.42 system-ui, -apple-system, "Segoe UI", sans-serif;
  }

  .detail * {
    box-sizing: border-box;
  }

  .detail h1 {
    margin: 0.25rem 2rem 0.3rem 0;
    font: 500 1.3rem/1.2 Georgia, serif;
  }

  .share {
    display: inline-grid;
    place-items: center;
    width: 1.75rem;
    min-height: 1.75rem;
    margin-left: .2rem;
    padding: .25rem;
    vertical-align: middle;
  }

  .share svg { width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }

  .record-category { margin: .3rem 0 .25rem; }

  .identity {
    margin: 0.55rem 0 0.7rem;
  }

  .classification-overview, .detail:not(.page) .classification-overview { margin-top: 0; }

  section {
    margin-top: .8rem;
  }

  h2 {
    margin: 0;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--line);
    font: 600 0.9rem/1.3 system-ui, sans-serif;
  }

  dl {
    margin: 0.2rem 0;
  }

  dl div {
    display: grid;
    grid-template-columns: minmax(7rem, 34%) 1fr;
    gap: 0.7rem;
    padding: 0.38rem 0;
    border-bottom: 1px solid #303632;
  }

  dt {
    color: var(--muted);
    font-size: 0.72rem;
  }

  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }

  a {
    color: #ddd4bb;
    text-underline-offset: 2px;
  }

  .evidence,
  section > p {
    color: #c2c8c1;
    font-size: 0.75rem;
  }

  footer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    margin-top: 1.1rem;
    padding-top: 0.8rem;
    border-top: 1px solid var(--line);
  }

  .record-id {
    overflow-wrap: anywhere;
    color: var(--muted);
    font: 0.65rem ui-monospace, monospace;
  }

  button {
    min-height: 2.1rem;
    padding: 0.45rem 0.7rem;
    border: 1px solid #69716a;
    color: var(--ink);
    background: #202421;
    font: inherit;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .close {
    float: right;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  .page {
    min-height: 100%;
    max-width: 58rem;
    margin: auto;
    padding: clamp(1.2rem, 5vw, 3rem);
  }

  .page h1 {
    font-size: clamp(1.8rem, 4vw, 2.5rem);
  }

  .detail:not(.page) {
    --ink: var(--ui-ink);
    --muted: var(--ui-muted);
    --line: var(--ui-line);
    padding: 1.1rem 1.25rem;
    background: var(--ui-raised);
    font: .8125rem/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  }

  .detail:not(.page) h1 {
    margin: 0 0 .85rem;
    font: 500 1.5rem/1.15 system-ui, -apple-system, "Segoe UI", sans-serif;
    letter-spacing: -.035em;
    overflow-wrap: anywhere;
  }

  .detail:not(.page) .open-facility { display: flex; align-items: center; justify-content: space-between; gap: .75rem; width: 100%; min-height: 2.75rem; margin: 0 0 .95rem; padding: .55rem .8rem; border: 1px solid var(--line); color: var(--ink); background: transparent; font-size: .8125rem; font-weight: 500; text-decoration: none; }
  .detail:not(.page) .open-facility:hover { background: var(--ui-hover); }
  .open-facility svg { width: 1rem; height: 1rem; flex: none; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }

  .detail:not(.page) .share {
    width: 2.25rem;
    min-height: 2.25rem;
    margin-left: .25rem;
    border: 0;
    color: var(--muted);
    background: transparent;
  }

  .detail:not(.page) section { margin-top: .95rem; }
  .detail:not(.page) h2 {
    margin: 0 0 .4rem;
    padding: 0;
    border: 0;
    font: 500 .875rem/1.4 system-ui, sans-serif;
    letter-spacing: -.015em;
  }
  .detail:not(.page) dl { margin: 0; }
  .detail:not(.page) dl div {
    grid-template-columns: minmax(5rem, 30%) minmax(0, 1fr);
    gap: .6rem;
    padding: .22rem 0;
    border: 0;
  }
  .detail:not(.page) dt { color: var(--muted); font-size: .75rem; }
  .detail:not(.page) dd { line-height: 1.55; }
  .detail:not(.page) dd ul { margin: 0; padding-left: 1.1rem; }
  .detail:not(.page) a { color: var(--ink); text-underline-offset: .25rem; }
  .detail:not(.page) section > p, .detail:not(.page) .evidence { color: var(--muted); font-size: .8125rem; }
  .detail:not(.page) footer { margin-top: 1rem; padding-top: .7rem; }
  .detail:not(.page) .record-id { font: .6875rem/1.5 system-ui, sans-serif; }
  .detail:not(.page) button { border-color: var(--line); color: var(--ink); background: var(--ui-raised); }
  .detail:not(.page) button:hover { background: var(--ui-hover); }
  .detail:not(.page) button:focus-visible, .detail:not(.page) a:focus-visible { outline: 2px solid var(--ink); outline-offset: 3px; }
  .detail:not(.page) .filter-fact { min-height: 1.75rem; padding: 0; border: 0; background: transparent; text-align: left; font: inherit; }
  .detail:not(.page) .filter-fact:hover { text-decoration: underline; text-underline-offset: .25rem; }
  .detail:not(.page) .source-reference { display: inline-grid; place-items: center; min-width: 1.75rem; min-height: 1.75rem; text-decoration: none; }
  @media (pointer: coarse) { .detail:not(.page) .filter-fact, .detail:not(.page) .source-reference { min-height: 2.75rem; } .detail:not(.page) .source-reference { min-width: 2.75rem; } }

  @media (max-width: 40rem) {
    .detail {
      border-top: 1px solid var(--line);
      padding: 1rem;
    }

    .page {
      min-height: 100dvh;
    }

    .page footer { background: #171a18; }
    .detail:not(.page) { border: 0; padding: 1rem; }
    .detail:not(.page) .share { width: 2.75rem; min-height: 2.75rem; }
  }
</style>
