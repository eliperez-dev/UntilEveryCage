<script lang="ts">
  import RecordConnections from './RecordConnections.svelte';
  import LocationPreview from './LocationPreview.svelte';
  import { serializeRoute } from './routeState';
  import type { LabRecord } from '../design-lab/contract';
  import { categoryPresentation } from '../features/locations/categoryPresentation';
  import { sourceClassificationLabels } from '../features/locations/sourceClassification';
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
    onclose,
  }: {
    record: LabRecord | RecordDetailRecord;
    presentation?: 'rail' | 'page';
    publicRelease?: boolean;
    publicReleaseId?: string | null;
    onclose?: () => void;
  } = $props();
  let copyFeedback = $state('');


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
  const taxonomyPrimaryLabels = $derived((taxonomy?.primaryCategories ?? ['unclassified']).map(key => categoryPresentation(key).label));
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
  const activityDisplay = $derived(taxonomy ? taxonomyPrimaryLabels.join(', ') : humanizeValue(activity));
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
      ? 'Source-provided coordinates'
      : precisionLabelFor(record.coordinatePrecision?.includes('provider_address') ? record.coordinatePrecision : precision),
  );
  const sourceFacts = $derived('sourceFacts' in record ? record.sourceFacts : undefined);
  const nativeActivity = $derived(
    sourceFacts ? humanizeValue(sourceFacts.nativeActivityLabel ?? sourceFacts.nativeActivityCode ?? null) : null,
  );
  const speciesSlaughtered = $derived(compactSourceFacts(sourceFacts, 'speciesSlaughtered'));
  const processingActivities = $derived(compactSourceFacts(sourceFacts, 'processingActivities'));
  const detailedActivityLabels = $derived(uniqueLabels([
    ...(taxonomy?.leafActivities.map(leaf => humanizeValue(leaf.label)) ?? []),
    ...sourceFactLabels(sourceFacts, 'processingActivities'),
  ]));
  const detailedActivities = $derived(detailedActivityLabels.filter(label => !isSummaryActivity(label)).join(', '));
  const sourceClassification = $derived(sourceClassificationLabels(
    [sourceFacts?.nativeActivityLabel, sourceFacts?.nativeActivityCode, activitySource],
    taxonomy?.assignments ?? [],
    [...detailedActivityLabels, ...taxonomyPrimaryLabels, ...(activity ? [activity] : [])],
  ));

  function humanizeValue(raw: string | null): string | null {
    if (!raw) return null;

    // These are display labels only; keep the repository's canonical enum untouched.
    const words = raw.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/\b(nrte|rte)\b/gi, acronym => acronym.toUpperCase());
    return words ? words[0]!.toLocaleUpperCase() + words.slice(1) : null;
  }
  function sourceFactLabel(raw: string): string {
    return humanizeValue(raw) ?? raw;
  }
  function sameLabel(left: string, right: string): boolean {
    return humanizeValue(left)?.toLocaleLowerCase() === humanizeValue(right)?.toLocaleLowerCase();
  }
  function isSummaryActivity(label: string): boolean {
    return taxonomyPrimaryLabels.some(primary => sameLabel(primary, label)) ||
      Boolean(taxonomy?.primaryCategories.includes('processing_and_preparation') && sameLabel(label, 'processing') && detailedActivityLabels.some(other => !sameLabel(other, 'processing')));
  }
  function coordinate(value: number | null | undefined): string {
    return typeof value === 'number' ? String(Number(value.toFixed(6))) : '';
  }
  function uniqueLabels(labels: Array<string | null>): string[] {
    return labels.filter((label): label is string => Boolean(label)).filter((label, index, all) => all.findIndex(other => sameLabel(label, other)) === index);
  }
  function sourceFactLabels(facts: LocationSourceFacts | undefined, field: 'speciesSlaughtered' | 'processingActivities'): string[] {
    const entries = facts?.[field]
      ? Object.entries(facts[field]!).filter(([, included]) => included !== false).sort(([left], [right]) => left.localeCompare(right))
      : [];
    return entries.map(([name, included]) => {
      const label = sourceFactLabel(name);
      if (typeof included !== 'string' || !included.trim() || /^(?:yes|true|1)$/i.test(included.trim())) return label;
      return `${label}: ${humanizeValue(included) ?? included}`;
    });
  }
  function compactSourceFacts(facts: LocationSourceFacts | undefined, field: 'speciesSlaughtered' | 'processingActivities'): string | null {
    return sourceFactLabels(facts, field).join(', ') || null;
  }
  function formattedRange(range: DerivedSourceVolumeRange): string | null {
    const number = (value: number) => new Intl.NumberFormat('en-US').format(value);
    if (range.bounds === 'exclusive_upper' && range.upper !== null) return `Less than ${number(range.upper)}`;
    if (range.bounds === 'inclusive_lower_unbounded' && range.lower !== null) return `${number(range.lower)} or more`;
    if (range.bounds === 'inclusive_lower_exclusive_upper' && range.lower !== null && range.upper !== null) return `${number(range.lower)} to less than ${number(range.upper)}`;
    return null;
  }
  function annualSpeciesCount(count: number): string { return new Intl.NumberFormat('en-US').format(count); }
  const slaughterRanges = $derived(sourceFacts?.derivedSourceVolumeRanges?.filter(range => range.unit === 'head' && range.period === 'trailing_360_days') ?? []);
  const processingRanges = $derived(sourceFacts?.derivedSourceVolumeRanges?.filter(range => range.unit === 'pounds' && range.period === 'month') ?? []);
  const slaughterRangeText = $derived(slaughterRanges.map(formattedRange).filter((range): range is string => Boolean(range)).map(range => `${range} animals`).join(', '));
  const processingRangeText = $derived(processingRanges.map(formattedRange).filter((range): range is string => Boolean(range)).map(range => `${range} pounds/month`).join(', '));

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
  async function copyFacilityLink() { try { await navigator.clipboard.writeText(facilityLink); copyFeedback = 'Facility link copied.'; } catch { copyFeedback = 'Could not copy facility link.'; } }
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
      aria-label="Close record detail"
      onclick={onclose}
    >Close</button>
  {/if}
  <h1 id="record-title">{name}{#if presentation === 'page'} <button class="share" type="button" aria-label="Copy facility link" title="Copy facility link" onclick={copyFacilityLink}><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.1 0l3-3A5 5 0 0 0 13 2.9l-1.7 1.7m2.7 6.4a5 5 0 0 0-7.1 0l-3 3A5 5 0 0 0 11 21.1l1.7-1.7"/></svg></button><span class="sr-only" role="status" aria-live="polite">{copyFeedback}</span>{/if}</h1>
  {#if presentation === 'page' && import.meta.env.VITE_COMMUNITY_PILOT === 'true' && id}
    <p class="contribution-actions">{#each [['evidence','Add evidence'],['correction','Suggest a correction'],['privacy-removal','Privacy or removal']] as [type, label]}<a class="evidence-link" href={`#/contribute/${type}?target=${encodeURIComponent(id)}&map=${encodeURIComponent('#/map?f1a=field')}`}>{label}</a>{/each}</p>
  {/if}
  {#if nameWithheld}
    <dl class="identity"><div><dt>Name</dt><dd>Name not shown, privacy review pending</dd></div></dl>
  {/if}
  <section aria-labelledby="location-heading">
    <h2 id="location-heading">Location</h2>
    <dl>
      {#if facilityAddress}<div><dt>Address</dt><dd>{facilityAddress}</dd></div>{/if}
      <div><dt>Locality</dt><dd>{locationText}</dd></div>
      {#if hasCoordinates}<div><dt>Coordinates</dt><dd>{coordinate(record.latitude)}, {coordinate(record.longitude)}</dd></div>{/if}
      <div><dt>Precision</dt><dd>{precisionLabel}</dd></div>
      {#if record.coordinatePrecision && !['source-provided', 'source_reported', 'source_provided_unverified'].includes(record.coordinatePrecision)}<div><dt>Source precision</dt><dd>{humanizeValue(record.coordinatePrecision)}</dd></div>{/if}
      {#if coordinateStatus && !sameLabel(coordinateStatus, 'source_confirmed')}<div><dt>Coordinate review</dt><dd>{humanizeValue(coordinateStatus)}</dd></div>{/if}
      {#if coordinateMethod}<div><dt>Location method</dt><dd>{humanizeValue(coordinateMethod)}</dd></div>{/if}
      {#if coordinateProvider}<div><dt>Geocoding provider</dt><dd>{coordinateProvider}</dd></div>{/if}
      {#if coordinateConfidence !== null || record.coordinateConfidenceBand}<div><dt>Geocoding confidence</dt><dd>{#if coordinateConfidence !== null}{coordinateConfidence} (provider score){/if}{#if record.coordinateConfidenceBand}{coordinateConfidence !== null ? ' · ' : ''}{humanizeValue(record.coordinateConfidenceBand)}{/if}</dd></div>{/if}
      {#if defaultMapScope === false}<div><dt>Map scope</dt><dd>Outside the default map{#if mapScopeReason} · {humanizeValue(mapScopeReason)}{/if}</dd></div>{/if}
    </dl>
  </section>

  {#if presentation === 'page' && hasCoordinates}<LocationPreview latitude={record.latitude!} longitude={record.longitude!} precision={precision} category={taxonomy?.primaryCategories[0] ?? activity ?? 'unclassified'} />{/if}

  {#if activityDisplay || taxonomy}
    <section class="taxonomy" aria-labelledby="taxonomy-heading">
      <h2 id="taxonomy-heading">Activities and classification</h2>
      {#if activityDisplay}<p class="activity">{activityDisplay}</p>{/if}
      {#if detailedActivities}
        <p aria-label="Detailed activities">{detailedActivities}</p>
      {/if}
      {#if sourceClassification.length}<p class="classification">{sourceClassification.join(' · ')}</p>{/if}
    </section>
  {/if}

  {#if sourceFacts}
    <section aria-labelledby="source-facts-heading">
      <h2 id="source-facts-heading">Source facts</h2>
      <dl>
        {#if nativeActivity && !taxonomy}<div><dt>Native activity</dt><dd>{nativeActivity}</dd></div>{/if}
        {#if speciesSlaughtered}<div><dt>Species slaughtered</dt><dd>{speciesSlaughtered}</dd></div>{/if}
        {#if processingActivities && !taxonomy}<div><dt>Processing activities</dt><dd>{processingActivities}</dd></div>{/if}
        {#if slaughterRangeText}<div><dt>Estimated animals slaughtered (last 360 days)</dt><dd>{slaughterRangeText}</dd></div>{/if}
        {#if processingRangeText}<div><dt>Estimated product volume (pounds/month)</dt><dd>{processingRangeText}</dd></div>{/if}
        {#if sourceLocationRole === 'aphis_mailing_locality'}<div><dt>Location role</dt><dd>APHIS mailing locality: approximate locality, not an operating-site location</dd></div>{/if}
        {#if sourceFacts.alternateNames?.length}<div><dt>Also known as</dt><dd>{sourceFacts.alternateNames.join(' · ')}</dd></div>{/if}
        {#if sourceFacts.establishmentId}<div><dt>Establishment ID</dt><dd>{sourceFacts.establishmentId}</dd></div>{/if}
        {#if sourceFacts.establishmentNumber}<div><dt>Establishment number</dt><dd>{sourceFacts.establishmentNumber}</dd></div>{/if}
        {#if sourceFacts.grantDate}<div><dt>Grant date</dt><dd>{sourceFacts.grantDate}</dd></div>{/if}
        {#if sourceFacts.aphisAnnualReports?.length}{#each sourceFacts.aphisAnnualReports as report (report.fiscalYear)}<div><dt>FY{report.fiscalYear} reported animals</dt><dd><ul>{#each report.speciesCounts as species (species.species)}<li>{sourceFactLabel(species.species)}: {annualSpeciesCount(species.count)}</li>{/each}</ul>{#if safeHttps(report.sourceUrl)}<a href={safeHttps(report.sourceUrl) ?? ''} target="_blank" rel="noopener noreferrer">Source report</a>{/if}</dd></div>{/each}{/if}
        {#if sourceFacts.aphisDatedInspections?.length}{#each sourceFacts.aphisDatedInspections as inspection (inspection.inspectionDate)}<div><dt>APHIS inspection</dt><dd>{inspection.inspectionDate}{#if safeHttps(inspection.sourceUrl)} <a href={safeHttps(inspection.sourceUrl) ?? ''} target="_blank" rel="noopener noreferrer">Source record</a>{/if}</dd></div>{/each}{/if}
      </dl>
    </section>
  {/if}

  {#if publicRelease && publicReleaseId && id}
    <RecordConnections facilityId={id} releaseId={publicReleaseId} sourceId={sourceId ?? undefined} sourceFacts={sourceFacts} />
  {/if}

  <section aria-labelledby="evidence-heading">
    <h2 id="evidence-heading">Source and review</h2>
    <dl>
      {#if sourceName}<div><dt>Source</dt><dd>{#if sourceUrl}<a href={sourceUrl} target="_blank" rel="noopener noreferrer">{sourceName}<span class="sr-only"> (opens in a new tab)</span></a>{:else}{sourceName}{/if}</dd></div>
      {:else if sourceId}<div><dt>Source ID</dt><dd>{sourceId}</dd></div>{/if}
      {#if sourceRecordId}<div><dt>Source record</dt><dd>{sourceRecordId}</dd></div>{/if}
      {#if sourceRecordUrl}<div><dt>Source record link</dt><dd><a href={sourceRecordUrl} target="_blank" rel="noopener noreferrer">Open source record<span class="sr-only"> (opens in a new tab)</span></a></dd></div>{/if}
      {#if observed}<div><dt>Observed</dt><dd><time datetime={observed}>{observed}</time></dd></div>{/if}
      {#if retrieved}<div><dt>Retrieved</dt><dd><time datetime={retrieved}>{retrieved}</time></dd></div>{/if}
      {#if publicationStatus}<div><dt>Publication</dt><dd>{humanizeValue(publicationStatus)}</dd></div>{/if}
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

  .activity {
    margin: 0.25rem 0;
    color: #d5d9d3;
  }

  .identity {
    margin: 0.55rem 0 0.7rem;
  }

  .taxonomy { margin-top: .8rem; }

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

  @media (max-width: 40rem) {
    .detail {
      border-top: 1px solid var(--line);
      padding: 1rem;
    }

    .page {
      min-height: 100dvh;
    }

    .page footer { background: #171a18; }
  }
</style>
