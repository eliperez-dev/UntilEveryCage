<script lang="ts">
  import { onMount } from 'svelte';
  import { explorerOptions, guardExplorerRequest, type ExplorerRequest } from './publicApiExplorer';
  import swaggerTheme from './swaggerTheme.css?raw';
  type SwaggerFactory = ((options: Record<string, unknown>) => { unmount?(): void }) & { presets: { apis: unknown } };
  let host: HTMLDivElement;
  let loading = $state(true);
  let error = $state('');
  let communitySelected = $state(false);
  let communityRequested = $state(false);
  const base = import.meta.env.BASE_URL;
  const reference = `${base}reference/`;

  onMount(() => {
    let disposed = false;
    let instance: ReturnType<SwaggerFactory> | undefined;
    const shadow = host.attachShadow({ mode: 'open' });
    const stylesheet = document.createElement('link'); stylesheet.rel = 'stylesheet'; stylesheet.href = `${reference}swagger-ui.css`;
    const theme = document.createElement('style'); theme.textContent = swaggerTheme;
    const container = document.createElement('div'); container.setAttribute('aria-label', 'Public API explorer');
    shadow.append(stylesheet, theme, container);
    const watchProfile = () => {
      communitySelected = [...shadow.querySelectorAll('tr')].some(row => row.querySelector('.parameters-col_name')?.textContent?.includes('profile') && row.querySelector('select')?.value === 'community');
    };
    shadow.addEventListener('change', watchProfile);
    shadow.addEventListener('input', watchProfile);
    void (async () => {
      try {
        const runtime = window as unknown as { SwaggerUIBundle?: SwaggerFactory };
        if (!runtime.SwaggerUIBundle) {
          await new Promise<void>((resolve, reject) => {
            const script = document.createElement('script'); script.src = `${reference}swagger-ui-bundle.js`; script.async = true;
            script.onload = () => resolve(); script.onerror = () => reject(new Error('The API explorer could not be loaded.'));
            document.head.append(script);
          });
        }
        if (disposed) return;
        const factory = runtime.SwaggerUIBundle;
        if (!factory) throw new Error('The API explorer could not be loaded.');
        instance = factory({
          ...explorerOptions, domNode: container, url: `${reference}public-openapi.json`,
          presets: [factory.presets.apis], layout: 'BaseLayout',
          requestInterceptor: (request: ExplorerRequest) => {
            const guarded = guardExplorerRequest(request, window.location.origin, base);
            if (new URL(guarded.url).searchParams.get('profile') === 'community') communityRequested = true;
            return guarded;
          },
          onComplete: () => { if (!disposed) loading = false; },
        });
      } catch (failure) { if (!disposed) { loading = false; error = failure instanceof Error ? failure.message : 'The API explorer could not be loaded.'; } }
    })();
    return () => { disposed = true; shadow.removeEventListener('change', watchProfile); shadow.removeEventListener('input', watchProfile); instance?.unmount?.(); shadow.replaceChildren(); };
  });
</script>
<svelte:head><title>API & downloads · Until Every Cage</title></svelte:head>
<section class="api-page" aria-labelledby="api-title">
  <h1 id="api-title">API & downloads</h1>
  <p>Public data are available when a release has been published. The explorer reads public releases only.</p>
  <p class="download-links"><a href="/api/v2/locations.csv?profile=official">Curated CSV (up to 1,000 records)</a> · <a href="/api/v2/locations?profile=official&limit=100">Paginated JSON</a> · <a href={`${reference}public-openapi.json`} download>OpenAPI specification</a></p>
  <p class="pagination-note">For larger exports, follow the JSON response’s next cursor to retrieve each page.</p>
  {#if communitySelected || communityRequested}<p class="community-warning" role="status"><strong>Unreviewed community claim — not verified by Until Every Cage.</strong> Community results are separate from curated totals; privacy screening is not factual review or project approval.</p>{/if}
  {#if loading}<p role="status">Loading the API explorer…</p>{/if}
  {#if error}<p role="alert">{error} <button type="button" onclick={() => window.location.reload()}>Try again</button></p>{/if}
  <div class="explorer" bind:this={host}></div>
</section>
<style>
  .api-page{width:min(100% - 3rem,72rem);margin:auto;padding:1.5rem 0 2.5rem;color:#f1efe8;font:.9rem/1.5 system-ui,sans-serif}h1{margin:0 0 1rem;font:500 2rem/1.15 Georgia,serif}p{margin:.6rem 0;color:#c6d0c5}a{color:#dce8d9;text-underline-offset:.2rem}.pagination-note{font-size:.82rem}.community-warning{padding:.75rem;border-left:3px solid #cf9a66;background:#282723;color:#eee4ce}.explorer{margin-top:1rem;min-width:0}@media(max-width:40rem){.api-page{width:calc(100% - 2rem)}h1{font-size:1.65rem}.download-links{line-height:1.8}}
</style>
