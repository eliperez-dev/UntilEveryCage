<script lang="ts">
  import { untrack, type Snippet } from 'svelte';
  import { language, tr } from './language';
  import { AphisReportsRepository, canHaveAphisAnnualReports, isAphisRelevant, type AphisReportKind } from '../api/AphisReportsRepository';
  import type { LocalProfile } from '../api/LocalLocationRepository';
  import type { LocationSourceFacts } from '../domain/location';
  import type { PublicAphisReportLink } from '../api/publicGraphSchema';

  let { facilityId, releaseId, profile, sourceId, sourceFacts, children }: {
    facilityId: string; releaseId: string; profile: LocalProfile; sourceId?: string | undefined; sourceFacts?: LocationSourceFacts | undefined; children?: Snippet;
  } = $props();

  type ReportList = {
    rows: readonly PublicAphisReportLink[];
    cursor: string | null;
    loading: boolean;
    error: boolean;
  };

  const repository = new AphisReportsRepository();
  const groups = [
    { kind: 'annual_reports', title: 'Annual reports', empty: 'No annual reports found.' },
    { kind: 'inspections', title: 'Inspection reports', empty: 'No inspection reports found.' },
  ] as const;
  const newList = (): ReportList => ({ rows: [], cursor: null, loading: true, error: false });
  let lists = $state<Record<AphisReportKind, ReportList>>({ annual_reports: newList(), inspections: newList() });
  const relevant = $derived(isAphisRelevant(sourceId, sourceFacts));
  const annualApplicable = $derived(canHaveAphisAnnualReports(sourceId, sourceFacts));
  let controller: AbortController | undefined;

  async function fetchPage(kind: AphisReportKind, active: AbortController, includeAnnualHistory = false) {
    if (active.signal.aborted) return;
    const list = lists[kind];
    try {
      const pageCount = includeAnnualHistory ? 2 : 1;
      for (let index = 0; index < pageCount; index += 1) {
        const cursor = list.cursor;
        const page = await repository.page(facilityId, profile, kind, releaseId, 20, cursor ?? undefined, active.signal);
        if (active.signal.aborted) return;
        const rows = new Map(list.rows.map(row => [row.reference_id, row]));
        for (const row of page.data) rows.set(row.reference_id, row);
        list.rows = [...rows.values()];
        list.cursor = page.nextCursor === cursor ? null : page.nextCursor;
        if (!list.cursor || list.rows.length >= 20) break;
      }
    } catch {
      if (!active.signal.aborted) list.error = true;
    } finally {
      if (!active.signal.aborted) list.loading = false;
    }
  }

  function loadMore(kind: AphisReportKind) {
    const list = lists[kind];
    if (!controller || list.loading) return;
    list.loading = true;
    list.error = false;
    void fetchPage(kind, controller);
  }

  $effect(() => {
    if (!relevant || !facilityId || !releaseId || !profile) return;
    const active = new AbortController();
    controller = active;
    lists = { annual_reports: newList(), inspections: newList() };
    // The report resolver has a shared upstream concurrency limit. Start both
    // lookups on open, one at a time, without blocking the record or its map.
    const start = annualApplicable ? () => fetchPage('annual_reports', active, true) : () => Promise.resolve();
    untrack(() => { void start().then(() => fetchPage('inspections', active)); });
    return () => { active.abort(); };
  });
</script>

{#if relevant}
  <section class="aphis-reports" aria-labelledby="aphis-reports-heading">
    <h2 id="aphis-reports-heading">{tr('APHIS reports', $language)}</h2>
    {#each groups as group (group.kind)}
      {@const list = lists[group.kind]}
      <section aria-label={tr(group.title, $language)}>
        <h3>{tr(group.title, $language)}</h3>
        {#if list.rows.length}
          <ul>
            {#each list.rows as reference (reference.reference_id)}
              <li>
                <span>{reference.evidence_type === 'annual_reports' ? `${tr('Annual report', $language)} · FY${reference.event_period}` : `${tr('Inspection', $language)} · ${reference.event_date}`}</span>
                {#if reference.report_url}<a href={reference.report_url} target="_blank" rel="noopener noreferrer">{tr('Open report', $language)}</a>{/if}
                {#if reference.column_e_url}<a href={reference.column_e_url} target="_blank" rel="noopener noreferrer">{tr('Column E narrative', $language)}</a>{/if}
                {#if !reference.report_url && !reference.column_e_url}<a href={reference.source_url} target="_blank" rel="noopener noreferrer">{tr('Open APHIS source page', $language)}</a>{/if}
              </li>
            {/each}
          </ul>
        {/if}
        {#if group.kind === 'annual_reports' && !annualApplicable}
          <p>{tr('Annual reports are for research facilities.', $language)}</p>
        {:else if list.loading}
          <p role="status">{tr('Loading reports…', $language)}</p>
        {:else if list.error}
          <p role="alert">{tr('Reports could not be loaded.', $language)} <button type="button" onclick={() => loadMore(group.kind)}>{tr('Retry', $language)}</button></p>
        {:else if list.cursor}
          <button type="button" onclick={() => loadMore(group.kind)}>{tr('Load more', $language)} {tr(group.title, $language).toLocaleLowerCase()}</button>
        {:else if !list.rows.length}
          <p>{tr(group.empty, $language)}</p>
        {/if}
      </section>
    {/each}
    {@render children?.()}
  </section>
{/if}

<style>
  .aphis-reports { padding-block: .9rem; border-top: 1px solid var(--line); color: var(--ink); }
  h2 { margin: 0 0 .65rem; font: 650 1.0625rem/1.4 var(--ui-font); }
  h3 { margin: .65rem 0 .25rem; font: 600 .9375rem/1.4 var(--ui-font); }
  p { margin: .3rem 0; color: var(--ink-secondary); }
  ul { list-style: none; margin: 0; padding: 0; }
  li { display: flex; flex-wrap: wrap; align-items: baseline; gap: .25rem .8rem; padding: .45rem 0; border-bottom: 1px solid var(--line); }
  li span { flex: 1 0 10rem; }
  a, button { color: var(--link); text-decoration: underline; text-underline-offset: .2em; }
  button { min-height: 44px; border: 0; padding: 0 .25rem; background: transparent; font: inherit; cursor: pointer; }
  button:focus-visible, a:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
</style>
