<script lang="ts">
  import { onMount } from "svelte";
  import {
    createRealPreviewRepository,
    mapRealPreviewCandidate,
    RealPreviewError,
    type RealPreviewCandidate,
    type RealPreviewFacet,
  } from "../api/RealPreviewRepository";
  import { TestReleaseRepository } from '../api/TestReleaseRepository';
  import type { LabRecord } from "../design-lab/contract";
  import { TAXONOMY_PRIMARY_KEYS, type TaxonomyPrimaryKey } from "../domain/taxonomy";
  import { CATEGORY_PRESENTATIONS } from "../features/locations/categoryPresentation";
  import RecordTable from './RecordTable.svelte';
  import ProjectFooter from './ProjectFooter.svelte';
  import PreviewMasthead from "./PreviewMasthead.svelte";
  const repository = createRealPreviewRepository();
  const candidateRepository = new TestReleaseRepository();
  const candidateMode = typeof document !== 'undefined' && document.querySelector<HTMLMetaElement>('meta[name="uec-local-data-mode"]')?.content === 'candidate-preview';
  type Status = "loading" | "ready" | "empty" | "error" | "unauthorized";
  // Continue using the API cursor until it is exhausted; the UI stays paginated.
  let query = $state("");
  let sourceId = $state<string | null>(null);
  let selectedCategories = $state<readonly TaxonomyPrimaryKey[]>([]);
  let selectedId = $state<string | null>(null);
  type DatabaseRecord = LabRecord & Partial<Pick<RealPreviewCandidate, 'displayName' | 'activityLabel' | 'activitySource' | 'sourceName' | 'sourceRecordId' | 'sourceUrl' | 'sourceRecordUrl' | 'retrievedAt' | 'observedAt' | 'evidenceSummary'>>;
  let records = $state<readonly DatabaseRecord[]>([]);
  let nextCursor = $state<string | null>(null);
  let totalCount = $state<number | null>(null);
  let candidateLabel = $state<string | null>(null);
  let candidateCountries = $state<readonly Readonly<{ value: string; count: number }>[]>([]);
  let candidateCategories = $state<readonly Readonly<{ value: string; count: number }>[]>([]);
  let candidateCountry = $state('');
  let candidateCategory = $state('');
  let status = $state<Status>("loading");
  let error = $state("");
  let loadingMore = $state(false);
  let facets = $state<readonly RealPreviewFacet[]>([]);
  let facetsStatus = $state<"loading" | "ready" | "error" | "unauthorized">(
    "loading",
  );
  let mapContext = $state<Record<string, string>>({});
  let request: AbortController | undefined;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  const sourceLabel = (value: string | null) => value ?? "All source feeds";
  const candidateRecord = (location: import('../domain/location').Location): DatabaseRecord => ({
    id: location.id, name: location.name, category: location.category, country: location.region, locality: location.region,
    precision: location.evidence?.displayPrecision ?? 'unmapped', latitude: location.lat, longitude: location.lon,
    ...(location.sourceId ? { sourceId: location.sourceId } : {}), sourceName: location.source,
    ...(location.evidence?.sourceUrl ? { sourceUrl: location.evidence.sourceUrl } : {}),
    ...(location.evidence?.retrievedAt ? { retrievedAt: location.evidence.retrievedAt } : {}),
    ...(location.evidence?.factualReviewStatus ? { factualReviewStatus: location.evidence.factualReviewStatus } : {}),
    ...(location.evidence?.privacyScreeningStatus ? { privacyScreeningStatus: location.evidence.privacyScreeningStatus } : {}),
    ...(location.evidence ? { projectApproval: location.evidence.projectApproval === 'approved' } : {}),
    ...(location.taxonomy ? { taxonomy: location.taxonomy } : {}),
  });
  const treatment = (record: LabRecord) =>
    record.sourceId === 'us.fsis' && record.coordinatePrecision === 'source-provided'
      ? 'Source-provided · precision unverified'
      : record.defaultMapScope === false
      ? 'Outside default map scope'
      : record.latitude === null || record.longitude === null
      ? "Unmapped"
      : record.precision === "city"
        ? "City-level approximation"
        : record.precision === "coarse"
          ? "City/postal approximation"
          : record.precision === "exact"
            ? "Source coordinate · awaiting review"
            : record.coordinatePrecision === "source-precision-unknown"
              ? "Approximate · precision unknown"
              : "Approximate · awaiting review";
  const statusText = (record: LabRecord) =>
    record.publicationStatus?.replaceAll("_", " ") ?? "Not supplied";
  const mapHref = (id = selectedId, focusSelected = false) => {
    const params = new URLSearchParams({
      f1a: "field",
      scenario: "default",
      ...mapContext,
    });
    // Database queries may contain addresses. Carry only the record ID and map
    // camera preferences into a shareable map URL.
    if (sourceId) params.set("source", sourceId);
    if (id) params.set("selected", id);
    if (id && focusSelected) params.set("focus", "selected");
    return `#/map?${params}`;
  };
  const write = (changes: {
    query?: string;
    sourceId?: string | null;
    selectedId?: string | null;
  }) => {
    const params = new URLSearchParams(mapContext);
    const nextQuery = changes.query ?? query;
    const nextSource =
      changes.sourceId === undefined ? sourceId : changes.sourceId;
    const nextSelected =
      changes.selectedId === undefined ? selectedId : changes.selectedId;
    if (nextQuery) params.set("q", nextQuery);
    if (nextSource) params.set("source", nextSource);
    if (nextSelected) params.set("selected", nextSelected);
    history.replaceState(
      null,
      "",
      `#/database${params.size ? `?${params}` : ""}`,
    );
    syncHash();
  };
  const classify = (value: unknown): "error" | "unauthorized" =>
    value instanceof RealPreviewError && value.kind === "unauthorized"
      ? "unauthorized"
      : "error";
  function syncHash() {
    const params = new URLSearchParams(location.hash.split("?")[1] ?? "");
    const nextQuery = params.get("q") ?? "";
    const value = params.get("source");
    const nextSource =
      value && /^[A-Za-z0-9.-]{1,80}$/.test(value) ? value : null;
    const numeric = (name: string, min: number, max: number) => {
      const raw = params.get(name);
      const parsed = raw === null ? NaN : Number(raw);
      return Number.isFinite(parsed) && parsed >= min && parsed <= max
        ? raw
        : null;
    };
    const nextContext: Record<string, string> = {};
    for (const [name, min, max] of [
      ["lat", -90, 90],
      ["lon", -180, 180],
      ["z", 1, 18],
    ] as const) {
      const raw = numeric(name, min, max);
      if (raw !== null) nextContext[name] = raw;
    }
    if (params.get("list") === "closed") nextContext.list = "closed";
    if (params.get("basemap") === "satellite")
      nextContext.basemap = "satellite";
    mapContext = nextContext;
    selectedId = params.get("selected");
    if (nextQuery !== query || nextSource !== sourceId) {
      query = nextQuery;
      sourceId = nextSource;
      void load(true);
    }
  }
  async function load(reset: boolean) {
    request?.abort();
    const controller = new AbortController();
    request = controller;
    if (reset) {
      status = "loading";
      error = "";
      records = [];
      nextCursor = null;
    } else loadingMore = true;
    try {
      if (candidateMode) {
        const page = await candidateRepository.list({ q: query, ...(candidateCountry ? { countryCode: candidateCountry } : {}), ...(candidateCategory ? { category: candidateCategory } : {}), cursor: reset ? null : nextCursor, limit: 100, signal: controller.signal });
        if (controller.signal.aborted) return;
        const incoming = page.locations.map(candidateRecord);
        records = [...new Map((reset ? incoming : [...records, ...incoming]).map(record => [record.id, record])).values()];
        nextCursor = page.nextCursor;
        totalCount = page.totalCount;
        candidateLabel = page.previewLabel;
        status = records.length ? 'ready' : 'empty';
        return;
      }
      const page = await repository.list({
        query,
        sourceId,
        categoryKeys: selectedCategories,
        cursor: reset ? null : nextCursor,
        limit: 100,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const incoming = page.records.map(mapRealPreviewCandidate);
      records = [
        ...new Map(
          (reset ? incoming : [...records, ...incoming]).map((record) => [
            record.id,
            record,
          ]),
        ).values(),
      ];
      nextCursor = page.nextCursor;
      status = records.length ? "ready" : "empty";
    } catch (cause) {
      if (controller.signal.aborted) return;
      status = classify(cause);
      error =
        cause instanceof Error
          ? cause.message
          : "The private preview index could not be loaded.";
    } finally {
      if (request === controller) loadingMore = false;
    }
  }
  function onSearch(value: string) {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(
      () => write({ query: value, selectedId: null }),
      180,
    );
  }
  const sources = $derived(
    [...new Set(facets.map((facet) => facet.sourceId))].sort(),
  );
  function toggleCategory(key: TaxonomyPrimaryKey, checked: boolean) {
    selectedCategories = checked
      ? [...new Set([...selectedCategories, key])]
      : selectedCategories.filter(value => value !== key);
    selectedId = null; void load(true);
  }
  function clearFilters() {
    selectedCategories = []; selectedId = null;
    if (searchTimer) clearTimeout(searchTimer);
    const changed = !!query || sourceId !== null;
    write({ query: '', sourceId: null, selectedId: null });
    if (!changed) void load(true);
  }
  const noMap = $derived(
    records.filter(
      (record) => record.defaultMapScope === false || record.latitude === null || record.longitude === null,
    ).length,
  );
  const selected = $derived(
    records.find((record) => record.id === selectedId) ?? null,
  );
  onMount(() => {
    syncHash();
    if (!records.length) void load(true);
    const controller = new AbortController();
    addEventListener("hashchange", syncHash);
    if (candidateMode) {
      void candidateRepository.facets(controller.signal).then(value => { candidateCountries = value.countries; candidateCategories = value.categories; facetsStatus = 'ready'; }).catch(cause => { facetsStatus = classify(cause); });
      return () => { controller.abort(); request?.abort(); if (searchTimer) clearTimeout(searchTimer); removeEventListener("hashchange", syncHash); };
    }
    void repository
      .facets(controller.signal)
      .then((value) => {
        facets = value;
        facetsStatus = "ready";
      })
      .catch((cause) => {
        facetsStatus = classify(cause);
      });
    return () => {
      controller.abort();
      request?.abort();
      if (searchTimer) clearTimeout(searchTimer);
      removeEventListener("hashchange", syncHash);
    };
  });
</script>

<svelte:head><title>Until Every Cage: Database</title></svelte:head>
<div class="database-research">
  <PreviewMasthead privateTools current="database" mapHref={mapHref()} databaseHref="#/database" />
  <main aria-labelledby="database-title">
    <section class="intro">
      <div>
        <h1 id="database-title">Browse records</h1>
        <p>{candidateMode && candidateLabel ? candidateLabel : 'Search private preview records by name, activity, source, or place. This data is not publication-approved.'}</p>
      </div>
      <dl class="index-context">
        <div>
          <dt>Current source</dt>
          <dd>{sourceLabel(sourceId)}</dd>
        </div>
        <div>
          <dt>Loaded records</dt>
          <dd>{candidateMode && totalCount !== null ? `${totalCount} total` : `${records.length} ${records.length === 1 ? 'record' : 'records'}`}</dd>
        </div>
        <div>
          <dt>No-map in loaded records</dt>
          <dd>{noMap}</dd>
        </div>
      </dl>
    </section>
    <section class="index-shell" class:has-selection={!!selected} aria-label="Database search">
      <aside class="facets" aria-label="Research filters">
        <label class="search-label" for="database-query"
          >Search records</label
        ><input
          id="database-query"
          type="search"
          placeholder="Name, activity, source, or place…"
          value={query}
          oninput={(event) => onSearch(event.currentTarget.value)}
        />
        {#if candidateMode}<fieldset><legend>Country</legend><select value={candidateCountry} onchange={(event) => { candidateCountry = event.currentTarget.value; void load(true); }}><option value="">All countries</option>{#each candidateCountries as facet (facet.value)}<option value={facet.value}>{facet.value} ({facet.count})</option>{/each}</select></fieldset>
        <fieldset><legend>Activity category</legend><select value={candidateCategory} onchange={(event) => { candidateCategory = event.currentTarget.value; void load(true); }}><option value="">All categories</option>{#each candidateCategories as facet (facet.value)}<option value={facet.value}>{facet.value.replaceAll('_', ' ')} ({facet.count})</option>{/each}</select></fieldset>
        {:else}<fieldset>
          <legend>Source feed</legend>{#if facetsStatus === "loading"}<p
              class="quiet"
            >
              Loading source facets…
            </p>{:else if facetsStatus === "error" || facetsStatus === "unauthorized"}<p
              class="quiet"
              role="alert"
            >
              Source facets unavailable. Search remains available.
            </p>{:else}<label
              ><input
                type="radio"
                name="database-source"
                checked={sourceId === null}
                onchange={() => write({ sourceId: null, selectedId: null })}
              /> All source feeds</label
            >{#each sources as source}<label
                ><input
                  type="radio"
                  name="database-source"
                  checked={sourceId === source}
                  onchange={() => write({ sourceId: source, selectedId: null })}
                />
                {source}</label
              >{/each}{/if}
        </fieldset>
        <fieldset>
          <legend>Activity category</legend>
          {#each TAXONOMY_PRIMARY_KEYS.filter(key => key !== 'unclassified') as key (key)}
            <label><input type="checkbox" checked={selectedCategories.includes(key)} onchange={(event) => toggleCategory(key, event.currentTarget.checked)} />{CATEGORY_PRESENTATIONS[key].label}</label>
          {/each}

        </fieldset>{/if}
        {#if !candidateMode && (query || sourceId || selectedCategories.length)}<div class="active-filters" aria-label="Selected filters">{#if query}<button type="button" onclick={() => write({ query: '', selectedId: null })}>Search: {query} ×</button>{/if}{#if sourceId}<button type="button" onclick={() => write({ sourceId: null, selectedId: null })}>{sourceId} ×</button>{/if}{#each selectedCategories as key}<button type="button" onclick={() => toggleCategory(key, false)}>{CATEGORY_PRESENTATIONS[key].label} ×</button>{/each}<button type="button" onclick={clearFilters}>Clear filters</button></div>{/if}
      </aside>
      <section class="records" aria-live="polite">
        <header>
          <p>
            <strong
              >{status === "loading"
                ? "Loading index"
                : status === "empty"
                  ? "No matching records"
                  : candidateMode && totalCount !== null ? `${totalCount} candidate ${totalCount === 1 ? 'record' : 'records'}` : `${records.length} ${records.length === 1 ? 'record' : 'records'} loaded`}</strong
            ><span>{candidateMode ? 'Configured candidate release' : query ? `Query: “${query}”` : "All accessible candidates"}</span>
          </p>
          <p class="quiet">
            {nextCursor ? "More records available." : "End of results."}
          </p>
        </header>
        {#if status === "loading"}<div class="state-card" role="status">
            Loading private-preview records…
          </div>{:else if status === "error" || status === "unauthorized"}<div
            class="state-card error"
            role="alert"
          >
            <strong
              >{status === "unauthorized"
                ? "Preview authentication unavailable"
                : "Index unavailable"}</strong
            >
            <p>{error}</p>
            <button type="button" onclick={() => void load(true)}>Retry</button>
          </div>{:else if status === "empty"}<div class="state-card">
            <strong>No records match this search.</strong>
            <p>
              Try another term or select a source feed. Records
              without map positions remain listed when the API returns them.
            </p>
            <button
              type="button"
              onclick={() =>
                clearFilters()}
              >Clear filters</button
            >
          </div>{:else}<RecordTable records={records.map(record => ({ id: record.id, name: record.name, activity: record.taxonomy?.leafActivities.map(activity => activity.label).join(' · ') || record.activityLabel || record.category, place: `${record.locality}, ${record.country}`, source: record.sourceName ?? record.sourceId ?? 'Unavailable', precision: treatment(record) }))} {selectedId} onselect={id => write({ selectedId: id })} />{/if}{#if status === "ready" && nextCursor}<button
            class="more"
            type="button"
            disabled={loadingMore}
            onclick={() => void load(false)}
          >{loadingMore ? "Loading next page…" : "Load more"}</button
          >{/if}
      </section>
      {#if selected}<aside class="selection" aria-label="Selected record"><button class="close-selection" type="button" onclick={() => write({ selectedId: null })}>Close details</button>
          <h2>{selected.name}</h2>
          <p>{selected.locality}, {selected.country}</p>
          <dl>
            <div>
              <dt>Record ID</dt>
              <dd>{selected.id}</dd>
            </div>
            <div>
              <dt>Source ID</dt>
              <dd>{selected.sourceName ?? selected.sourceId ?? "Not supplied by current preview API"}</dd>
            </div>
            <div>
              <dt>Facility name</dt>
              <dd>{selected.displayName ?? "Name not shown — privacy review pending"}</dd>
            </div>
            <div>
              <dt>Activity/category</dt>
              <dd>{selected.taxonomy?.leafActivities.map(activity => activity.label).join(' · ') || selected.activityLabel || "Unavailable in current preview API"}{#if selected.activitySource}<span class="quiet"> · {selected.activitySource}</span>{/if}</dd>
            </div>
            {#if selected.taxonomy}
              <div><dt>Primary categories</dt><dd>{selected.taxonomy.primaryCategories.map(key => CATEGORY_PRESENTATIONS[key].label).join(' · ')}</dd></div>
              <div><dt>Classification provenance</dt><dd>{#each selected.taxonomy.assignments as assignment, index (`${assignment.primaryKey}:${assignment.leafKey ?? ''}:${index}`)}<span class="taxonomy-assignment">{assignment.sourceLabel ?? assignment.sourceCode ?? selected.sourceName ?? selected.sourceId} · {assignment.method} · {assignment.status} · {assignment.taxonomyVersion}</span>{/each}<span class="quiet">Taxonomy {selected.taxonomy.taxonomyVersion}</span></dd></div>
            {/if}
            <div>
              <dt>Source record URL</dt>
              <dd>{#if selected.sourceRecordUrl}<a href={selected.sourceRecordUrl} target="_blank" rel="noopener noreferrer">Open source record</a>{:else if selected.sourceUrl}<a href={selected.sourceUrl} target="_blank" rel="noopener noreferrer">Open source</a>{:else}Unavailable in current preview API{/if}{#if selected.sourceRecordId}<br /><span class="quiet">Source record: {selected.sourceRecordId}</span>{/if}</dd>
            </div>
            <div>
              <dt>Evidence and timestamps</dt>
              <dd>{selected.evidenceSummary ?? "Unavailable in current preview API"}{#if selected.retrievedAt}<br /><span class="quiet">Retrieved {selected.retrievedAt}</span>{/if}{#if selected.observedAt}<br /><span class="quiet">Observed {selected.observedAt}</span>{/if}</dd>
            </div>
            <div>
              <dt>Location</dt>
              <dd>{treatment(selected)}</dd>
            </div>
            <div>
              <dt>Publication</dt>
              <dd>{statusText(selected)}</dd>
            </div>
          </dl>
          <a class="dossier-link" href={`#/records/${encodeURIComponent(selected.id)}`}>Open full record <span>→</span></a>
          {#if selected.defaultMapScope !== false && selected.latitude !== null && selected.longitude !== null}<a class="dossier-link" href={mapHref(selected.id, true)}>Open on map <span>→</span></a>{/if}
          <p class="quiet">
            Fields not supplied by the current private-preview API remain unavailable.
          </p>
      </aside>{/if}
    </section>
  </main>
  <ProjectFooter returnMapHref={mapHref()} />
</div>

<style>
  .database-research{--ink:#edf0e9;--muted:#b9c3b7;--line:#3c4640;min-height:100dvh;background:#171a18;color:var(--ink);font:.9rem/1.5 system-ui,sans-serif}.database-research *{box-sizing:border-box}main{max-width:96rem;margin:auto;padding:1.5rem}.intro{display:flex;flex-wrap:wrap;justify-content:space-between;gap:1rem;padding-bottom:1rem;border-bottom:1px solid var(--line)}.intro>div{max-width:40rem}h1{margin:0 0 .75rem;font:500 2rem/1.15 Georgia,serif}.intro p{margin:0;color:var(--muted)}.index-context{display:flex;flex-wrap:wrap;gap:.6rem 1.5rem;margin:0;align-self:end}dt{color:var(--muted);font-size:.8rem}dd{margin:.2rem 0 0;font-size:.88rem;overflow-wrap:anywhere}.index-shell{display:grid;grid-template-columns:13rem minmax(0,1fr);border-bottom:1px solid var(--line)}.index-shell.has-selection{grid-template-columns:13rem minmax(0,1fr) 19rem}.facets{padding:1rem 1rem 1rem 0;border-right:1px solid var(--line)}.search-label,legend{display:block;margin-bottom:.4rem;font-size:.86rem;font-weight:600}.facets input[type=search]{width:100%;padding:.55rem;border:1px solid #59615c;background:#202523;color:var(--ink);font:inherit}.facets fieldset{display:grid;gap:.4rem;padding:0;border:0;margin:1rem 0}.facets fieldset label{font-size:.85rem}.facets input{accent-color:#c9d5c4}.active-filters{display:flex;flex-wrap:wrap;gap:.4rem}.active-filters button,.close-selection,.more,.state-card button{min-height:2rem;padding:.35rem .55rem;border:1px solid #657466;background:#252f28;color:var(--ink);font:.85rem system-ui;cursor:pointer}.records{min-width:0}.records>header{display:flex;flex-wrap:wrap;justify-content:space-between;gap:.5rem;padding:.85rem .75rem;border-bottom:1px solid var(--line)}.records>header p{margin:0}.records>header span{display:block;color:var(--muted);font-size:.82rem}.quiet{color:var(--muted);font-size:.82rem}.more{margin:1rem}.state-card{margin:1rem;font-size:.9rem}.state-card p{color:var(--muted)}.selection{min-width:0;padding:1rem;border-left:1px solid var(--line)}.selection h2{margin:.75rem 0 .5rem;font-size:1.15rem}.selection p{font-size:.9rem}.selection dl div{padding:.5rem 0;border-top:1px solid var(--line)}.taxonomy-assignment{display:block}.dossier-link{display:block;margin:.6rem 0;color:#dce8d9;text-underline-offset:.2em}.dossier-link span{float:right}button:focus-visible,input:focus-visible,a:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:72rem){.index-shell.has-selection{grid-template-columns:13rem minmax(0,1fr)}.selection{grid-column:1/-1;border-left:0;border-top:1px solid var(--line)}}@media(max-width:43rem){main{padding:1.5rem 1rem}h1{font-size:1.75rem}.index-shell,.index-shell.has-selection{display:block}.facets{border-right:0;border-bottom:1px solid var(--line);padding:1rem 0}.facets fieldset{grid-template-columns:repeat(2,minmax(0,1fr))}.index-context{font-size:.82rem}.selection{padding:1rem 0}}
</style>
