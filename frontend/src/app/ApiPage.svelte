<script lang="ts">
  import { language, tr } from './language';
  import { onMount } from 'svelte';
  import { PublicReleaseRepository } from '../api/PublicReleaseRepository';
  import type { LocalProfile } from '../api/LocalLocationRepository';
  import { publicReleaseLabel } from '../features/locations/releasePresentation';
  import { explorerOptions, guardExplorerRequest, type ExplorerRequest } from './publicApiExplorer';
  import swaggerTheme from './swaggerTheme.css?raw';
  type SwaggerFactory = ((options: Record<string, unknown>) => { unmount?(): void }) & { presets: { apis: unknown } };
  let host: HTMLDivElement;
  let loading = $state(true);
  let error = $state('');
  let communitySelected = $state(false);
  let communityRequested = $state(false);
  let communityReleaseAvailable = $state(false);
  let profile = $state<LocalProfile>('official');
  let { selectedReleaseId: selectedFromRoute = null }: { selectedReleaseId?: string | null } = $props();
  let selectedReleaseId = $state<string | null>(null);
  let releaseOptions = $state<readonly { id: string; label: string }[]>([]);
  let releaseId = $state<string | null>(null);
  let releaseDate = $state<string | null>(null);
  let releaseLoading = $state(true);
  let releaseError = $state('');
  let retry = $state(0);
  const repository = new PublicReleaseRepository();
  const base = import.meta.env.BASE_URL;
  const reference = `${base}reference/`;
  const V0_ARCHIVE_RELEASE_ID = 'v0-candidate-2026-10-04-r3';
  const query = $derived(new URLSearchParams({ profile, ...(releaseId ? { release_id: releaseId } : {}) }).toString());
  const releaseLabel = (id: string, date?: string) => {
    const readableDate = date ? new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(date)) : null;
    return readableDate ? `${readableDate} · ${publicReleaseLabel(id) ?? 'Public release'}` : publicReleaseLabel(id) ?? id;
  };

  $effect(() => { selectedReleaseId = selectedFromRoute ?? null; });
  let activeSelectionProfile = $state<LocalProfile>('official');
  $effect(() => {
    if (activeSelectionProfile !== profile) {
      activeSelectionProfile = profile;
      selectedReleaseId = null;
    }
  });

  $effect(() => {
    void retry;
    const requestedReleaseId = selectedReleaseId;
    const controller = new AbortController(); releaseLoading = true; releaseError = ''; releaseId = null; releaseDate = null; releaseOptions = [];
    void (async () => {
      const active = await repository.current(profile, controller.signal);
      const history = profile === 'official' && active?.releaseId !== V0_ARCHIVE_RELEASE_ID
        ? await repository.current(profile, controller.signal, V0_ARCHIVE_RELEASE_ID) : null;
      if (controller.signal.aborted) return;
      const available = [active, history].filter((item): item is NonNullable<typeof item> => item !== null);
      const chosenId = requestedReleaseId ?? active?.releaseId ?? null;
      if (!requestedReleaseId && chosenId) selectedReleaseId = chosenId;
      const selected = chosenId === active?.releaseId ? active
        : chosenId === history?.releaseId ? history
          : chosenId ? await repository.current(profile, controller.signal, chosenId) : null;
      if (controller.signal.aborted) return;
      releaseOptions = available.map(item => ({ id: item.releaseId, label: releaseLabel(item.releaseId, item.mapGeneratedAt) }));
      if (selected && !available.some(item => item.releaseId === selected.releaseId)) {
        releaseOptions = [...releaseOptions, { id: selected.releaseId, label: releaseLabel(selected.releaseId, selected.mapGeneratedAt) }];
      }
      releaseId = selected?.releaseId ?? null;
      releaseDate = selected?.mapGeneratedAt ?? null;
      if (requestedReleaseId && !selected) releaseError = 'The selected release is unavailable for this dataset.';
    })().catch(() => { if (!controller.signal.aborted) releaseError = 'Release availability could not be checked. Try again.'; }).finally(() => { if (!controller.signal.aborted) releaseLoading = false; });
    return () => controller.abort();
  });

  onMount(() => {
    let disposed = false;
    let instance: ReturnType<SwaggerFactory> | undefined;
    void repository.current('community').then(result => { if (!disposed) communityReleaseAvailable = result !== null; }).catch(() => { if (!disposed) communityReleaseAvailable = false; });
    const shadow = host.attachShadow({ mode: 'open' });
    const stylesheet = document.createElement('link'); stylesheet.rel = 'stylesheet'; stylesheet.href = `${reference}swagger-ui.css`;
    const theme = document.createElement('style'); theme.textContent = swaggerTheme;
    const container = document.createElement('div'); container.setAttribute('aria-label', 'Public API explorer');
    shadow.append(stylesheet, theme, container);
    const watchProfile = () => { communitySelected = [...shadow.querySelectorAll('tr')].some(row => row.querySelector('.parameters-col_name')?.textContent?.includes('profile') && row.querySelector('select')?.value === 'community'); };
    shadow.addEventListener('change', watchProfile); shadow.addEventListener('input', watchProfile);
    void (async () => {
      try {
        const runtime = window as unknown as { SwaggerUIBundle?: SwaggerFactory };
        if (!runtime.SwaggerUIBundle) await new Promise<void>((resolve, reject) => {
          const script = document.createElement('script'); script.src = `${reference}swagger-ui-bundle.js`; script.async = true;
          script.onload = () => resolve(); script.onerror = () => reject(new Error('The API explorer could not be loaded.')); document.head.append(script);
        });
        if (disposed) return;
        const factory = runtime.SwaggerUIBundle;
        if (!factory) throw new Error('The API explorer could not be loaded.');
        instance = factory({ ...explorerOptions, domNode: container, url: `${reference}public-openapi.json`, presets: [factory.presets.apis], layout: 'BaseLayout',
          requestInterceptor: (request: ExplorerRequest) => {
            const guarded = guardExplorerRequest(request, window.location.origin, base);
            const selectedProfile = new URL(guarded.url).searchParams.get('profile');
            if (selectedProfile === 'community') communityRequested = true;
            return guarded;
          },
          onComplete: () => { if (!disposed) loading = false; },
        });
      } catch (failure) { if (!disposed) { loading = false; error = failure instanceof Error ? failure.message : 'The API explorer could not be loaded.'; } }
    })();
    return () => { disposed = true; shadow.removeEventListener('change', watchProfile); shadow.removeEventListener('input', watchProfile); instance?.unmount?.(); shadow.replaceChildren(); };
  });
</script>
<svelte:head><title>API and data access · Until Every Cage</title></svelte:head>
<section class="api-page" aria-labelledby="api-title">
  <h1 id="api-title">{tr('API and data access', $language)}</h1>
  <p>{tr('Download the complete selected public release as CSV, or use paginated JSON to browse records. Downloads cover the selected release, not only the current map or database results.', $language)}</p>
  <div class="release-access">
    <label>{tr('Dataset', $language)}<select bind:value={profile}><option value="official">{tr('Project dataset', $language)}</option>{#if communityReleaseAvailable}<option value="community">{tr('Community submissions', $language)}</option>{/if}</select></label>
    {#if releaseOptions.length}<label>{tr('Release', $language)}<select aria-label={tr('Public release', $language)} value={releaseId ?? selectedReleaseId ?? ''} onchange={event => selectedReleaseId = event.currentTarget.value}>{#each releaseOptions as release}<option value={release.id}>{release.label}</option>{/each}</select></label>{/if}
    {#if profile === 'community'}<p class="community-warning"><strong>Unreviewed community claims are not verified by Until Every Cage.</strong> This opt-in profile is separate from project totals. Privacy screening does not mean factual review or project approval.</p>{/if}
    {#if releaseLoading}<p role="status">Checking the current release…</p>{:else if releaseError}<p role="alert">{releaseError} <button type="button" onclick={() => retry += 1}>Retry</button></p>{:else if !releaseId}<p role="status">No public release is available for this dataset yet.</p>{:else}
      <p class="release-label">{profile === 'official' ? 'Project dataset' : 'Community submissions'}{#if releaseDate} · map snapshot generated {new Intl.DateTimeFormat('en', { dateStyle: 'long', timeZone: 'UTC' }).format(new Date(releaseDate))}{:else} · {publicReleaseLabel(releaseId)}{/if}</p>
      <p class="release-id">{tr('API release ID:', $language)} <code>{releaseId}</code></p>
      <p class="download-links"><a href={`/api/v2/locations.csv?${query}`}>{tr('Download complete CSV', $language)}</a> · <a href={`/api/v2/locations?${query}&limit=100`}>{tr('Paginated JSON (100 per page)', $language)}</a> · <a href={`${reference}public-openapi.json`} download>{tr('OpenAPI specification', $language)}</a></p>
    {/if}
  </div>
  <p class="pagination-note">A release is a dated, versioned snapshot. The date identifies its creation; current privacy restrictions still apply to older views. The API ID above selects that specific release.</p>
  {#if communitySelected || communityRequested}<p class="community-warning" role="status"><strong>Unreviewed community claims are not verified by Until Every Cage.</strong> Community results are separate from project totals; privacy screening is not factual review or project approval.</p>{/if}
  {#if loading}<p role="status">Loading the API explorer…</p>{/if}
  {#if error}<p role="alert">{error} <button type="button" onclick={() => window.location.reload()}>Try again</button></p>{/if}
  <div class="explorer" bind:this={host}></div>
  <section class="reuse"><h2>{tr('Reuse and citation', $language)}</h2><p>{tr('The code is licensed under AGPLv3 or later. The project compilation is licensed under CC BY-NC-SA 4.0 where the project holds those rights. Individual sources and map providers may have separate terms.', $language)}</p><p>{tr('Credit Until Every Cage and the original sources; retain source links, release IDs, dates, and uncertainty labels. Check source rights before redistributing material.', $language)}</p></section>
</section>
<style>
  .api-page{width:min(100% - 3rem,72rem);margin:auto;padding:1.5rem 0 2.5rem;color:#f1efe8;font:.9rem/1.5 system-ui,sans-serif}h1{margin:0 0 .65rem;font:500 2rem/1.15 Georgia,serif}h2{margin:0 0 .45rem;font:600 1rem/1.35 system-ui,sans-serif}p{margin:.55rem 0;color:#c6d0c5}a{color:var(--api-link);text-underline-offset:.2rem}.release-access{margin:1rem 0;padding:.85rem 1rem;border:1px solid #465148;background:#191e1b}.release-access label{display:grid;gap:.35rem;max-width:20rem;margin:.55rem 0;font-size:.8rem}.release-access select{min-height:2.4rem;padding:.4rem .5rem;border:1px solid #59615c;background:#202523;color:#f4f1e9;font:inherit}.release-label{color:#eee9df}.release-id{font-size:.77rem}.release-id code{overflow-wrap:anywhere;color:#eee9df}.download-links{margin-top:.75rem}.pagination-note{font-size:.8rem}.community-warning{padding:.7rem;border-left:3px solid #cf9a66;background:#282723;color:#eee4ce}.explorer{margin-top:1rem;min-width:0}.reuse{margin-top:1.5rem;padding-top:1rem;border-top:1px solid #3d4740}.release-access button,.api-page button{min-height:2rem;padding:.35rem .65rem;background:#252f28;border:1px solid #657466;color:#edf0e9;font:inherit}.api-page a:focus-visible,.api-page select:focus-visible,.api-page button:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}
  @media(max-width:40rem){.api-page{width:calc(100% - 2rem);padding-top:1.2rem}h1{font-size:1.7rem}.download-links{line-height:1.8}.release-access{padding:.75rem}}
</style>
