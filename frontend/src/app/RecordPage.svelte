<script lang="ts">
  import { createRealPreviewRepository, mapRealPreviewCandidate, RealPreviewError } from '../api/RealPreviewRepository';
  import type { LabRecord } from '../design-lab/contract';
  import ProjectFooter from './ProjectFooter.svelte';
  import RecordDetail from './RecordDetail.svelte';
  import PreviewMasthead from './PreviewMasthead.svelte';
  const mapHref = '#/map?f1a=field';

  let { id }: { id: string } = $props();
  const repository = createRealPreviewRepository();
  let record = $state<LabRecord | null>(null);
  let status = $state<'loading' | 'ready' | 'error' | 'unauthorized'>('loading');
  let error = $state('');

  // A route change cancels the previous detail request, so an older response
  // cannot replace the record currently named in the address bar.
  $effect(() => {
    const controller = new AbortController();
    record = null;
    status = 'loading';
    error = '';
    void repository.detail(id, controller.signal).then(candidate => {
      if (!controller.signal.aborted) {
        record = mapRealPreviewCandidate(candidate);
        status = 'ready';
      }
    }).catch(cause => {
      if (controller.signal.aborted) return;
      status = cause instanceof RealPreviewError && cause.kind === 'unauthorized' ? 'unauthorized' : 'error';
      error = cause instanceof Error ? cause.message : 'This record could not be loaded.';
    });
    return () => controller.abort();
  });
</script>

<svelte:head><title>Record: Until Every Cage</title></svelte:head>
<div class="record-page">
  <PreviewMasthead current="database" {mapHref} databaseHref="#/database?f1a=field" />
  <main id="main-content">
    {#if status === 'loading'}<p class="state" role="status">Loading record evidence…</p>
    {:else if status === 'error' || status === 'unauthorized'}<div class="state" role="alert"><h1>Record unavailable</h1><p>{error}</p><a href="#/database">Return to database</a></div>
    {:else if record}<RecordDetail {record} presentation="page" />{/if}
  </main>
  <ProjectFooter returnMapHref={mapHref} />
</div>

<style>
  .record-page{min-height:100dvh;background:#171a18;color:#f1efe8;font-family:system-ui,sans-serif}
  .state a{color:#ded8c9;text-underline-offset:.2em}
  .state{max-width:50rem;margin:4rem auto;padding:1rem}.state h1{font:500 1.8rem Georgia,serif}
</style>
