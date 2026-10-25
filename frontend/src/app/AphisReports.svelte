<script lang="ts">
  import { AphisReportsRepository, isAphisRelevant, type AphisReportKind } from '../api/AphisReportsRepository';
  import type { LocalProfile } from '../api/LocalLocationRepository';
  import type { LocationSourceFacts } from '../domain/location';
  import type { PublicAphisReportLink } from '../api/publicGraphSchema';

  let { facilityId, releaseId, profile, sourceId, sourceFacts }: {
    facilityId: string; releaseId: string; profile: LocalProfile; sourceId?: string | undefined; sourceFacts?: LocationSourceFacts | undefined;
  } = $props();
  const repository = new AphisReportsRepository();
  const kinds: readonly AphisReportKind[] = ['annual_reports', 'inspections'];
  let selected = $state<AphisReportKind | null>(null);
  let rows = $state<readonly PublicAphisReportLink[]>([]);
  let cursor = $state<string | null>(null);
  let loading = $state(false);
  let error = $state(false);
  let retryCursor = $state<string | null>(null);
  let fetched = $state(false);
  let version = 0;
  let controller: AbortController | undefined;
  const queryKey = $derived(`${facilityId}\u0000${releaseId}\u0000${profile}`);

  const relevant = $derived(isAphisRelevant(sourceId, sourceFacts));

  function title(kind: AphisReportKind): string {
    return kind === 'annual_reports' ? 'Annual reports' : 'Inspection reports';
  }

  async function load(kind: AphisReportKind, next?: string) {
    if (!relevant || !facilityId || !releaseId) return;
    if (loading) return;
    if (selected === kind && !next && !error && fetched) return;
    if (selected !== kind || !next) {
      controller?.abort();
      controller = new AbortController();
      selected = kind;
      rows = [];
      cursor = null;
      retryCursor = null;
      fetched = false;
    }
    const active = controller;
    if (!active) return;
    const request = ++version;
    loading = true;
    error = false;
    try {
      const page = await repository.page(facilityId, profile, kind, releaseId, 20, next, active.signal);
      if (active.signal.aborted || request !== version || page.releaseId !== releaseId) return;
      rows = next ? [...rows, ...page.data] : page.data;
      cursor = page.nextCursor;
      retryCursor = null;
      fetched = true;
    } catch {
      if (!active.signal.aborted && request === version) { error = true; retryCursor = next ?? null; }
    } finally {
      if (!active.signal.aborted && request === version) loading = false;
    }
  }

  $effect(() => {
    void queryKey;
    controller?.abort();
    version += 1;
    selected = null;
    rows = [];
    cursor = null;
    retryCursor = null;
    fetched = false;
    loading = false;
    error = false;
    return () => { controller?.abort(); version += 1; };
  });
</script>

{#if relevant}
  <section class="aphis-reports" aria-labelledby="aphis-reports-heading">
    <h3 id="aphis-reports-heading">APHIS reports</h3>
    <div class="choices" aria-label="Choose APHIS report type">
      {#each kinds as kind}
        <button type="button" aria-pressed={selected === kind} disabled={loading} onclick={() => void load(kind)}>{kind === 'annual_reports' ? 'Fetch annual reports' : 'Fetch inspection reports'}</button>
      {/each}
    </div>
    {#if selected}
      <h4>{title(selected)}</h4>
      {#if error}<p role="alert">Report references could not be loaded. <button type="button" onclick={() => void load(selected!, retryCursor ?? undefined)}>Retry</button></p>{/if}
      {#if loading}<p role="status">Loading report references…</p>
      {:else if rows.length}
        <ul>
          {#each rows as reference (reference.reference_id)}
            <li>
              <span>{reference.evidence_type === 'annual_reports' ? `Annual report · FY${reference.event_period}` : `Inspection · ${reference.event_date}`}</span>
              {#if reference.report_url}<a href={reference.report_url} target="_blank" rel="noopener noreferrer">Open report</a>{/if}
              {#if reference.column_e_url}<a href={reference.column_e_url} target="_blank" rel="noopener noreferrer">Column E narrative</a>{/if}
              {#if !reference.report_url && !reference.column_e_url}<a href={reference.source_url} target="_blank" rel="noopener noreferrer">Open APHIS source page</a>{/if}
            </li>
          {/each}
        </ul>
        {#if cursor}<button type="button" disabled={loading} onclick={() => void load(selected!, cursor!)}>Load more {title(selected).toLocaleLowerCase()}</button>{/if}
      {:else if !error && cursor}<p>No matching references on this page.</p><button type="button" disabled={loading} onclick={() => void load(selected!, cursor!)}>Load more {title(selected).toLocaleLowerCase()}</button>
      {:else if !error}<p>No {title(selected).toLocaleLowerCase()} references are available in this release.</p>{/if}
    {/if}
  </section>
{/if}

<style>
  .aphis-reports{margin-top:.8rem;padding-top:.65rem;border-top:1px solid #303a33}.aphis-reports h3{margin:0 0 .25rem;font:600 .95rem/1.3 Georgia,serif}.aphis-reports h4{margin:.65rem 0 .2rem;font-size:.85rem}.aphis-reports p{margin:.35rem 0;color:#b9c3b7}.choices{display:flex;flex-wrap:wrap;gap:.45rem;margin:.5rem 0}.aphis-reports ul{list-style:none;margin:.45rem 0;padding:0}.aphis-reports li{display:flex;flex-wrap:wrap;justify-content:space-between;gap:.5rem;padding:.5rem 0;border-top:1px solid #303a33}.aphis-reports a{color:#dce8d9;text-underline-offset:.2em}.aphis-reports button{min-height:2rem;padding:.25rem .45rem;background:#252f28;border:1px solid #657466;color:#edf0e9;font:inherit;cursor:pointer}.aphis-reports button:focus-visible,.aphis-reports a:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}.aphis-reports button:disabled{opacity:.65;cursor:wait}
</style>
