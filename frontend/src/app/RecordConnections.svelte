<script lang="ts">
  import { LocalLocationRepository, type LocalProfile } from '../api/LocalLocationRepository';
  import { PublicGraphRepository, type GraphFilters } from '../api/PublicGraphRepository';
  import type { PublicGraphConnection } from '../api/publicGraphSchema';
  import type { LocationSourceFacts } from '../domain/location';
  import AphisReports from './AphisReports.svelte';
  import { serializeRoute } from './routeState';

  let { facilityId, releaseId, profile = 'official', sourceId, sourceFacts }: { facilityId: string; releaseId: string; profile?: LocalProfile; sourceId?: string | undefined; sourceFacts?: LocationSourceFacts | undefined } = $props();
  const graph = new PublicGraphRepository();
  const locations = new LocalLocationRepository();
  let rows = $state<readonly PublicGraphConnection[]>([]);
  let names = $state<Readonly<Record<string, string>>>({});
  let nextCursor = $state<string | null>(null);
  let loading = $state(false);
  let loadingMore = $state(false);
  let error = $state(false);
  let kind = $state<'all' | 'exact' | 'inferred'>('all');
  let confidence = $state<'all' | 'high' | 'medium' | 'low'>('all');
  let retry = $state(0);
  let controller: AbortController | undefined;
  let requestVersion = 0;

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
    if (endpoint.entity_type === 'organization') return endpoint.display_name ?? 'Organization';
    if (!endpoint.entity_id) return 'Facility record';
    return names[endpoint.entity_id] ?? 'Facility record';
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

<section class="connections" aria-labelledby="connections-heading">
  <h2 id="connections-heading">Connections</h2>
  <div class="controls">
    <label>Relationship <select bind:value={kind}><option value="all">All</option><option value="exact">Exact</option><option value="inferred">Inferred</option></select></label>
    <label>Confidence <select bind:value={confidence}><option value="all">All</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
  </div>
  {#if loading}<p role="status">Loading connections…</p>
  {:else if error}<p role="alert">Connections could not be loaded. <button type="button" onclick={() => retry += 1}>Retry</button></p>
  {:else if !rows.length}<p class="empty">No connections in this release.</p>
  {:else}<ul>
    {#each rows as edge (edge.connection_edge_id)}
      {@const endpoint = otherEndpoint(edge)}
      <li>
        <div class="row-heading">
          {#if endpoint.entity_type === 'facility' && endpoint.entity_id}<a href={recordHref(endpoint.entity_id)}>{endpointLabel(edge)}</a>{:else}<span>{endpointLabel(edge)}</span>{/if}
          <span class="relationship">{humanize(edge.relationship_type)}</span>
        </div>
        <p class="meta"><span>{edge.connection_type === 'exact' ? 'Exact source' : `Inferred · ${humanize(edge.confidence_band)} confidence`}</span>{#if edge.connection_type === 'inferred'}<span>{Math.round(edge.confidence * 100)}%</span>{/if}</p>
        <details>
          <summary>Method and evidence</summary>
          <dl>
            <div><dt>Method</dt><dd>{humanize(edge.match_method)}</dd></div>
            <div><dt>Source</dt><dd>{edge.provenance.source_ids.map(humanize).join(', ')}</dd></div>
            <div><dt>Observed</dt><dd><time datetime={edge.observed_at}>{new Date(edge.observed_at).toLocaleDateString()}</time></dd></div>
            {#if Object.keys(edge.signals).length}<div><dt>Signals</dt><dd>{Object.keys(edge.signals).map(humanize).join(', ')}</dd></div>{/if}
            {#if edge.contradictions.length}<div><dt>Contradictions</dt><dd>{edge.contradictions.length} recorded</dd></div>{/if}
          </dl>
          {#if edge.connection_type === 'inferred'}<p class="limitation">{edge.disclaimer}</p>{/if}
        </details>
      </li>
    {/each}
  </ul>
  {#if nextCursor}<button class="more" type="button" disabled={loadingMore} onclick={() => void load(false)}>{loadingMore ? 'Loading…' : 'Load more'}</button>{/if}
  {/if}
  <AphisReports {facilityId} {releaseId} {profile} {sourceId} {sourceFacts} />
</section>

<style>
  .connections{margin-top:1rem;padding-top:.8rem;border-top:1px solid #3c4640;color:#edf0e9;font:.82rem/1.45 system-ui,sans-serif}.connections h2{margin:0 0 .35rem;font:600 1rem/1.3 Georgia,serif}.empty{margin:.35rem 0;color:#b9c3b7}.controls{display:flex;flex-wrap:wrap;gap:.55rem;margin:.6rem 0}.controls label{display:flex;align-items:center;gap:.35rem;color:#c6d0c5}.controls select{max-width:9rem;min-height:2rem;padding:.25rem .4rem;background:#202523;border:1px solid #59615c;color:#edf0e9;font:inherit}.connections ul{list-style:none;margin:.5rem 0;padding:0}.connections li{padding:.6rem 0;border-top:1px solid #303a33}.row-heading{display:flex;justify-content:space-between;gap:.65rem;align-items:baseline}.row-heading a,.connections a{color:#dce8d9;text-underline-offset:.2em}.relationship{color:#d0c7b3}.meta{display:flex;flex-wrap:wrap;gap:.25rem .8rem;margin:.2rem 0;color:#b9c3b7;font-size:.75rem;font-variant-numeric:tabular-nums}.connections details{margin-top:.25rem}.connections summary{width:fit-content;color:#c6d0c5;cursor:pointer;text-underline-offset:.2em}.connections dl{margin:.35rem 0}.connections dl div{display:grid;grid-template-columns:5.5rem minmax(0,1fr);gap:.5rem;padding:.12rem 0}.connections dt{color:#b9c3b7}.connections dd{margin:0;overflow-wrap:anywhere}.limitation{margin:.4rem 0;color:#c6d0c5}.connections button{min-height:2rem;padding:.25rem .45rem;background:#252f28;border:1px solid #657466;color:#edf0e9;font:inherit;cursor:pointer}.more{margin-top:.35rem}.connections a:focus-visible,.connections button:focus-visible,.connections select:focus-visible,.connections summary:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:34rem){.row-heading{align-items:flex-start;flex-direction:column;gap:.1rem}.connections dl div{grid-template-columns:1fr;gap:0}}
</style>
