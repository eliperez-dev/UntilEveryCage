<script lang="ts">
  import { LocalLocationRepository, type LocalProfile } from '../api/LocalLocationRepository';
  import type { DerivedSourceVolumeRange, Location, SourceVolumeCategory } from '../domain/location';
  import CopyValue from './CopyValue.svelte';
  import { serializeRoute } from './routeState';
  import { precisionPresentation } from '../features/locations/precisionPresentation';
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
  const human = (value: string | false | null | undefined) => value === undefined || value === null ? null : String(value).replaceAll('_',' ').replaceAll('-',' ');
  const precision = $derived(precisionPresentation(record?.evidence?.displayPrecision));
  const detailActivity = (location: Location) => location.taxonomy?.leafActivities.map(activity => activity.label).join(' · ') || (location.category === 'unclassified' ? 'Category not provided' : location.category);
  const humanLabel = (value: string) => value.replaceAll(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/^./, letter => letter.toLocaleUpperCase());
  const sourceFlag = (value: string | boolean) => value === true ? 'Yes' : typeof value === 'string' ? humanLabel(value) : null;
  const sourceFlagLabel = (key: string) => humanLabel(key);
  const affirmativeEntries = (flags: Readonly<Record<string, string | boolean>> | undefined) => flags ? Object.entries(flags).filter(([, value]) => value !== false).sort(([left], [right]) => left.localeCompare(right)) : [];
  const volumeProvenance = (value: SourceVolumeCategory['provenance']) => {
    if (!value) return null;
    if (typeof value === 'string') return value;
    return [value.sourceField, value.method].filter(Boolean).join(' · ') || null;
  };
  const volumeCategoryKey = (volume: SourceVolumeCategory, index: number) => `${volume.code}:${typeof volume.provenance === 'string' ? volume.provenance : volume.provenance?.sourceField ?? ''}:${index}`;
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
</script>
<svelte:head><title>{record?.name ?? 'Record'} · Until Every Cage</title></svelte:head>
<section class="public-record" aria-label="Public record">
  {#if profile === 'community'}<p class="warning"><strong>Unreviewed community claim — not verified by Until Every Cage.</strong> Privacy screening is not factual review or project approval. Community counts are separate.</p>{/if}
  {#if busy}<p role="status">Loading record…</p>{:else if error}<h1>Record unavailable</h1><p role="alert">{error}</p><button type="button" onclick={() => retry += 1}>Retry</button><p><a href="#/database">Browse records</a></p>{:else if record}<h1>{record.name}</h1><p>{record.region} · {precision}{#if record.evidence?.geometryProvenance?.method} · {record.evidence.geometryProvenance.method.replaceAll(/[_-]+/g, ' ')}{/if}</p>
    <dl><div><dt>Activity</dt><dd>{detailActivity(record)}</dd></div><div><dt>Source</dt><dd>{record.source} {#if record.evidence?.sourceUrl}<a href={record.evidence.sourceUrl} target="_blank" rel="noreferrer">Open source</a>{/if}</dd></div><div><dt>Source origin</dt><dd>{record.evidence?.sourceType === 'user_submitted' ? 'Community-submitted' : record.evidence?.sourceType === 'secondary' ? 'Secondary source' : 'Government-sourced'}</dd></div>{#if record.observed !== 'unknown'}<div><dt>Observed</dt><dd>{record.observed}</dd></div>{/if}{#if record.evidence?.retrievedAt}<div><dt>Retrieved</dt><dd>{record.evidence.retrievedAt}</dd></div>{/if}{#if human(record.evidence?.factualReviewStatus)}<div><dt>Factual review</dt><dd>{human(record.evidence?.factualReviewStatus)}{#if record.evidence?.reviewerRole} · {human(record.evidence.reviewerRole)}{/if}</dd></div>{/if}{#if human(record.evidence?.privacyScreeningStatus)}<div><dt>Privacy screening</dt><dd>{human(record.evidence?.privacyScreeningStatus)}</dd></div>{/if}{#if human(record.evidence?.projectApproval)}<div><dt>Project approval</dt><dd>{human(record.evidence?.projectApproval)}</dd></div>{/if}<div><dt>Publication</dt><dd>{profile === 'official' ? 'Curated records' : profile === 'community' ? 'Community submissions' : 'Secondary sources'} · release {currentRelease}</dd></div>{#if human(record.evidence?.lifecycleStatus)}<div><dt>Lifecycle</dt><dd>{human(record.evidence?.lifecycleStatus)}</dd></div>{/if}</dl>
    {#if record.sourceFacts}<section class="source-facts" aria-labelledby="source-facts-heading"><h2 id="source-facts-heading">Source facts</h2><dl>{#if record.sourceFacts.alternateNames?.length}<div><dt>Also known as</dt><dd>{record.sourceFacts.alternateNames.join(' · ')}</dd></div>{/if}{#if record.sourceFacts.establishmentId}<div><dt>Establishment ID</dt><dd>{record.sourceFacts.establishmentId}</dd></div>{/if}{#if record.sourceFacts.establishmentNumber}<div><dt>Establishment number</dt><dd>{record.sourceFacts.establishmentNumber}</dd></div>{/if}{#if record.sourceFacts.grantDate}<div><dt>Grant date</dt><dd>{record.sourceFacts.grantDate}</dd></div>{/if}{#if record.sourceFacts.nativeActivityLabel || record.sourceFacts.nativeActivityCode}<div><dt>Source activity</dt><dd>{record.sourceFacts.nativeActivityLabel}{#if record.sourceFacts.nativeActivityLabel && record.sourceFacts.nativeActivityCode} · {/if}{record.sourceFacts.nativeActivityCode}</dd></div>{/if}{#if affirmativeEntries(record.sourceFacts.speciesSlaughtered).length}<div><dt>Species slaughtered</dt><dd><ul>{#each affirmativeEntries(record.sourceFacts.speciesSlaughtered) as [key, value] (key)}<li>{sourceFlagLabel(key)}{#if sourceFlag(value)}: {sourceFlag(value)}{/if}</li>{/each}</ul></dd></div>{/if}{#if affirmativeEntries(record.sourceFacts.processingActivities).length}<div><dt>Processing activities</dt><dd><ul>{#each affirmativeEntries(record.sourceFacts.processingActivities) as [key, value] (key)}<li>{sourceFlagLabel(key)}{#if sourceFlag(value)}: {sourceFlag(value)}{/if}</li>{/each}</ul></dd></div>{/if}{#if slaughterRanges(record.sourceFacts.derivedSourceVolumeRanges).length}<div><dt>Estimated animals slaughtered (last 360 days)</dt><dd><ul>{#each slaughterRanges(record.sourceFacts.derivedSourceVolumeRanges) as range, index (`${range.ordinalCode}:${range.unit}:${range.period}:${index}`)}{#if formattedRange(range)}<li>{formattedRange(range)} head</li>{/if}{/each}</ul></dd></div>{/if}{#if processingRanges(record.sourceFacts.derivedSourceVolumeRanges).length}<div><dt>Estimated product volume (pounds/month)</dt><dd><ul>{#each processingRanges(record.sourceFacts.derivedSourceVolumeRanges) as range, index (`${range.ordinalCode}:${range.unit}:${range.period}:${index}`)}{#if formattedRange(range)}<li>{formattedRange(range)} pounds/month</li>{/if}{/each}</ul></dd></div>{/if}{#if record.sourceFacts.aphisAnnualReports?.length}{#each record.sourceFacts.aphisAnnualReports as report (report.fiscalYear)}<div><dt>FY{report.fiscalYear} reported animals</dt><dd><ul>{#each report.speciesCounts as species (species.species)}<li>{sourceFlagLabel(species.species)}: {annualSpeciesCount(species.count)}</li>{/each}</ul><a href={report.sourceUrl} target="_blank" rel="noopener noreferrer">Source report</a></dd></div>{/each}{/if}{#if record.sourceFacts.sourceVolumeCategories?.length}<div><dt>Source volume categories</dt><dd><ul>{#each record.sourceFacts.sourceVolumeCategories as volume, index (volumeCategoryKey(volume, index))}<li>{volume.code}{#if volumeProvenance(volume.provenance)} · {volumeProvenance(volume.provenance)}{/if}</li>{/each}</ul></dd></div>{/if}</dl></section>{/if}
    <p class="record-id">Record ID: <code>{record.id}</code></p><CopyValue value={record.id} label="Record ID" buttonLabel="Copy record ID" /><CopyValue value={recordLink} label="Record link" buttonLabel="Copy record link" />
    <nav aria-label="Record contribution actions">{#each [['evidence','Add evidence'],['correction','Suggest a correction'],['privacy-removal','Privacy or removal']] as [type,label]}<a href={`#/contribute/${type}?target=${encodeURIComponent(record.id)}`}>{label}</a>{/each}</nav>
  {/if}
</section>
<style>
  .public-record{width:min(100% - 3rem,46rem);margin:auto;padding:1.5rem 0 2rem;color:#edf0e9;font:.9rem/1.5 system-ui,sans-serif}h1{margin:0 0 .75rem;font:500 2rem/1.2 Georgia,serif;overflow-wrap:anywhere}h2{margin:1.5rem 0 0;font:600 1.05rem/1.3 Georgia,serif}p{color:#c6d0c5}dl{margin:1.25rem 0}.source-facts dl{margin:.4rem 0}dl div{display:grid;grid-template-columns:9rem minmax(0,1fr);gap:1rem;padding:.55rem 0;border-bottom:1px solid #3c4640}dt{font-weight:600}dd{margin:0;overflow-wrap:anywhere;color:#c6d0c5}ul{margin:0;padding-left:1.1rem}.record-id{overflow-wrap:anywhere}nav{display:flex;flex-wrap:wrap;gap:.6rem 1rem;margin-top:1.25rem}a{color:#dce8d9;text-underline-offset:.2em}.public-record :global(.copy-value){margin-top:.7rem}button{min-height:2.25rem;padding:.4rem .6rem;background:#252f28;border:1px solid #657466;color:#edf0e9;font:inherit}.warning{padding:.75rem;border-left:3px solid #cf9a66;background:#282723;color:#eee4ce}a:focus-visible,button:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:40rem){.public-record{width:calc(100% - 2rem)}h1{font-size:1.65rem}dl div{grid-template-columns:1fr;gap:.15rem}}
</style>
