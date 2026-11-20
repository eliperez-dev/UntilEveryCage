<script lang="ts">
  import { untrack } from 'svelte';
  import { language, tr } from './language';
  import { LocalLocationRepository, type LocalProfile } from '../api/LocalLocationRepository';
  import { PublicGraphRepository, type GraphFilters } from '../api/PublicGraphRepository';
  import type { PublicGraphConnection } from '../api/publicGraphSchema';
  import { serializeRoute } from './routeState';

  let { facilityId, releaseId, profile = 'official', rail = false, hideWhenEmpty = false, onstatechange }: { facilityId: string; releaseId: string; profile?: LocalProfile; rail?: boolean; hideWhenEmpty?: boolean; onstatechange?: ((state: { count:number; loading:boolean; error:boolean; available:boolean }) => void) | undefined } = $props();
  const graph = new PublicGraphRepository();
  const locations = new LocalLocationRepository();
  let rows = $state<readonly PublicGraphConnection[]>([]);
  let names = $state<Readonly<Record<string, string>>>({});
  let nextCursor = $state<string | null>(null);
  let loading = $state(true);
  let loadingMore = $state(false);
  let error = $state(false);
  let kind = $state<'all' | 'exact' | 'inferred'>('all');
  let confidence = $state<'all' | 'high' | 'medium' | 'low'>('all');
  let retry = $state(0);
  const hasFilters = $derived(kind !== 'all' || confidence !== 'all');
  let controller: AbortController | undefined;
  let requestVersion = 0;
  $effect(() => {
    const state = { count:rows.length, loading, error, available: Boolean(rows.length || nextCursor || hasFilters || error) };
    untrack(() => onstatechange?.(state));
  });

  function filters(cursor?: string): GraphFilters {
    return {
      release_id: releaseId,
      ...(kind === 'all' ? {} : { connection_type: kind }),
      ...(confidence === 'all' ? {} : { confidence_band: confidence }),
      limit: 20,
      ...(cursor ? { cursor } : {}),
    };
  }

  async function load(reset = true) {
    if (!facilityId || !releaseId) return;
    if (reset) {
      controller?.abort();
      controller = new AbortController();
      rows = [];
      names = {};
      nextCursor = null;
      error = false;
      loading = true;
      loadingMore = false;
    } else {
      loadingMore = true;
    }
    const active = controller;
    if (!active) return;
    const version = ++requestVersion;
    try {
      const page = await graph.neighborhood(facilityId, profile, filters(reset ? undefined : nextCursor ?? undefined), active.signal);
      if (active.signal.aborted || version !== requestVersion) return;
      const merged = reset ? page.data : [...rows, ...page.data];
      rows = merged;
      nextCursor = page.nextCursor;
      const ids = [...new Set(page.data.flatMap(edge => {
        const other = edge.from.entity_id === facilityId ? edge.to : edge.from;
        return other.entity_type === 'facility' && other.entity_id ? [other.entity_id] : [];
      }))].filter(id => names[id] === undefined);
      const resolved = await Promise.all(ids.map(async id => {
        try {
          const detail = await locations.detail(id, profile, active.signal, releaseId);
          return [id, detail.location.name] as const;
        } catch { return [id, null] as const; }
      }));
      if (active.signal.aborted || version !== requestVersion) return;
      names = { ...names, ...Object.fromEntries(resolved.filter((item): item is readonly [string, string] => typeof item[1] === 'string')) };
    } catch {
      if (!active.signal.aborted && version === requestVersion) error = true;
    } finally {
      if (!active.signal.aborted && version === requestVersion) {
        loading = false;
        loadingMore = false;
      }
    }
  }

  function recordHref(id: string): string {
    return serializeRoute({ kind: 'record', facilityId: id, profile, releaseId });
  }

  function otherEndpoint(edge: PublicGraphConnection) {
    return edge.from.entity_id === facilityId ? edge.to : edge.from;
  }

  function endpointLabel(edge: PublicGraphConnection): string {
    const endpoint = otherEndpoint(edge);
    if (endpoint.entity_type === 'organization') return endpoint.display_name ?? tr('Organization', $language);
    if (!endpoint.entity_id) return tr('Facility record', $language);
    return names[endpoint.entity_id] ?? tr('Facility record', $language);
  }

  function humanize(value: string): string {
    if (value === 'source_assertion') return 'Source';
    if (value === 'us.aphis') return 'USDA APHIS';
    if (value === 'us.aphis.annual-reports') return 'USDA APHIS annual reports';
    if (value === 'us.inspections') return 'USDA APHIS inspections';
    return value.replaceAll(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/^./, letter => letter.toLocaleUpperCase());
  }

  $effect(() => {
    void facilityId; void releaseId; void profile; void kind; void confidence; void retry;
    void load();
    return () => { controller?.abort(); requestVersion += 1; };
  });
</script>

{#if !hideWhenEmpty || loading || error || rows.length || hasFilters || nextCursor}
<section class="connections" class:rail aria-labelledby="connections-heading">
  <h2 id="connections-heading">{tr('Connections', $language)}</h2>
  {#if kind !== 'all' || confidence !== 'all' || (!loading && !error && rows.length > 0)}<div class="controls">
    <label>{tr('Relationship', $language)} <select bind:value={kind}><option value="all">{tr('All', $language)}</option><option value="exact">{tr('Exact', $language)}</option><option value="inferred">{tr('Inferred', $language)}</option></select></label>
    <label>{tr('Confidence', $language)} <select bind:value={confidence}><option value="all">{tr('All', $language)}</option><option value="high">{tr('High', $language)}</option><option value="medium">{tr('Medium', $language)}</option><option value="low">{tr('Low', $language)}</option></select></label>
  </div>{/if}
  {#if loading}<p role="status">{tr('Loading connections…', $language)}</p>
  {:else if error}<p role="alert">{tr('Connections could not be loaded.', $language)} <button type="button" onclick={() => retry += 1}>{tr('Retry', $language)}</button></p>
  {:else if !rows.length}<p class="empty">{tr('None', $language)}</p>
  {:else}<ul>
    {#each rows as edge (edge.connection_edge_id)}
      {@const endpoint = otherEndpoint(edge)}
      <li>
        <div class="row-heading">
          {#if endpoint.entity_type === 'facility' && endpoint.entity_id}<a href={recordHref(endpoint.entity_id)}>{endpointLabel(edge)}</a>{:else}<span>{endpointLabel(edge)}</span>{/if}
          <span class="relationship">{tr(humanize(edge.relationship_type), $language)}</span>
        </div>
        <p class="meta"><span>{edge.connection_type === 'exact' ? tr('Exact source', $language) : `${tr('Inferred', $language)} · ${tr(humanize(edge.confidence_band), $language)} ${tr('confidence', $language)}`}</span>{#if edge.connection_type === 'inferred'}<span>{Math.round(edge.confidence * 100)}%</span>{/if}</p>
        <details>
          <summary>{tr('Method and evidence', $language)}</summary>
          <dl>
            <div><dt>{tr('Method', $language)}</dt><dd>{tr(humanize(edge.match_method), $language)}</dd></div>
            <div><dt>{tr('Source', $language)}</dt><dd>{edge.provenance.source_ids.join(', ')}</dd></div>
            <div><dt>{tr('Observed', $language)}</dt><dd><time datetime={edge.observed_at}>{new Date(edge.observed_at).toLocaleDateString($language)}</time></dd></div>
            {#if Object.keys(edge.signals).length}<div><dt>{tr('Signals', $language)}</dt><dd>{Object.keys(edge.signals).map(value => tr(humanize(value), $language)).join(', ')}</dd></div>{/if}
            {#if edge.contradictions.length}<div><dt>{tr('Contradictions', $language)}</dt><dd>{edge.contradictions.length} {tr('recorded', $language)}</dd></div>{/if}
          </dl>
        </details>
      </li>
    {/each}
  </ul>
  {#if nextCursor}<button class="more" type="button" disabled={loadingMore} onclick={() => void load(false)}>{tr(loadingMore ? 'Loading…' : 'Load more', $language)}</button>{/if}
  {/if}
</section>
{/if}

<style>
  .connections { margin-top: 1rem; padding-top: .8rem; border-top: 1px solid var(--line); color: var(--ink); }
  .connections h2 { margin: 0 0 .35rem; font-size: 1rem; font-weight: 600; }
  .empty { margin: .35rem 0; }
  .controls { display: flex; flex-wrap: wrap; gap: .6rem 1rem; margin: .5rem 0; }
  .controls label { display: flex; align-items: center; gap: .35rem; font-size: .8125rem; }
  .controls select, .connections button { min-height: 2.75rem; padding: .25rem .5rem; border: 1px solid var(--line); color: var(--ink); background: var(--panel); font: inherit; }
  .connections ul { list-style: none; margin: .5rem 0; padding: 0; }
  .connections li { padding: .55rem 0; border-top: 1px solid var(--line); }
  .row-heading { display: flex; justify-content: space-between; gap: .65rem; align-items: baseline; overflow-wrap: anywhere; }
  .connections a { color: var(--link); text-underline-offset: .2em; }
  .empty, .controls label, .meta, .relationship, summary, dt { color: var(--ink-secondary); }
  .meta { display: flex; flex-wrap: wrap; gap: .25rem .8rem; margin: .2rem 0; font-size: .8125rem; font-variant-numeric: tabular-nums; }
  summary { width: fit-content; min-height: 2.75rem; padding: .6rem 0; cursor: pointer; font-size: .8125rem; }
  .connections dl { margin: 0 0 .35rem; }
  .connections dl div { display: grid; grid-template-columns: 5.5rem minmax(0, 1fr); gap: .5rem; padding: .12rem 0; }
  .connections dd { margin: 0; overflow-wrap: anywhere; }
  .connections button { cursor: pointer; }
  .connections button:hover { background: var(--panel-hover); }
  .more { margin-top: .35rem; }
  .connections :is(a, button, select, summary):focus-visible { outline: 2px solid var(--focus); outline-offset: 3px; }
  @media (max-width: 34rem) {
    .row-heading { align-items: flex-start; flex-direction: column; gap: .1rem; }
    .connections dl div { grid-template-columns: 1fr; gap: 0; }
  }
  .connections.rail { margin-top: .95rem; padding-top: .8rem; border-color: var(--ui-line); color: var(--ui-ink); font: .8125rem/1.55 var(--ui-font); }
  .rail h2 { margin: 0 0 .4rem; font: 500 .875rem/1.4 var(--ui-font); letter-spacing: -.015em; }
  .rail .empty, .rail .controls label, .rail .meta, .rail .relationship, .rail summary, .rail dt { color: var(--ui-muted); }
  .rail .controls { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: .6rem; margin: .5rem 0; }
  .rail .controls label { display: grid; align-items: start; gap: .3rem; font-size: .6875rem; }
  .rail .controls select { width: 100%; max-width: none; min-height: 2.5rem; padding: .35rem .25rem; border: 0; border-bottom: 1px solid var(--ui-line); border-radius: 0; color: var(--ui-ink); background: var(--ui-surface); font-size: .75rem; }
  .rail li { padding: .55rem 0; border-color: var(--ui-line); }
  .rail .row-heading { align-items: flex-start; flex-direction: column; gap: .15rem; }
  .rail .row-heading a { font-weight: 500; }
  .rail .relationship, .rail .meta { font-size: .75rem; }
  .rail a { color: var(--ui-ink); text-underline-offset: .25rem; }
  .rail summary { font-size: .75rem; }
  .rail dl { margin: .35rem 0; padding-left: .65rem; border-left: 1px solid var(--ui-line); font-size: .75rem; }
  .rail dl div { grid-template-columns: 4.5rem minmax(0, 1fr); padding: .18rem 0; }
  .rail button { min-height: 2.5rem; padding: .4rem .65rem; border-color: var(--ui-line); color: var(--ui-ink); background: var(--ui-raised); }
  .rail button:hover { background: var(--ui-hover); }
  .rail a:focus-visible, .rail button:focus-visible, .rail select:focus-visible, .rail summary:focus-visible { outline-color: var(--ui-ink); }
  @media (max-width: 40rem) {
    .rail .controls select, .rail button { min-height: 2.75rem; }
  }
</style>
