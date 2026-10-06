<script lang="ts">
  import { tick } from "svelte";
  import { writable } from "svelte/store";
  import type {
    DirectionViewProps,
    LabRecord,
    MapDiagnostics,
    Precision,
  } from "../../contract";
  import type { RealPreviewFacet } from "../../../api/RealPreviewRepository";
  import MapSurface from "../../components/MapSurface.svelte";
  import WorldLocator from "../../components/WorldLocator.svelte";
  import RecordList from "../../components/RecordList.svelte";
  import RecordDetail from "../../../app/RecordDetail.svelte";
  import PreviewMasthead from "../../../app/PreviewMasthead.svelte";
  import type { PlaceSuggestion } from "../../../features/placeSearch/placeSearch";
  let {
    state,
    records,
    mapRecords,
    coverageOpen = false,
    mode = "synthetic",
    dataStatus = "ready",
    dataError = "",
    mapStatus = "idle",
    mapError = "",
    mapTruncated = false,
    mapDiagnostics,
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
    coverageOpen?: boolean;
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
  const precisionLabel = (record: LabRecord) =>
    mode === "real-preview"
      ? record.sourceId === 'us.fsis' && record.coordinatePrecision === 'source-provided'
        ? 'Source-provided coordinate · precision unverified · private rehearsal, not approved'
        : record.precision === "city"
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
  let selectionOrigin: HTMLElement | null = null;
  let selectionOriginRecordId: string | null = null;
  // `state` is a prop in this component, so $state is interpreted as a store
  // subscription rather than Svelte's rune. Use a store for this DOM binding.
  const searchToggle = writable<HTMLButtonElement | undefined>(undefined);
  const debugOpen = writable(false);
  const debugEnabled = writable(false);
  const initialSelectedId = (() => {
    if (typeof location === "undefined") return null;
    const route = new URLSearchParams(location.hash.split("?")[1] ?? "");
    return route.get("focus") === "selected" ? route.get("selected") : null;
  })();
  let initialSelectionFlightHandled = false;
  const placeSuggestions = writable<readonly PlaceSuggestion[]>([]);
  const flightTarget = writable<{
    id: number;
    longitude: number;
    latitude: number;
    zoom: number;
  } | null>(null);
  let flightSequence = 0;
  let placeSearchGeneration = 0;
  let placeSearchModule: Promise<typeof import("../../../features/placeSearch/placeSearch")> | undefined;
  // The gazetteer is lazy and local: typing a place never contacts a geocoder.
  $effect(() => {
    const query = state.query.trim();
    if (!state.listOpen || query.length < 2 || aggregateOpen) {
      placeSuggestions.set([]);
      return;
    }
    const generation = ++placeSearchGeneration;
    placeSearchModule ??= import("../../../features/placeSearch/placeSearch");
    void placeSearchModule.then(({ searchPlaces }) => {
      if (generation === placeSearchGeneration) {
        placeSuggestions.set(searchPlaces(query, 5));
      }
    }).catch(() => {
      if (generation === placeSearchGeneration) placeSuggestions.set([]);
    });
    return () => { placeSearchGeneration++; };
  });
  let hadSelection = false;
  let activeSelectionId: string | null = null;
  let pendingRailFocusId: string | null = null;
  $effect(() => {
    if (state.selectedId) {
      hadSelection = true;
      if (activeSelectionId !== state.selectedId) {
        activeSelectionId = state.selectedId;
        pendingRailFocusId = state.selectedId;
      }
      // A Forward navigation can restore the dossier without calling
      // selectRecord again. Keep its row as the dismissal fallback.
      selectionOriginRecordId ??= state.selectedId;
      // Wait for evidence loading to finish: the loading and ready rails are
      // separate branches, so focusing the loading close button would leave
      // focus on BODY when that branch is replaced.
      if (pendingRailFocusId === state.selectedId && detailStatus !== "loading") {
        const id = state.selectedId;
        pendingRailFocusId = null;
        void tick().then(() => {
          if (state.selectedId === id) {
            document.querySelector<HTMLButtonElement>(".dossier-header button")?.focus();
          }
        });
      }
    } else if (hadSelection) {
      hadSelection = false;
      activeSelectionId = null;
      pendingRailFocusId = null;
      void tick().then(() => {
        const restoredRecord = selectionOriginRecordId
          ? [...document.querySelectorAll<HTMLElement>("[data-record-id]")]
              .find((item) => item.dataset.recordId === selectionOriginRecordId)
          : null;
        const target = selectionOrigin?.isConnected
          ? selectionOrigin
          : restoredRecord ?? $searchToggle;
        target?.focus();
        selectionOrigin = null;
        selectionOriginRecordId = null;
      });
    }
  });
  function selectRecord(id: string) {
    selectionOrigin = document.activeElement instanceof HTMLElement && document.activeElement !== document.body
      ? document.activeElement
      : null;
    selectionOriginRecordId = selectionOrigin?.dataset.recordId ?? null;
    dispatch({ type: "select", value: id });
  }
  function flyTo(longitude: number, latitude: number, zoom: number) {
    flightTarget.set({ id: ++flightSequence, longitude, latitude, zoom });
  }
  $effect(() => {
    if (initialSelectionFlightHandled || !initialSelectedId || detailStatus !== "ready" || detailRecord?.id !== initialSelectedId) return;
    initialSelectionFlightHandled = true;
    if (detailRecord.latitude != null && detailRecord.longitude != null) {
      flyTo(detailRecord.longitude, detailRecord.latitude,
        detailRecord.precision === "city" ? 10 : 14);
    }
  });
  function selectSearchRecord(id: string) {
    const record = recordPool.find((item) => item.id === id);
    if (record?.latitude !== null && record?.longitude !== null &&
        record?.latitude !== undefined && record?.longitude !== undefined) {
      // A city reference remains an approximation; do not zoom into a parcel.
      flyTo(record.longitude, record.latitude,
        record.precision === "city" ? 10 : 14);
    }
    selectRecord(id);
  }
  function selectPlace(place: PlaceSuggestion) {
    // Natural Earth supplies a city-centre navigation point, not a facility.
    flyTo(place.longitude, place.latitude, 10);
    // Keep the drawer in the hit-test tree until this pointer click finishes.
    // Removing it synchronously can send the tail of the gesture to the map.
    setTimeout(() => dispatch({ type: "list", value: false }), 0);
  }
  function dismissSelection() {
    dispatch({ type: "select", value: null });
  }
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
      dismissSelection();
      return;
    }
    if (aggregateOpen) {
      dispatch({ type: "aggregate", value: null });
      return;
    }
    if (state.listOpen) dispatch({ type: "list", value: false });
  }
  function onKeydown(event: KeyboardEvent) {
    if (event.key === "Escape" && (state.selectedId || aggregateOpen || state.listOpen)) {
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
      q.set("f1a", "field");
      if (state.sourceId) q.set("source", state.sourceId);
      if (state.selectedId) q.set("selected", state.selectedId);
      q.set("lat", String(state.viewport.centerLat));
      q.set("lon", String(state.viewport.centerLon));
      q.set("z", String(state.viewport.zoom));
      if (!state.listOpen) q.set("list", "closed");
      if (state.basemap !== "vector") q.set("basemap", state.basemap);
      return `#/database?${q}`;
    })(),
  );
  const mapHref = $derived(
    `#/map?${new URLSearchParams({ f1a: "field", scenario: state.scenario, ...Object.fromEntries(new URLSearchParams(databaseHref.split("?")[1] ?? "")) })}`,
  );
</script>

<svelte:window onkeydown={onKeydown} />
<section class="field-view">
  <PreviewMasthead privateTools current="map" {mapHref} {databaseHref} debugEnabled={$debugEnabled} ondebugchange={(enabled) => { debugEnabled.set(enabled); if (!enabled) debugOpen.set(false); }} />
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
        flightTarget={$flightTarget}
        debugEnabled={$debugEnabled}
        suppressDiagnostics={state.listOpen && !selected}
        referenceLoading={aggregateLoading}
        onmaptiming={(timing) => onMapTiming?.(timing)}
        onselect={selectRecord}
        onaggregate={(ids) => dispatch({ type: "aggregate", value: ids })}
        onreference={(key, sourceId) => onMapReference?.(key, sourceId)}
        onbasemap={(value) => dispatch({ type: "basemap", value })}
        ondebugopenchange={(open) => debugOpen.set(open)}
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
    {#if !state.listOpen}<button
      class="search-toggle"
      bind:this={$searchToggle}
      type="button"
      aria-expanded={state.listOpen}
      aria-controls="field-record-list"
      onclick={() => dispatch({ type: "list", value: !state.listOpen })}
      ><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg><span class="search-toggle-copy"><strong>Search map</strong><small>{state.query || state.sourceId ? "Search or filters active" : "Places, facilities, sources"}</small></span></button>{/if}
    {#if state.listOpen}<aside
        class="results"
        id="field-record-list"
        aria-label={aggregateOpen
          ? "Aggregate member records"
          : "Search, filters, and results"}
      >
        <header>
          <strong>Search records</strong><button
            type="button"
            aria-label="Close search panel"
            onclick={() => dispatch({ type: "list", value: false })}>×</button
          >
        </header>
        <div class="search-tools">
          <form class="search" role="search" onsubmit={(event) => event.preventDefault()}>
            <label for="field-search">Search across preview records</label>
            <input id="field-search" type="search" placeholder="Name, activity, source, or place"
              value={state.query} oninput={(event) => dispatch({ type: "query", value: event.currentTarget.value })} />
          </form>
          <details class="filters">
            <summary>Filters {#if state.sourceId}<b>1</b>{:else if active}<b>{active}</b>{/if}</summary>
            <div class="filter-sheet">
              {#if mode === "real-preview"}
                <fieldset class="source-filter">
                  <legend>Source</legend>
                  {#if facetsStatus === "loading"}<small>Loading sources…</small>
                  {:else if facetsStatus === "error" || facetsStatus === "unauthorized"}<small role="alert">Sources unavailable. Search remains available.</small>
                  {:else}
                    <label><input type="radio" name="source" checked={state.sourceId === null} onchange={() => dispatch({ type: "source", value: null })} />All sources</label>
                    {#each sources as value}<label><input type="radio" name="source" checked={state.sourceId === value} onchange={() => dispatch({ type: "source", value })} />{value}</label>{/each}
                  {/if}
                </fieldset>
              {:else}
                <p class="category-key"><i class="poultry"></i>Poultry <i class="pig"></i>Pig <i class="dairy"></i>Dairy <i class="processing"></i>Processing <i class="laboratory"></i>Lab <i class="aquaculture"></i>Aquaculture</p>
                <fieldset><legend>Category</legend>{#each categories as value}<label><input type="checkbox" checked={state.filters.categories.includes(value)} onchange={(event) => category(value, event.currentTarget.checked)} />{value}</label>{/each}</fieldset>
                <fieldset><legend>Location precision</legend>{#each precisions as value}<label><input type="checkbox" checked={state.filters.precisions.includes(value)} onchange={(event) => precision(value, event.currentTarget.checked)} />{value}</label>{/each}</fieldset>
              {/if}
              <button type="button" onclick={() => mode === "real-preview" ? dispatch({ type: "source", value: null }) : dispatch({ type: "reset-filters" })}>Clear filters</button>
            </div>
          </details>
        </div>
        {#if $placeSuggestions.length > 0}
          <section class="place-suggestions" aria-label="Places">
            <div class="results-heading"><strong>Places</strong><span>City centres</span></div>
            <ol>
              {#each $placeSuggestions as place (place.id)}
                <li><button type="button" onclick={(event) => { event.stopPropagation(); selectPlace(place); }}>
                  <strong>{place.label}</strong>
                  <small>Navigate to city centre · Natural Earth, not a facility location</small>
                </button></li>
              {/each}
            </ol>
          </section>
        {/if}
        <div class="results-heading"><strong>{aggregateOpen ? "Members" : "Facility records"}</strong><span>{resultCount} loaded</span></div>
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
          onselect={selectSearchRecord}
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
        class="reading-sheet dossier"
        role="status"
      >
        <header class="dossier-header"><span>Record evidence</span><button type="button" aria-label="Close record detail" onclick={dismissSelection}>×</button></header>
        <p class="dossier-message">Loading record evidence…</p>
      </aside>{:else if state.selectedId && mode === "real-preview" && (detailStatus === "error" || detailStatus === "unauthorized")}<aside
        class="reading-sheet dossier"
        role="alert"
      >
        <header class="dossier-header"><span>Record evidence</span><button type="button" aria-label="Close record detail" onclick={dismissSelection}>×</button></header>
        <p class="dossier-message">{detailError}</p>
      </aside>{:else if selected}<aside class="reading-sheet dossier" aria-label="Record evidence">
        <header class="dossier-header"><span>Record evidence</span><button type="button" aria-label="Close record detail" onclick={dismissSelection}>×</button></header>
        {#if aggregateOpen}<button type="button" class="back" onclick={dismissSelection}>← Members</button>{/if}
        <a class="full-record" href={`#/records/${encodeURIComponent(selected.id)}`}>Open full record <span aria-hidden="true">↗</span></a>
        <RecordDetail record={selected} presentation="rail" />
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
    <div class="world-position" hidden={$debugOpen || coverageOpen}><WorldLocator latitude={state.viewport.centerLat} longitude={state.viewport.centerLon} basemap={state.basemap} onbasemap={(value) => dispatch({ type: "basemap", value })} /></div>
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
  .field-view :global(.masthead) { position: relative; z-index: 5; }
  .search {
    height: 2.6rem;
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
  .filters { position:relative; min-width:8.25rem; }
  .filters summary,
  .search-toggle,
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
  .filters summary b {
    margin-left: 0.3rem;
    padding: 0.06rem 0.3rem;
    border: 1px solid #7b837c;
  }
  .filter-sheet {
    position:absolute;
    z-index:8;
    top:calc(100% + .3rem);
    right:0;
    width:min(20rem, calc(100vw - 2rem));
    max-height:min(26rem, 65vh);
    overflow:auto;
    padding: 0.55rem 0.4rem;
    border: 1px solid var(--line);
    background: #1b1f1d;
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
    inset: 4.8rem 0 0;
  }
  .map-stage :global(.map-surface),
  .map-stage :global(.map-host) {
    position: absolute;
    inset: 0;
  }
  .world-position { position: absolute; z-index: 3; right: 0.5rem; bottom: 1.65rem; }
  .map-stage:has(.reading-sheet) .world-position { display: none; }
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
  .search-toggle {
    position: absolute;
    z-index: 4;
    top: 1rem;
    left: 1rem;
  }
  .search-toggle { display:flex; align-items:center; gap:.55rem; min-width:13rem; text-align:left; }
  .search-toggle svg { width:1.15rem; height:1.15rem; flex:none; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; }
  .search-toggle-copy { display:grid; gap:.12rem; }
  .search-toggle-copy strong { font-size:.72rem; font-weight:650; }
  .search-toggle-copy small { color:var(--muted); font-size:.59rem; }
  .search-toggle:focus-visible { outline:2px solid #f1efe8; outline-offset:2px; }
  .results {
    position: absolute;
    z-index: 5;
    top: 1rem;
    bottom: 2rem;
    left: 1rem;
    display: flex;
    flex-direction: column;
    width: min(35rem, calc(100% - 2rem));
    border: 1px solid var(--line);
    background: #171a18;
  }
  .map-stage:has(.results):has(.reading-sheet) .results { width:min(31rem, calc(50% - 1.5rem)); }
  .map-stage:has(.results):has(.reading-sheet) .reading-sheet { width:min(25rem, calc(50% - 1.5rem)); }
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
    flex: 1 1 auto;
    min-height: 0;
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
  .results :global(.record-list button:focus) {
    outline: 2px solid #eee7d6;
    outline-offset: -2px;
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
  .search-tools { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:start; gap:.55rem; flex:0 0 auto; padding:.65rem; border-bottom:1px solid var(--line); }
  .search-tools .search { min-width:0; }
  .filters summary { display:flex; align-items:center; justify-content:center; min-height:2.6rem; }
  .results-heading { display: flex; flex-shrink: 0; justify-content: space-between; gap: 0.5rem; padding: 0.55rem 0.65rem; border-bottom: 1px solid var(--line); font-size: 0.73rem; }
  .results-heading span { color: var(--muted); font-variant-numeric: tabular-nums; }
  .place-suggestions { flex: 0 0 auto; max-height: min(12rem, 32vh); overflow-y: auto; border-bottom: 1px solid var(--line); }
  .place-suggestions ol { margin: 0; padding: 0; list-style: none; }
  .place-suggestions li + li { border-top: 1px solid #343a36; }
  .place-suggestions button { display: block; width: 100%; padding: 0.62rem 0.7rem; border: 0; color: var(--ink); background: #1b2528; text-align: left; cursor: pointer; }
  .place-suggestions button:hover, .place-suggestions button:focus-visible { background: #253236; }
  .place-suggestions button:focus-visible { outline: 2px solid #b9d5dc; outline-offset: -2px; }
  .place-suggestions strong, .place-suggestions small { display: block; }
  .place-suggestions strong { font-size: 0.77rem; }
  .place-suggestions small { margin-top: 0.18rem; color: #afc3c7; font-size: 0.66rem; line-height: 1.35; }
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
  .dossier-header { position:sticky; top:0; z-index:2; display:flex; align-items:center; justify-content:space-between; min-height:2.7rem; padding:.3rem .65rem .3rem 1.1rem; border-bottom:1px solid var(--line); background:#171a18; color:#c6cec4; font-size:.68rem; letter-spacing:.04em; }
  .dossier-header button { min-width:2.2rem; min-height:2.2rem; border:1px solid var(--line); color:var(--ink); background:#202421; font-size:1.25rem; cursor:pointer; }
  .dossier-header button:focus-visible, .full-record:focus-visible { outline:2px solid #eee7d6; outline-offset:2px; }
  .dossier-message { margin:1.1rem; }
  .full-record { display:flex; align-items:center; justify-content:space-between; margin:0; padding:.8rem 1.1rem; border-bottom:1px solid var(--line); color:#eee5ce; font-size:.75rem; text-underline-offset:2px; }
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
    .map-stage { inset: 4.8rem 0 0; }
    .search-toggle { top: 0.65rem; left: 0.65rem; }
    .results {
      top: 0.65rem;
      right: 0.65rem;
      bottom: 3rem;
      left: 0.65rem;
      width: auto;
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
    .map-stage:has(.results):has(.reading-sheet) .results { display:none; }
    .map-stage:has(.results):has(.reading-sheet) .reading-sheet { width:auto; }
    .map-stage:has(.reading-sheet) .search-toggle { display: none; }
    .world-position { bottom: 7.5rem; right: 0.4rem; }
    .map-stage:has(.results) .world-position { display: none; }
    /* Header menus take precedence over the Map lens on a narrow screen. */
    :global(body:has(.masthead .header-menu) .world-position) { display:none; }
    .search-tools { grid-template-columns:1fr; }
    .filters { width:100%; }
    .filters summary { justify-content:flex-start; }
    .filter-sheet { right:auto; left:0; }
    .search-toggle { min-width:11.8rem; }
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
  @media (max-width: 40rem) {
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
