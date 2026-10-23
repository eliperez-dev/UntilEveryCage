<script lang="ts">
  import { LocalLocationRepository, type LocalProfile } from '../api/LocalLocationRepository';
  import { PublicGraphRepository, type GraphFilters } from '../api/PublicGraphRepository';
  import type { PublicGraphConnection, PublicGraphEvidenceReference } from '../api/publicGraphSchema';
  import { serializeRoute } from './routeState';

  let { facilityId, releaseId, profile = 'official' }: { facilityId: string; releaseId: string; profile?: LocalProfile } = $props();
  const graph = new PublicGraphRepository();
  const locations = new LocalLocationRepository();
  let rows = $state<readonly PublicGraphConnection[]>([]);
  let evidenceReferences = $state<readonly PublicGraphEvidenceReference[]>([]);
  let names = $state<Readonly<Record<string, string>>>({});
  let nextCursor = $state<string | null>(null);
  let evidenceCursor = $state<string | null>(null);
  let loading = $state(false);
  let loadingMore = $state(false);
  let evidenceLoading = $state(false);
  let evidenceLoadingMore = $state(false);
  let evidenceError = $state(false);
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
      evidenceReferences = [];
      names = {};
      nextCursor = null;
      evidenceCursor = null;
      error = false;
      evidenceError = false;
      loading = true;
    } else {
      loadingMore = true;
    }
    const active = controller;
    if (!active) return;
    const version = ++requestVersion;
    if (reset) void loadEvidenceReferences();
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

  async function loadEvidenceReferences(cursor?: string) {
    if (!facilityId || !releaseId || !controller) return;
    const active = controller;
    const version = requestVersion;
    if (cursor) evidenceLoadingMore = true;
    else evidenceLoading = true;
    evidenceError = false;
    try {
      const page = await graph.evidenceReferences(facilityId, profile, {
        release_id: releaseId, limit: 20, ...(cursor ? { cursor } : {}),
      }, active.signal);
      if (active.signal.aborted || version !== requestVersion || page.releaseId !== releaseId) return;
      evidenceReferences = cursor ? [...evidenceReferences, ...page.data] : page.data;
      evidenceCursor = page.nextCursor;
    } catch {
      if (!active.signal.aborted && version === requestVersion) evidenceError = true;
    } finally {
      if (!active.signal.aborted && version === requestVersion) {
        evidenceLoading = false;
        evidenceLoadingMore = false;
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
  <p class="explanation">Exact connections come from an explicit source key or assertion. Inferred connections are ruleset estimates, not proof of identity or ownership.</p>
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
        <p class="meta"><span>{edge.connection_type === 'exact' ? 'Exact · source-supported' : 'Inferred'}</span><span>{edge.connection_type === 'exact' ? 'Confidence · source-supported' : `${humanize(edge.confidence_band)} confidence · ${Math.round(edge.confidence * 100)}%`}</span></p>
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
  <section class="evidence-references" aria-labelledby="aphis-evidence-heading">
    <h3 id="aphis-evidence-heading">APHIS evidence references</h3>
    <p class="explanation">Only typed references that passed this release’s source-record, privacy, and publication gates appear here. Report contents and source identifiers are not included.</p>
    {#if evidenceLoading}<p role="status">Loading APHIS references…</p>
    {:else if evidenceError}<p role="alert">APHIS references could not be loaded. <button type="button" onclick={() => void loadEvidenceReferences()}>Retry</button></p>
    {:else if !evidenceReferences.length}<p class="empty">No APHIS evidence references are approved in this release.</p>
    {:else}<ul>
      {#each evidenceReferences as reference (reference.reference_id)}
        <li>
          <span>{reference.evidence_type === 'annual_reports' ? `Annual report · FY${reference.event_period}` : `Inspection · ${reference.event_date}`}</span>
          <a href={reference.source_url} target="_blank" rel="noopener noreferrer">Open APHIS source</a>
          <span class="meta">Source {humanize(reference.source_id)} · exact source identifier</span>
        </li>
      {/each}
    </ul>
    {#if evidenceCursor}<button class="more" type="button" disabled={evidenceLoadingMore} onclick={() => void loadEvidenceReferences(evidenceCursor ?? undefined)}>{evidenceLoadingMore ? 'Loading…' : 'Load more APHIS references'}</button>{/if}
    {/if}
  </section>
</section>

<style>
  .connections{margin-top:1rem;padding-top:.8rem;border-top:1px solid #3c4640;color:#edf0e9;font:.82rem/1.45 system-ui,sans-serif}.connections h2{margin:0 0 .35rem;font:600 1rem/1.3 Georgia,serif}.explanation,.empty{margin:.35rem 0;color:#b9c3b7}.controls{display:flex;flex-wrap:wrap;gap:.55rem;margin:.6rem 0}.controls label{display:flex;align-items:center;gap:.35rem;color:#c6d0c5}.controls select{max-width:9rem;min-height:2rem;padding:.25rem .4rem;background:#202523;border:1px solid #59615c;color:#edf0e9;font:inherit}.connections ul{list-style:none;margin:.5rem 0;padding:0}.connections li{padding:.6rem 0;border-top:1px solid #303a33}.row-heading{display:flex;justify-content:space-between;gap:.65rem;align-items:baseline}.row-heading a,.connections a{color:#dce8d9;text-underline-offset:.2em}.relationship{color:#d0c7b3}.meta{display:flex;flex-wrap:wrap;gap:.25rem .8rem;margin:.2rem 0;color:#b9c3b7;font-size:.75rem;font-variant-numeric:tabular-nums}.connections details{margin-top:.25rem}.connections summary{width:fit-content;color:#c6d0c5;cursor:pointer;text-underline-offset:.2em}.connections dl{margin:.35rem 0}.connections dl div{display:grid;grid-template-columns:5.5rem minmax(0,1fr);gap:.5rem;padding:.12rem 0}.connections dt{color:#b9c3b7}.connections dd{margin:0;overflow-wrap:anywhere}.limitation{margin:.4rem 0;color:#c6d0c5}.connections button{min-height:2rem;padding:.25rem .45rem;background:#252f28;border:1px solid #657466;color:#edf0e9;font:inherit;cursor:pointer}.more{margin-top:.35rem}.connections a:focus-visible,.connections button:focus-visible,.connections select:focus-visible,.connections summary:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:34rem){.row-heading{align-items:flex-start;flex-direction:column;gap:.1rem}.connections dl div{grid-template-columns:1fr;gap:0}}
</style>
