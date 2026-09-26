<script lang="ts">
  import { onMount } from "svelte";
  import {
    createRealPreviewRepository,
    mapRealPreviewCandidate,
    RealPreviewError,
    type RealPreviewCandidate,
    type RealPreviewFacet,
  } from "../api/RealPreviewRepository";
  import type { LabRecord } from "../design-lab/contract";
  const repository = createRealPreviewRepository();
  type Status = "loading" | "ready" | "empty" | "error" | "unauthorized";
  // Continue using the API cursor until it is exhausted; the UI stays paginated.
  let query = $state("");
  let sourceId = $state<string | null>(null);
  let selectedId = $state<string | null>(null);
  type DatabaseRecord = LabRecord & Pick<RealPreviewCandidate, 'displayName' | 'activityLabel' | 'activitySource' | 'sourceName' | 'sourceRecordId' | 'sourceUrl' | 'sourceRecordUrl' | 'retrievedAt' | 'observedAt' | 'evidenceSummary'>;
  let records = $state<readonly DatabaseRecord[]>([]);
  let nextCursor = $state<string | null>(null);
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
  const treatment = (record: LabRecord) =>
    record.defaultMapScope === false
      ? `Outside the default map scope${record.mapScopeReason ? ` · ${record.mapScopeReason.replaceAll('_', ' ')}` : ''} · list/search only`
      : record.latitude === null || record.longitude === null
      ? "No map position · list/search only"
      : record.precision === "city"
        ? "Administrative city reference · approximate"
        : record.precision === "coarse"
          ? "City or postal reference · approximate"
          : record.precision === "exact"
            ? "Numeric source coordinate · pending review"
            : record.coordinatePrecision === "source-precision-unknown"
              ? "Approximate source coordinate · precision unknown"
              : "Approximate source coordinate · pending review";
  const statusText = (record: LabRecord) =>
    record.publicationStatus?.replaceAll("_", " ") ?? "Not supplied";
  const mapHref = (id = selectedId) => {
    const params = new URLSearchParams({
      f1a: "field",
      scenario: "default",
      ...mapContext,
    });
    if (query) params.set("q", query);
    if (sourceId) params.set("source", sourceId);
    if (id) params.set("selected", id);
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
      const page = await repository.list({
        query,
        sourceId,
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
  const noMap = $derived(
    records.filter(
      (record) => record.defaultMapScope === false || record.latitude === null || record.longitude === null,
    ).length,
  );
  const mapped = $derived(records.length - noMap);
  const selected = $derived(
    records.find((record) => record.id === selectedId) ?? null,
  );
  onMount(() => {
    syncHash();
    if (!records.length) void load(true);
    const controller = new AbortController();
    void repository
      .facets(controller.signal)
      .then((value) => {
        facets = value;
        facetsStatus = "ready";
      })
      .catch((cause) => {
        facetsStatus = classify(cause);
      });
    addEventListener("hashchange", syncHash);
    return () => {
      controller.abort();
      request?.abort();
      if (searchTimer) clearTimeout(searchTimer);
      removeEventListener("hashchange", syncHash);
    };
  });
</script>

<svelte:head><title>Until Every Cage — Database</title></svelte:head>
<div class="database-research">
  <header class="masthead">
    <a class="wordmark" href={mapHref()}
      ><img src={`${import.meta.env.BASE_URL}assets/icon.png`} alt="" />Until
      Every Cage</a
    >
    <nav aria-label="Primary">
      <a href={mapHref()}>Map</a><a aria-current="page" href="#/database"
        >Database</a
      >
    </nav>
    <p>PRIVATE DEVELOPMENT PREVIEW <span>·</span> NOT PUBLICATION-APPROVED</p>
  </header>
  <main aria-labelledby="database-title">
    <section class="intro">
      <div>
        <p class="eyebrow">DATABASE / PRIVATE PREVIEW</p>
        <h1 id="database-title">Research index</h1>
        <p>
          Search all accessible preview candidates—not just the current map view.
          Search names, activities, sources, cities, and postal codes across
          the private index. Records without map positions remain in these
          paginated results.
        </p>
      </div>
      <dl class="index-context">
        <div>
          <dt>Current source</dt>
          <dd>{sourceLabel(sourceId)}</dd>
        </div>
        <div>
          <dt>Loaded working set</dt>
          <dd>{records.length} records</dd>
        </div>
        <div>
          <dt>No-map in loaded records</dt>
          <dd>{noMap}</dd>
        </div>
      </dl>
    </section>
    <section class="index-shell" aria-label="Database search">
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
        <fieldset>
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
        <section
          class="precision-note"
          aria-labelledby="location-treatment-title"
        >
          <h2 id="location-treatment-title">Location treatment</h2>
          <p>Mapped in loaded records: {mapped}</p>
          <p>Not on the default map in loaded records: {noMap}</p>
          <small>Search covers safe name, activity, source, city, and postal fields. Evidence text is not searched.</small>
        </section>
      </aside>
      <section class="records" aria-live="polite">
        <header>
          <p>
            <strong
              >{status === "loading"
                ? "Loading index"
                : status === "empty"
                  ? "No matching records"
                  : `${records.length} loaded records`}</strong
            ><span>{query ? `Query: “${query}”` : "All accessible candidates"}</span>
          </p>
          <p class="quiet">
            Results retain source and location context across API pages.
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
                write({ query: "", sourceId: null, selectedId: null })}
              >Clear search and source</button
            >
          </div>{:else}<ol>
            {#each records as record (record.id)}<li
                class:selected={record.id === selectedId}
              >
                <button
                  type="button"
                  onclick={() => write({ selectedId: record.id })}
                  ><span class="record-name">{record.name}</span><span
                    class="record-place"
                    >{record.locality}, {record.country}</span
                  ><span
                    class:unmapped={record.defaultMapScope === false || record.latitude === null || record.longitude === null}
                    class="record-treatment">{treatment(record)}</span
                  ><span class="record-source"
                    >{record.sourceName ?? record.sourceId ?? "Source unavailable"}</span
                  ><span class="record-status">{statusText(record)}</span
                  ></button
                >
              </li>{/each}
          </ol>{/if}{#if status === "ready" && nextCursor}<button
            class="more"
            type="button"
            disabled={loadingMore}
            onclick={() => void load(false)}
          >{loadingMore ? "Loading next page…" : "Load next page · 100 records"}</button
          >{/if}
      </section>
      <aside class="selection" aria-label="Selected record">
        {#if selected}<p class="eyebrow">SELECTED PREVIEW CANDIDATE</p>
          <h2>{selected.name}</h2>
          <p>{selected.locality}, {selected.country}</p>
          <dl>
            <div>
              <dt>Candidate ID</dt>
              <dd>{selected.id}</dd>
            </div>
            <div>
              <dt>Source ID</dt>
              <dd>{selected.sourceName ?? selected.sourceId ?? "Not supplied by current preview API"}</dd>
            </div>
            <div>
              <dt>Facility name</dt>
              <dd>{selected.displayName ?? "Name unavailable"}</dd>
            </div>
            <div>
              <dt>Activity/category</dt>
              <dd>{selected.activityLabel ?? "Unavailable in current preview API"}{#if selected.activitySource}<span class="quiet"> · {selected.activitySource}</span>{/if}</dd>
            </div>
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
          {#if selected.defaultMapScope !== false && selected.latitude !== null && selected.longitude !== null}<a class="dossier-link" href={mapHref(selected.id)}>Open in map workspace <span>→</span></a>{/if}
          <p class="quiet">
            Fields not supplied by the current private-preview API remain unavailable.
          </p>{:else}<p class="eyebrow">SELECT A RECORD</p>
          <h2>Candidate data, with its limits.</h2>
          <p>
            Select a result to inspect the fields returned by the current
            private-preview API.
          </p>
          <p class="quiet">
            Missing names, classifications, source links, and evidence are never inferred.
          </p>{/if}
      </aside>
    </section>
  </main>
</div>

<style>
  .database-research {
    --ink: #edf0e9;
    --muted: #a9b0a9;
    --line: #3c4640;
    --panel: #151a17;
    min-height: 100dvh;
    background: #101412;
    color: var(--ink);
    font-family: ui-sans-serif, system-ui, sans-serif;
  }
  .database-research * {
    box-sizing: border-box;
  }
  .masthead {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 1.25rem;
    min-height: 4.8rem;
    padding: 0.75rem clamp(1rem, 3vw, 3.2rem);
    border-bottom: 1px solid var(--line);
    background: #141916;
  }
  .wordmark {
    display: flex;
    align-items: center;
    gap: 0.58rem;
    color: var(--ink);
    font:
      600 1rem Georgia,
      serif;
    text-decoration: none;
  }
  .wordmark img {
    width: 2rem;
    height: 2rem;
  }
  .masthead nav {
    display: flex;
    gap: 1.2rem;
    font-size: 0.77rem;
  }
  .masthead nav a {
    color: var(--muted);
    text-decoration: none;
  }
  .masthead nav a[aria-current] {
    color: var(--ink);
    text-decoration: underline;
    text-underline-offset: 0.35rem;
  }
  .masthead > p {
    justify-self: end;
    margin: 0;
    color: #bbc7b9;
    font:
      0.59rem ui-monospace,
      monospace;
    letter-spacing: 0.1em;
  }
  .masthead > p span {
    color: #687468;
  }
  main {
    max-width: 96rem;
    margin: 0 auto;
    padding: clamp(1.1rem, 3vw, 3.4rem);
  }
  .intro {
    display: flex;
    justify-content: space-between;
    gap: 3rem;
    padding: 0 0 2rem;
    border-bottom: 1px solid var(--line);
  }
  .intro > div {
    max-width: 44rem;
  }
  .eyebrow {
    margin: 0 0 0.45rem;
    color: #b9c7b8;
    font:
      0.6rem ui-monospace,
      monospace;
    letter-spacing: 0.13em;
  }
  .intro h1 {
    margin: 0;
    font:
      500 clamp(2.1rem, 5vw, 4rem) / 0.95 Georgia,
      serif;
  }
  .intro > div > p:last-child {
    max-width: 38rem;
    color: var(--muted);
    font-size: 0.86rem;
    line-height: 1.55;
  }
  .index-context {
    display: grid;
    grid-template-columns: repeat(3, minmax(6.5rem, 1fr));
    align-self: end;
    margin: 0;
    border-left: 1px solid var(--line);
  }
  .index-context div {
    padding: 0.25rem 0.8rem;
    border-right: 1px solid var(--line);
  }
  dt {
    color: var(--muted);
    font-size: 0.62rem;
  }
  dd {
    margin: 0.3rem 0 0;
    font-size: 0.76rem;
    line-height: 1.35;
  }
  .index-shell {
    display: grid;
    grid-template-columns: 14rem minmax(0, 1fr) 17rem;
    min-height: 34rem;
    border: 1px solid var(--line);
    border-top: 0;
  }
  .facets,
  .selection {
    padding: 1rem;
    background: var(--panel);
  }
  .facets {
    border-right: 1px solid var(--line);
  }
  .search-label,
  legend {
    display: block;
    margin-bottom: 0.4rem;
    color: var(--muted);
    font-size: 0.66rem;
  }
  .facets input[type="search"] {
    width: 100%;
    padding: 0.65rem;
    border: 1px solid #566159;
    background: #0e1210;
    color: var(--ink);
    font: inherit;
  }
  .facets fieldset {
    display: grid;
    gap: 0.52rem;
    margin: 1.2rem 0;
    padding: 0;
    border: 0;
  }
  .facets fieldset label {
    font-size: 0.72rem;
    line-height: 1.3;
  }
  .facets input[type="radio"] {
    accent-color: #c9d5c4;
  }
  .precision-note {
    margin-top: 1.4rem;
    padding-top: 0.8rem;
    border-top: 1px solid var(--line);
  }
  .precision-note h2,
  .selection h2 {
    margin: 0;
    font:
      600 1rem Georgia,
      serif;
  }
  .precision-note p {
    margin: 0.45rem 0;
    font-size: 0.73rem;
  }
  .precision-note small,
  .quiet {
    color: var(--muted);
    font-size: 0.66rem;
    line-height: 1.45;
  }
  .records {
    min-width: 0;
    background: #111613;
  }
  .records > header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.8rem 1rem;
    border-bottom: 1px solid var(--line);
  }
  .records > header p {
    margin: 0;
    font-size: 0.72rem;
  }
  .records > header span {
    display: block;
    margin-top: 0.18rem;
    color: var(--muted);
    font-size: 0.65rem;
  }
  .records ol {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .records li {
    border-bottom: 1px solid #2e3731;
  }
  .records li.selected {
    background: #1b251d;
    box-shadow: inset 2px 0 #b9c7b8;
  }
  .records li button {
    display: grid;
    grid-template-columns: 1.25fr 0.8fr 1.6fr 0.8fr 0.75fr;
    gap: 0.65rem;
    width: 100%;
    padding: 0.74rem 1rem;
    border: 0;
    color: inherit;
    background: transparent;
    text-align: left;
    cursor: pointer;
  }
  .records li button:hover {
    background: #18201a;
  }
  .record-name {
    font:
      600 0.76rem Georgia,
      serif;
  }
  .record-place,
  .record-treatment,
  .record-source,
  .record-status {
    color: var(--muted);
    font-size: 0.66rem;
    line-height: 1.35;
  }
  .record-treatment {
    color: #cbd5c8;
  }
  .record-treatment.unmapped {
    color: #decf9d;
  }
  .record-status {
    text-transform: capitalize;
  }
  .more,
  .state-card button {
    margin: 1rem;
    padding: 0.55rem 0.8rem;
    border: 1px solid #657064;
    background: #1e2820;
    color: var(--ink);
    font: 0.7rem system-ui;
    cursor: pointer;
  }
  .more:disabled {
    opacity: 0.6;
    cursor: wait;
  }
  .state-card {
    margin: 1rem;
    padding: 1rem;
    border: 1px solid #566159;
    background: #171d19;
    font-size: 0.77rem;
  }
  .state-card p {
    color: var(--muted);
    line-height: 1.45;
  }
  .state-card.error {
    border-color: #8b5c4e;
  }
  .selection {
    border-left: 1px solid var(--line);
  }
  .selection h2 {
    margin: 0.25rem 0 0.7rem;
    font-size: 1.15rem;
  }
  .selection > p:not(.eyebrow):not(.quiet) {
    color: var(--muted);
    font-size: 0.73rem;
    line-height: 1.5;
  }
  .selection dl {
    margin: 1rem 0;
  }
  .selection dl div {
    padding: 0.58rem 0;
    border-top: 1px solid var(--line);
  }
  .dossier-link {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.7rem;
    border: 1px solid #839281;
    color: var(--ink);
    background: #1d271f;
    font-size: 0.72rem;
    text-decoration: none;
  }
  .dossier-link span {
    font-size: 1rem;
    line-height: 0.7;
  }
  .selection .quiet {
    margin-top: 1rem;
  }
  @media (max-width: 62rem) {
    .index-shell {
      grid-template-columns: 13rem minmax(0, 1fr);
    }
    .selection {
      grid-column: 1/-1;
      border-top: 1px solid var(--line);
      border-left: 0;
    }
    .selection dl {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.6rem;
    }
    .selection dl div {
      border-top: 0;
    }
    .records li button {
      grid-template-columns: 1.2fr 0.8fr 1.3fr 0.75fr;
    }
    .record-status {
      display: none;
    }
  }
  @media (max-width: 43rem) {
    .masthead {
      grid-template-columns: 1fr auto;
    }
    .masthead > p {
      display: none;
    }
    main {
      padding: 1rem;
    }
    .intro {
      display: grid;
      gap: 1.2rem;
    }
    .index-context {
      align-self: auto;
    }
    .index-shell {
      display: block;
      border: 0;
    }
    .facets,
    .records,
    .selection {
      border: 1px solid var(--line);
    }
    .facets {
      border-bottom: 0;
    }
    .facets fieldset {
      grid-template-columns: 1fr 1fr;
    }
    .precision-note {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.3rem 0.8rem;
    }
    .precision-note h2,
    .precision-note small {
      grid-column: 1/-1;
    }
    .records li button {
      grid-template-columns: 1fr 1fr;
      padding: 0.75rem;
    }
    .record-treatment {
      grid-column: 1/-1;
    }
    .record-source {
      display: none;
    }
    .selection {
      border-top: 0;
    }
    .selection dl {
      grid-template-columns: 1fr;
    }
    .masthead nav {
      gap: 0.75rem;
    }
  }
</style>
