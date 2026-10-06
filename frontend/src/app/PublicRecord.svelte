<script lang="ts">
  import { LocalLocationRepository, type LocalProfile } from '../api/LocalLocationRepository';
  import type { Location } from '../domain/location';
  import CopyValue from './CopyValue.svelte';
  import { serializeRoute } from './routeState';
  import { precisionPresentation } from '../features/locations/precisionPresentation';
  let { id, profile = 'official', releaseId }: { id: string; profile?: LocalProfile; releaseId?: string | undefined } = $props();
  const repository = new LocalLocationRepository();
  let record = $state<Location | null>(null);
  let currentRelease = $state('');
  let busy = $state(true);
  let error = $state('');
  let retry = $state(0);
  $effect(() => {
    void retry;
    const controller = new AbortController(); record = null; busy = true; error = '';
    void repository.detail(id, profile, controller.signal, releaseId).then(result => { if (!controller.signal.aborted) { record = result.location; currentRelease = result.releaseId; } }).catch(cause => { if (!controller.signal.aborted) error = cause && typeof cause === 'object' && 'kind' in cause && cause.kind === 'restricted' ? 'This record is unavailable in the selected public release.' : 'This record could not be loaded. Try again.'; }).finally(() => { if (!controller.signal.aborted) busy = false; });
    return () => controller.abort();
  });
  const human = (value: string | false | undefined) => value === undefined ? 'Unknown' : String(value).replaceAll('_',' ').replaceAll('-',' ');
  const precision = $derived(precisionPresentation(record?.evidence?.displayPrecision));
  const recordLink = $derived(`${window.location.origin}${window.location.pathname}${serializeRoute({kind:'record',facilityId:id,profile,...(currentRelease ? {releaseId:currentRelease} : {})})}`);
</script>
<svelte:head><title>{record?.name ?? 'Record'} · Until Every Cage</title></svelte:head>
<section class="public-record" aria-label="Public record">
  {#if profile === 'community'}<p class="warning"><strong>Unreviewed community claim — not verified by Until Every Cage.</strong> Privacy screening is not factual review or project approval. Community counts are separate.</p>{/if}
  {#if busy}<p role="status">Loading record…</p>{:else if error}<h1>Record unavailable</h1><p role="alert">{error}</p><button type="button" onclick={() => retry += 1}>Retry</button><p><a href="#/database">Browse records</a></p>{:else if record}<h1>{record.name}</h1><p>{record.region} · {precision}</p>
    <dl><div><dt>Activity</dt><dd>{record.taxonomy?.leafActivities.map(activity => activity.label).join(' · ') || record.category}</dd></div><div><dt>Source</dt><dd>{record.source} {#if record.evidence?.sourceUrl}<a href={record.evidence.sourceUrl} target="_blank" rel="noreferrer">Open source</a>{/if}</dd></div><div><dt>Source origin</dt><dd>{record.evidence?.sourceType === 'user_submitted' ? 'Community-submitted' : record.evidence?.sourceType === 'secondary' ? 'Secondary source' : 'Government-sourced'}</dd></div><div><dt>Observed</dt><dd>{record.observed}</dd></div><div><dt>Retrieved</dt><dd>{record.evidence?.retrievedAt ?? 'Unknown'}</dd></div><div><dt>Factual review</dt><dd>{human(record.evidence?.factualReviewStatus)}{#if record.evidence?.reviewerRole} · {human(record.evidence.reviewerRole)}{/if}</dd></div><div><dt>Privacy screening</dt><dd>{human(record.evidence?.privacyScreeningStatus)}</dd></div><div><dt>Project approval</dt><dd>{human(record.evidence?.projectApproval)}</dd></div><div><dt>Publication</dt><dd>{profile === 'official' ? 'Curated records' : profile === 'community' ? 'Community submissions' : 'Secondary sources'} · release {currentRelease}</dd></div><div><dt>Lifecycle</dt><dd>{human(record.evidence?.lifecycleStatus)}</dd></div></dl>
    <p class="limitation">A source record does not establish current operation or an exact operating address. Source-reported precision is not independently verified; approximate and city-level locations are not exact facility points.</p>
    <p class="record-id">Record ID: <code>{record.id}</code></p><CopyValue value={record.id} label="Record ID" buttonLabel="Copy record ID" /><CopyValue value={recordLink} label="Record link" buttonLabel="Copy record link" />
    <nav aria-label="Record contribution actions">{#each [['evidence','Add evidence'],['correction','Suggest a correction'],['privacy-removal','Privacy or removal']] as [type,label]}<a href={`#/contribute/${type}?target=${encodeURIComponent(record.id)}`}>{label}</a>{/each}</nav>
  {/if}
</section>
<style>
  .public-record{width:min(100% - 3rem,46rem);margin:auto;padding:1.5rem 0 2rem;color:#edf0e9;font:.9rem/1.5 system-ui,sans-serif}h1{margin:0 0 .75rem;font:500 2rem/1.2 Georgia,serif;overflow-wrap:anywhere}p{color:#c6d0c5}dl{margin:1.25rem 0}dl div{display:grid;grid-template-columns:9rem minmax(0,1fr);gap:1rem;padding:.55rem 0;border-bottom:1px solid #3c4640}dt{font-weight:600}dd{margin:0;overflow-wrap:anywhere;color:#c6d0c5}.record-id{overflow-wrap:anywhere}.limitation{font-size:.85rem}nav{display:flex;flex-wrap:wrap;gap:.6rem 1rem;margin-top:1.25rem}a{color:#dce8d9;text-underline-offset:.2em}.public-record :global(.copy-value){margin-top:.7rem}button{min-height:2.25rem;padding:.4rem .6rem;background:#252f28;border:1px solid #657466;color:#edf0e9;font:inherit}.warning{padding:.75rem;border-left:3px solid #cf9a66;background:#282723;color:#eee4ce}a:focus-visible,button:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:40rem){.public-record{width:calc(100% - 2rem)}h1{font-size:1.65rem}dl div{grid-template-columns:1fr;gap:.15rem}}
</style>
