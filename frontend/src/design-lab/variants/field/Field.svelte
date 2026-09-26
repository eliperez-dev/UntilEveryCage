<script lang="ts">
  import type {
    DirectionViewProps,
    LabRecord,
    MapDiagnostics,
    Precision,
  } from "../../contract";
  import type { RealPreviewFacet } from "../../../api/RealPreviewRepository";
  import MapSurface from "../../components/MapSurface.svelte";
  import RecordList from "../../components/RecordList.svelte";
  import RecordDetail from "../../../app/RecordDetail.svelte";
  let {
    state,
    records,
    mapRecords,
    mode = "synthetic",
    dataStatus = "ready",
    dataError = "",
    mapStatus = "idle",
    mapError = "",
    mapTruncated = false,
    mapDiagnostics,
    useMvtMap = false,
    onMapTiming,
    detailRecord = null,
    detailStatus = "ready",
    detailError = "",
    nextCursor = null,
    pageLoading = false,
    onLoadMore,
    onMapReference,
    aggregateMemberRecords = [],
    aggregateNextCursor = null,
    aggregateLoading = false,
    aggregateError = "",
    onLoadMoreAggregate,
    onViewportBounds,
    facets = [],
    facetsStatus = "loading",
    dispatch,
  }: DirectionViewProps & {
    mapDiagnostics?: MapDiagnostics;
    facets?: readonly RealPreviewFacet[];
    facetsStatus?: "loading" | "ready" | "error" | "unauthorized";
  } = $props();
  const categories = [
    "Poultry",
    "Pig",
    "Dairy",
    "Processing",
    "Laboratory",
    "Aquaculture",
  ];
  const precisions: readonly Precision[] = [
    "exact",
    "city",
    "coarse",
    "unmapped",
  ];
  const mapRows = $derived(mapRecords ?? records);
  const recordPool = $derived([
    ...new Map(
      [...records, ...mapRows, ...aggregateMemberRecords].map((record) => [
        record.id,
        record,
      ]),
    ).values(),
  ]);
  const selected = $derived(
    detailRecord ??
      recordPool.find((record) => record.id === state.selectedId) ??
      null,
  );
  const aggregateRecords = $derived(
    state.aggregateMemberIds === null
      ? records
      : recordPool.filter((record) =>
          state.aggregateMemberIds!.includes(record.id),
        ),
  );
  const aggregateOpen = $derived(state.aggregateMemberIds !== null);
  const aggregateRequestedCount = $derived(
    state.aggregateMemberIds?.length ?? 0,
  );
  const aggregateContext = $derived(aggregateContextFor(aggregateRecords));
  const mapped = $derived(
    mapRows.filter(
      (record) => record.latitude !== null && record.longitude !== null,
    ),
  );
  const resultCount = $derived(aggregateRecords.length);
  const active = $derived(
    mode === "synthetic"
      ? state.filters.categories.length + state.filters.precisions.length
      : 0,
  );
  const v1Logo = `${import.meta.env.BASE_URL}assets/icon.png`;
  const precisionLabel = (record: LabRecord) =>
    mode === "real-preview"
      ? record.precision === "city"
        ? "Approximate city location · not a facility point"
        : record.precision === "exact"
          ? "Numeric source coordinate · pending review"
          : record.precision === "approximate" &&
              record.coordinatePrecision === "source-precision-unknown"
            ? "Approximate source coordinate · precision unknown"
            : record.precision === "approximate"
              ? "Approximate source coordinate · pending review"
              : record.precision === "coarse"
                ? "City or postal · no approved map geometry"
                : "Unmapped · list only"
      : `${record.precision} precision`;
  function category(value: string, checked: boolean) {
    dispatch({
      type: "filters",
      value: {
        ...state.filters,
        categories: checked
          ? [...state.filters.categories, value]
          : state.filters.categories.filter((item) => item !== value),
      },
    });
  }
  function precision(value: Precision, checked: boolean) {
    dispatch({
      type: "filters",
      value: {
        ...state.filters,
        precisions: checked
          ? [...state.filters.precisions, value]
          : state.filters.precisions.filter((item) => item !== value),
      },
    });
  }
  const sources = $derived(
    [...new Set(facets.map((facet) => facet.sourceId))].sort(),
  );
  // No reviewed relationship projection exists in the preview API yet. Keep
  // the disclosure, without an unreachable loading/empty/error state machine.
  const relationshipUnavailableReason =
    "The private-preview relationship projection has not been supplied for this record.";
  function aggregateContextFor(items: readonly LabRecord[]) {
    const mostFrequent = (values: readonly string[]) => {
      const counts = new Map<string, number>();
      for (const value of values) {
        if (value.trim()) counts.set(value, (counts.get(value) ?? 0) + 1);
      }
      return (
        [...counts].sort(
          (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
        )[0]?.[0] ?? null
      );
    };
    const locality = mostFrequent(items.map((item) => item.locality));
    const country = mostFrequent(items.map((item) => item.country));
    const sources = [
      ...new Set(
        items.flatMap((item) => (item.sourceId ? [item.sourceId] : [])),
      ),
    ].sort();
    const precision = new Set(items.map((item) => item.precision));
    const treatment =
      precision.size === 1 && precision.has("city")
        ? "Administrative city reference · approximate, not a facility point"
        : precision.size === 1 && precision.has("coarse")
          ? "Coarse area reference · no approved facility geometry"
          : "Approximate location reference · not a facility pin";
    return {
      locality,
      place:
        [locality, country].filter(Boolean).join(", ") ||
        "Approximate area reference",
      treatment,
      sourceText:
        sources.length === 0
          ? "Source context unavailable"
          : sources.length === 1
            ? sources[0]
            : `${sources.length} source feeds`,
    };
  }
  function closeOverlay() {
    if (state.selectedId) {
      dispatch({ type: "select", value: null });
      return;
    }
    if (aggregateOpen) {
      dispatch({ type: "aggregate", value: null });
      return;
    }
    if (state.listOpen) dispatch({ type: "list", value: false });
  }
  function onKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeOverlay();
    }
  }
  function browseAggregate() {
    if (!aggregateContext.locality) return;
    dispatch({ type: "aggregate", value: null });
    dispatch({ type: "query", value: aggregateContext.locality });
    dispatch({ type: "list", value: true });
  }
  const databaseHref = $derived(
    (() => {
      const q = new URLSearchParams();
      if (state.query) q.set("q", state.query);
      if (state.sourceId) q.set("source", state.sourceId);
      if (state.selectedId) q.set("selected", state.selectedId);
      q.set("lat", String(state.viewport.centerLat));
      q.set("lon", String(state.viewport.centerLon));
      q.set("z", String(state.viewport.zoom));
      if (!state.listOpen) q.set("list", "closed");
      if (state.basemap === "satellite") q.set("basemap", "satellite");
      return `#/database?${q}`;
    })(),
  );
</script>

<svelte:window onkeydown={onKeydown} />
<section class="field-view">
  <header class="spine">
    <a
      class="brand"
      href="#/map?f1a=field"
      aria-label="Until Every Cage map home"
      ><img src={v1Logo} alt="" /><span>Until Every Cage</span></a
    >
    <form
      class="search"
      role="search"
      onsubmit={(event) => event.preventDefault()}
    >
      <label for="field-search">Search across preview records</label><input
        id="field-search"
        type="search"
        placeholder="Name, activity, source, or place"
        value={state.query}
        oninput={(event) =>
          dispatch({ type: "query", value: event.currentTarget.value })}
      />
    </form>
    <details class="filters">
      <summary
        >Filters {#if state.sourceId}<b>1</b>{:else if active}<b>{active}</b
          >{/if}</summary
      >
      <div class="filter-sheet">
        <strong>Refine results</strong>{#if mode === "real-preview"}<fieldset
            class="source-filter"
          >
            <legend>Source</legend>{#if facetsStatus === "loading"}<small
                >Loading sources…</small
              >{:else if facetsStatus === "error" || facetsStatus === "unauthorized"}<small
                role="alert"
                >Sources unavailable. Search remains available.</small
              >{:else}<label
                ><input
                  type="radio"
                  name="source"
                  checked={state.sourceId === null}
                  onchange={() => dispatch({ type: "source", value: null })}
                />All sources</label
              >{#each sources as value}<label
                  ><input
                    type="radio"
                    name="source"
                    checked={state.sourceId === value}
                    onchange={() => dispatch({ type: "source", value })}
                  />{value}</label
                >{/each}{/if}
          </fieldset>{:else}<p class="category-key">
            <i class="poultry"></i>Poultry <i class="pig"></i>Pig
            <i class="dairy"></i>Dairy <i class="processing"></i>Processing
            <i class="laboratory"></i>Lab <i class="aquaculture"></i>Aquaculture
          </p>
          <fieldset>
            <legend>Category</legend>{#each categories as value}<label
                ><input
                  type="checkbox"
                  checked={state.filters.categories.includes(value)}
                  onchange={(event) =>
                    category(value, event.currentTarget.checked)}
                />{value}</label
              >{/each}
          </fieldset>
          <fieldset>
            <legend>Location precision</legend>{#each precisions as value}<label
                ><input
                  type="checkbox"
                  checked={state.filters.precisions.includes(value)}
                  onchange={(event) =>
                    precision(value, event.currentTarget.checked)}
                />{value}</label
              >{/each}
          </fieldset>{/if}<button
          type="button"
          onclick={() =>
            mode === "real-preview"
              ? dispatch({ type: "source", value: null })
              : dispatch({ type: "reset-filters" })}>Clear filters</button
        >
      </div>
    </details>
  </header>
  <section class="map-stage" aria-label="Investigative map field">
    {#if mode === "synthetic" && state.scenario === "loading"}<div class="status" role="status">
        Loading records…
      </div>{:else if mode === "synthetic" && state.scenario === "error"}<div
        class="status"
        role="alert"
      >
        Records unavailable. No live fallback was attempted.
      </div>{:else}<MapSurface
        records={mapped}
        {state}
        {mode}
        {mapStatus}
        {mapError}
        {mapTruncated}
        {mapDiagnostics}
        {useMvtMap}
        referenceLoading={aggregateLoading}
        onmaptiming={(timing) => onMapTiming?.(timing)}
        onselect={(id) => dispatch({ type: "select", value: id })}
        onaggregate={(ids) => dispatch({ type: "aggregate", value: ids })}
        onreference={(key) => onMapReference?.(key)}
        onbasemap={(value) => dispatch({ type: "basemap", value })}
        onviewport={(value) => dispatch({ type: "viewport", value })}
        onbounds={(bounds) => onViewportBounds?.(bounds)}
      />{/if}
    {#if mode === "real-preview" && dataStatus === "loading"}<div
        class="status"
        role="status"
      >
        Loading search results…
      </div>{/if}
    {#if (mode === "synthetic" && (state.scenario === "empty" || (state.scenario !== "loading" && state.scenario !== "error" && records.length === 0))) || (mode === "real-preview" && dataStatus === "empty")}<div
        class="status"
        role="status"
      >
        No records match this search and these filters.
      </div>{/if}
    {#if mode === "real-preview" && dataStatus === "error"}<div
        class="status"
        role="alert"
      >
        {dataError}
      </div>{:else if mode === "real-preview" && dataStatus === "unauthorized"}<div
        class="status"
        role="alert"
      >
        {dataError}
      </div>{/if}
    <button
      class="results-toggle"
      type="button"
      aria-expanded={state.listOpen}
      aria-controls="field-record-list"
      onclick={() => dispatch({ type: "list", value: !state.listOpen })}
      >Results <b>{resultCount}</b></button
    >
    <a class="database-link" href={databaseHref}>Database</a>
    {#if state.listOpen && !selected}<aside
        class="results"
        id="field-record-list"
        aria-label={aggregateOpen
          ? "Aggregate member records"
          : "Synchronized results"}
      >
        <header>
          <strong
            >{aggregateOpen ? "Members" : "Results"}
            <span>{resultCount}</span></strong
          ><button
            type="button"
            aria-label="Close results"
            onclick={() => dispatch({ type: "list", value: false })}>×</button
          >
        </header>
        {#if aggregateOpen}<div class="member-context">
            <strong>{aggregateContext.place}</strong><span
              >{aggregateContext.treatment}</span
            ><small>Source context: {aggregateContext.sourceText}</small>
          </div>
          <p class="member-disclosure" role="status">
            Showing {resultCount} loaded member {resultCount === 1
              ? "record"
              : "records"} from this map reference. Members remain private-preview
            records.
          </p>{/if}<RecordList
          records={aggregateRecords}
          selectedId={state.selectedId}
          onselect={(id) => dispatch({ type: "select", value: id })}
        />{#if mode === "real-preview" && nextCursor && !aggregateOpen}<button
            type="button"
            disabled={pageLoading}
            style="width:calc(100% - 1rem);min-height:2.2rem;margin:.35rem .5rem .5rem;border:1px solid #69716a;color:#f1efe8;background:#171a18;font:.72rem system-ui;cursor:pointer"
            onclick={() => onLoadMore?.()}
            >{pageLoading ? "Loading…" : "Load more records"}</button
          >{:else if mode === "real-preview" && aggregateOpen && aggregateNextCursor}<button
            type="button"
            disabled={aggregateLoading}
            style="width:calc(100% - 1rem);min-height:2.2rem;margin:.35rem .5rem .5rem;border:1px solid #69716a;color:#f1efe8;background:#171a18;font:.72rem system-ui;cursor:pointer"
            onclick={() => onLoadMoreAggregate?.()}
            >{aggregateLoading
              ? "Loading members…"
              : "Load more members"}</button
          >{/if}{#if aggregateOpen && aggregateError}<p
            role="alert"
            style="margin:.5rem;color:#f1c7b8;font-size:.72rem"
          >
            {aggregateError}
          </p>{:else if mode === "real-preview" && (dataStatus === "unauthorized" || dataStatus === "error")}<p
            role="alert"
            style="margin:.5rem;color:#f1c7b8;font-size:.72rem"
          >
            {dataError}
          </p>{/if}
      </aside>{/if}
    {#if state.selectedId && mode === "real-preview" && detailStatus === "loading"}<aside
        class="reading-sheet"
        role="status"
      >
        Loading record evidence…
      </aside>{:else if state.selectedId && mode === "real-preview" && (detailStatus === "error" || detailStatus === "unauthorized")}<aside
        class="reading-sheet"
        role="alert"
      >
        <button
          type="button"
          class="close"
          aria-label="Close record detail"
          onclick={() => dispatch({ type: "select", value: null })}>×</button
        >{detailError}
      </aside>{:else if selected}<aside class="reading-sheet dossier" aria-label="Record evidence">
        {#if aggregateOpen}<button type="button" class="back" onclick={() => dispatch({ type: "select", value: null })}>← Members</button>{/if}
        <a class="full-record" href={`#/records/${encodeURIComponent(selected.id)}`}>Open full record</a>
        <RecordDetail record={selected} presentation="rail" onclose={() => dispatch({ type: "select", value: null })} />
        <section
          class="connections-evidence"
          aria-labelledby="connections-title"
        >
          <p class="eyebrow">EVIDENCE CONNECTIONS</p>
          <h3 id="connections-title">Connections</h3>
          <p>{relationshipUnavailableReason}</p>
          <p class="connection-disclosure">
            When supplied, this view will show only authorized, mappable
            endpoints. Relationship type, confidence, uncertainty, and
            contradictory evidence will remain disclosed per connection.
          </p>
        </section>
      </aside>{:else if aggregateOpen}<aside
        class="reading-sheet aggregate-sheet"
        aria-labelledby="aggregate-title"
      >
        <button
          type="button"
          class="close"
          aria-label="Close aggregate and return to map"
          onclick={() => dispatch({ type: "aggregate", value: null })}>×</button
        >
        <p class="eyebrow">PRIVATE PREVIEW / MAP REFERENCE</p>
        <p class="aggregate-source">{aggregateContext.sourceText}</p>
        <h2 id="aggregate-title">{aggregateContext.place}</h2>
        <p class="place">{aggregateContext.treatment}</p>
        <dl>
          <div>
            <dt>Mapped members</dt>
            <dd>{aggregateRequestedCount}</dd>
          </div>
          <div>
            <dt>Loaded here</dt>
            <dd>{resultCount} records</dd>
          </div>
          <div>
            <dt>Member access</dt>
            <dd>Bounded to this map response</dd>
          </div>
        </dl>
        <p class="evidence-note">
          Use the Members panel to inspect the loaded records. Selecting a
          member opens its own evidence record.
        </p>
        {#if aggregateContext.locality}<p class="continuation-note">
            This preview has no reference-specific member cursor. Continue
            through the global, paginated search for this locality.
          </p>
          <button
            class="continue-members"
            type="button"
            onclick={browseAggregate}
            >Search all records for {aggregateContext.locality}</button
          >{:else}<p class="continuation-note">
            This preview has no reference-specific member cursor. Only the
            bounded map response is available here.
          </p>{/if}<button
          class="open-members"
          type="button"
          onclick={() => dispatch({ type: "list", value: true })}
          >Open member records</button
        >
      </aside>{/if}
  </section>
</section>

<style>
  .field-view {
    --ink: #f1efe8;
    --muted: #aab0aa;
    --line: #48504b;
    position: fixed;
    inset: 0;
    background: #171a18;
    color: var(--ink);
    font-family:
      system-ui,
      -apple-system,
      "Segoe UI",
      sans-serif;
  }
  .field-view * {
    box-sizing: border-box;
  }
  .spine {
    position: absolute;
    z-index: 5;
    inset: 0 0 auto;
    display: grid;
    grid-template-columns: auto minmax(12rem, 34rem) auto;
    gap: 0.7rem;
    align-items: center;
    height: 4.5rem;
    padding: 0.65rem 1rem;
    border-bottom: 1px solid var(--line);
    background: #171a18;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    color: inherit;
    text-decoration: none;
    font:
      600 0.9rem Georgia,
      serif;
  }
  .brand img {
    width: 2rem;
    height: 2rem;
    object-fit: contain;
  }
  .search {
    height: 2.5rem;
    border: 1px solid #69716a;
    background: #111312;
  }
  .search label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
  }
  .search input {
    width: 100%;
    height: 100%;
    padding: 0 0.7rem;
    border: 0;
    outline: 0;
    color: var(--ink);
    background: transparent;
    font: inherit;
  }
  .filters {
    position: relative;
  }
  .filters summary,
  .results-toggle,
  .filter-sheet button {
    min-height: 2.4rem;
    padding: 0.4rem 0.65rem;
    border: 1px solid #69716a;
    color: var(--ink);
    background: #171a18;
    cursor: pointer;
    font: 0.72rem system-ui;
    list-style: none;
  }
  .filters summary::-webkit-details-marker {
    display: none;
  }
  .filters summary b,
  .results-toggle b {
    margin-left: 0.3rem;
    padding: 0.06rem 0.3rem;
    border: 1px solid #7b837c;
  }
  .filter-sheet {
    position: absolute;
    top: 3rem;
    right: 0;
    width: 20rem;
    padding: 0.9rem;
    border: 1px solid var(--line);
    background: #1b1f1d;
    box-shadow: 0 0.6rem 1.5rem #0008;
  }
  .category-key {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin: 0.65rem 0;
    color: var(--muted);
    font-size: 0.61rem;
  }
  .category-key i {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: #c83232;
  }
  .category-key .pig {
    background: #8c8c8c;
  }
  .category-key .dairy {
    background: #7f5c9c;
  }
  .category-key .processing {
    background: #ccb44f;
  }
  .category-key .laboratory {
    background: #d47b30;
  }
  .category-key .aquaculture {
    background: #39804e;
  }
  .filter-sheet fieldset {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.4rem;
    margin: 0.65rem 0;
    padding: 0;
    border: 0;
  }
  .filter-sheet legend {
    color: var(--muted);
    font-size: 0.68rem;
  }
  .filter-sheet label {
    font-size: 0.7rem;
  }
  .map-stage {
    position: absolute;
    inset: 4.5rem 0 0;
  }
  .map-stage :global(.map-surface),
  .map-stage :global(.map-host) {
    position: absolute;
    inset: 0;
  }
  .status {
    position: absolute;
    z-index: 4;
    top: 50%;
    left: 50%;
    padding: 1rem;
    border: 1px solid var(--line);
    background: #171a18;
    transform: translate(-50%, -50%);
  }
  .results-toggle {
    position: absolute;
    z-index: 4;
    top: 1rem;
    left: 1rem;
  }
  .results {
    position: absolute;
    z-index: 5;
    top: 1rem;
    bottom: 1rem;
    left: 1rem;
    width: min(21rem, calc(100% - 2rem));
    border: 1px solid var(--line);
    background: #171a18;
  }
  .results header {
    display: flex;
    justify-content: space-between;
    padding: 0.65rem;
    border-bottom: 1px solid var(--line);
  }
  .results header button,
  .close {
    border: 1px solid var(--line);
    color: inherit;
    background: #202421;
    cursor: pointer;
  }
  .results :global(.record-list) {
    height: calc(100% - 3rem);
    overflow: auto;
    border: 0;
    background: transparent;
  }
  .results :global(.record-list h2) {
    display: none;
  }
  .results :global(.record-list ol) {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .results :global(.record-list li) {
    border-bottom: 1px solid #343a36;
  }
  .results :global(.record-list button) {
    width: 100%;
    padding: 0.7rem;
    border: 0;
    color: inherit;
    background: transparent;
    text-align: left;
  }
  .results :global(.record-list button.active) {
    background: #2a302c;
  }
  .results :global(.record-list small) {
    display: block;
    color: var(--muted);
    font-size: 0.68rem;
  }
  .member-disclosure {
    margin: 0;
    padding: 0.55rem 0.65rem;
    border-bottom: 1px solid #343a36;
    color: var(--muted);
    font-size: 0.68rem;
    line-height: 1.35;
  }
  .results:has(.member-disclosure) :global(.record-list) {
    height: calc(100% - 5.9rem);
  }
  .reading-sheet {
    position: absolute;
    z-index: 5;
    top: 1rem;
    right: 1rem;
    bottom: 1rem;
    width: min(25rem, calc(100% - 2rem));
    padding: 1.25rem;
    border: 1px solid var(--line);
    background: #171a18;
    overflow: auto;
  }
  .close {
    position: absolute;
    top: 0.7rem;
    right: 0.7rem;
    width: 2rem;
    height: 2rem;
    font-size: 1rem;
  }
  .reading-sheet h2 {
    margin: 1rem 2rem 0.5rem 0;
    font:
      500 1.45rem Georgia,
      serif;
  }
  .reading-sheet p {
    color: var(--muted);
  }
  .dossier {
    border-top: 2px solid #a5b8a6;
    padding: 0;
  }
  .full-record { display:block; margin:0 1.1rem; padding:.55rem 0; color:#ddd4bb; font-size:.75rem; text-underline-offset:2px; }
  .dossier .connections-evidence { margin:1rem 1.1rem 1.2rem; }
  .eyebrow {
    margin: 0 0 0.3rem;
    color: #b9c7b8 !important;
    font:
      0.59rem ui-monospace,
      monospace;
    letter-spacing: 0.12em;
  }
  .place {
    margin-top: 0;
  }
  .reading-sheet dl {
    margin: 1.3rem 0;
  }
  .reading-sheet dl div {
    display: grid;
    grid-template-columns: 7rem 1fr;
    gap: 0.7rem;
    padding: 0.7rem 0;
    border-top: 1px solid #343a36;
  }
  .reading-sheet dt {
    color: var(--muted);
    font-size: 0.68rem;
  }
  .reading-sheet dd {
    margin: 0;
    font-size: 0.74rem;
    line-height: 1.35;
  }
  .evidence-note {
    padding: 0.65rem 0;
    border-top: 1px solid #343a36;
    font-size: 0.72rem;
    line-height: 1.45;
  }
  .open-members {
    width: 100%;
    min-height: 2.5rem;
    border: 1px solid #7a8b7b;
    color: var(--ink);
    background: #212821;
    font: 0.72rem system-ui;
    cursor: pointer;
  }
  @media (max-width: 40rem) {
    .spine {
      grid-template-columns: auto 1fr auto;
      height: 7rem;
      padding: 0.5rem 0.65rem;
    }
    .brand span {
      display: none;
    }
    .search {
      grid-column: 1/3;
      grid-row: 2;
    }
    .filters {
      grid-column: 3;
      grid-row: 2;
    }
    .filters summary {
      font-size: 0;
      width: 2.7rem;
    }
    .filters summary::after {
      content: "☰";
      font-size: 1rem;
    }
    .map-stage {
      inset: 7rem 0 0;
    }
    .results {
      top: auto;
      right: 0;
      bottom: 0;
      left: 0;
      width: auto;
      height: min(48dvh, 26rem);
    }
    .reading-sheet {
      top: auto;
      right: 0.65rem;
      bottom: 0.65rem;
      left: 0.65rem;
      width: auto;
      height: auto;
      max-height: 67dvh;
    }
    .map-stage:has(.reading-sheet) .results-toggle {
      display: none;
    }
  }
  .database-link {
    position: absolute;
    z-index: 4;
    top: 1rem;
    left: 8.4rem;
    min-height: 2.4rem;
    padding: 0.62rem 0.72rem;
    border: 1px solid #69716a;
    color: var(--ink);
    background: #171a18;
    font: 0.72rem system-ui;
    text-decoration: none;
  }
  @media (max-width: 40rem) {
    .database-link {
      top: 1rem;
      left: 7.7rem;
      min-height: 2.25rem;
      padding: 0.54rem 0.6rem;
    }
    .map-stage:has(.reading-sheet) .database-link {
      display: none;
    }
  }
  .member-context {
    display: grid;
    gap: 0.24rem;
    padding: 0.68rem 0.65rem;
    border-bottom: 1px solid #343a36;
    background: #1c211e;
  }
  .member-context strong {
    font:
      600 0.82rem Georgia,
      serif;
  }
  .member-context span,
  .member-context small {
    color: var(--muted);
    font-size: 0.66rem;
    line-height: 1.35;
  }
  .aggregate-source {
    margin: 0.3rem 2rem 0.25rem 0 !important;
    color: #b9c7b8 !important;
    font:
      0.65rem ui-monospace,
      monospace;
  }
  .back {
    min-height: 2rem;
    margin: 0 0 0.8rem;
    padding: 0 0.5rem;
    border: 1px solid var(--line);
    color: var(--ink);
    background: #202421;
    font: 0.68rem system-ui;
    cursor: pointer;
  }
  .continuation-note {
    margin: 0.6rem 0 !important;
    font-size: 0.68rem;
    line-height: 1.4;
  }
  .continue-members {
    width: 100%;
    min-height: 2.5rem;
    margin: 0.3rem 0;
    border: 1px solid #69716a;
    color: var(--ink);
    background: #202421;
    font: 0.72rem system-ui;
    cursor: pointer;
  }
  .results:has(.member-context) :global(.record-list) {
    height: calc(100% - 9.35rem);
  }
  @media (max-width: 40rem) {
    .results:has(.member-context) {
      height: min(54dvh, 31rem);
    }
    .results:has(.member-context) :global(.record-list) {
      height: calc(100% - 9.35rem);
    }
    .aggregate-sheet {
      top: 0.75rem;
      right: 0.65rem;
      bottom: auto;
      left: 4.2rem;
      width: auto;
      max-height: min(35dvh, 15.5rem);
      padding: 0.85rem 0.9rem;
      background: #171a18ee;
      box-shadow: 0 0.5rem 1.3rem #0008;
    }
    .aggregate-sheet h2 {
      margin: 0.55rem 2rem 0.35rem 0;
      font-size: 1.05rem;
    }
    .aggregate-sheet .eyebrow {
      font-size: 0.52rem;
    }
    .aggregate-sheet .aggregate-source {
      font-size: 0.58rem;
    }
    .aggregate-sheet .place {
      margin: 0.3rem 1.7rem 0.35rem 0;
      font-size: 0.67rem;
      line-height: 1.35;
    }
    .aggregate-sheet dl,
    .aggregate-sheet .evidence-note,
    .aggregate-sheet .open-members {
      display: none;
    }
    .aggregate-sheet .continuation-note {
      margin: 0.35rem 0 !important;
      font-size: 0.61rem;
    }
    .aggregate-sheet .continue-members {
      min-height: 2.1rem;
      font-size: 0.66rem;
    }
    .reading-sheet.dossier {
      padding: 0;
    }
    .reading-sheet.dossier .back {
      margin-right: 0.4rem;
    }
    .results header {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #171a18;
    }
    .member-context {
      position: sticky;
      top: 2.8rem;
      z-index: 1;
    }
    .member-disclosure {
      position: sticky;
      top: 6.2rem;
      z-index: 1;
      background: #171a18;
    }
    .map-stage:has(.reading-sheet) .results-toggle {
      display: none;
    }
  }
  .connections-evidence {
    margin: 0.95rem 0;
    padding: 0.8rem;
    border: 1px solid #3e4740;
    border-left: 2px solid #9aaa98;
    background: #1c211e;
  }
  .connections-evidence h3 {
    margin: 0.1rem 0 0.55rem;
    font:
      600 0.98rem Georgia,
      serif;
  }
  .connections-evidence p {
    margin: 0.45rem 0;
    color: #c7cec5;
    font-size: 0.7rem;
    line-height: 1.45;
  }
  .connections-evidence .eyebrow {
    color: #b9c7b8 !important;
  }
  .connection-disclosure {
    color: var(--muted) !important;
    font-size: 0.65rem !important;
  }
</style>
