<script lang="ts">
  import { PublicReleaseRepository } from '../api/PublicReleaseRepository';
  import type { LocalProfile } from '../api/LocalLocationRepository';
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  const href = (path: string) => `#/${path}${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`;
  let profile = $state<LocalProfile>('official');
  const repository = new PublicReleaseRepository();
  let releaseId = $state<string | null>(null);
  let loading = $state(true);
  let error = $state('');
  let retry = $state(0);
  $effect(() => {
    void retry;
    const controller = new AbortController(); loading = true; error = ''; releaseId = null;
    void repository.current(profile, controller.signal).then(result => { if (!controller.signal.aborted) releaseId = result?.releaseId ?? null; }).catch(() => { if (!controller.signal.aborted) error = 'Release availability could not be checked. Try again.'; }).finally(() => { if (!controller.signal.aborted) loading = false; });
    return () => controller.abort();
  });
  const query = $derived(`profile=${profile}`);
</script>
<svelte:head><title>Downloads · Until Every Cage</title></svelte:head>
<section class="downloads-page" aria-labelledby="downloads-title">
  <h1 id="downloads-title">Downloads</h1>
  <p>Downloads are available after an eligible public release is published.</p>
  <label>Dataset<select bind:value={profile}><option value="official">Curated records</option><option value="secondary">Secondary sources</option><option value="community">Community submissions</option></select></label>
  {#if profile === 'community'}<p class="warning"><strong>Unreviewed community claim — not verified by Until Every Cage.</strong> Privacy screening is not factual review or project approval. Community counts are separate.</p>{/if}
  {#if loading}<p role="status">Checking release availability…</p>{:else if error}<p role="alert">{error}</p><button type="button" onclick={() => retry += 1}>Retry</button>{:else if !releaseId}<p role="status">No public release is available yet.</p>{:else}<p class="release">Current release: {releaseId}</p>{/if}
  <ul>{#if releaseId}<li><a href={`/api/v2/locations.csv?${query}&limit=1000`}>CSV · first up to 1,000 records (facility ID order)</a></li><li><a href={`/api/v2/locations?${query}&limit=100`}>Paginated JSON</a> — follow the response’s next cursor for more records.</li>{/if}<li><a href={`${import.meta.env.BASE_URL}reference/public-openapi.json`} download>OpenAPI specification</a></li></ul>
  <p>Exports use the latest selected public dataset, independent of Browse records filters. CSV returns the first 1,000 eligible records in facility ID order when the release is larger; use JSON pages for the full dataset.</p>
  <h2>Reuse & citation</h2>
  <p>The code is licensed under AGPLv3 or later. The project’s compilation is licensed under CC BY-NC-SA 4.0 where the project holds those rights. Individual sources and map providers may have separate terms.</p>
  <p>Credit Until Every Cage and the original sources; retain source links, release information, dates, and uncertainty labels. Check each source’s rights before redistributing its material.</p>
  <a href={href('database/api')}>API documentation</a> · <a href={href('about/sources')}>Sources & methodology</a>
</section>
<style>
  .downloads-page{width:min(100% - 3rem,46rem);margin:auto;padding:1.5rem 0 2rem;color:#f1efe8;font:.9rem/1.5 system-ui,sans-serif}h1{margin:0 0 1rem;font:500 2rem/1.15 Georgia,serif}h2{margin:1.5rem 0 .5rem;font-size:1.1rem}p{color:#c6d0c5;margin:.75rem 0}label{display:grid;gap:.4rem;max-width:18rem;margin:1rem 0}select{min-height:2.5rem;padding:.5rem;border:1px solid #59615c;background:#202523;color:#f4f1e9;font:inherit}ul{padding-left:1.2rem}li{margin:.55rem 0}a{color:#dce8d9;text-underline-offset:.2em}.warning{padding:.75rem;border-left:3px solid #cf9a66;background:#282723;color:#eee4ce}button{min-height:2.25rem;padding:.4rem .7rem;background:#252f28;border:1px solid #657466;color:#edf0e9;font:inherit}a:focus-visible,select:focus-visible,button:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:40rem){.downloads-page{width:calc(100% - 2rem)}h1{font-size:1.65rem}}
</style>
