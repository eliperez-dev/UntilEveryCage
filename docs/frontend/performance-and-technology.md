# Performance and technology assessment

## Recommendation

Retain Svelte 5 and TypeScript as the starting implementation because the
repository already has a functioning preview and tests. Keep Rust/Axum/PostGIS
as the source of query truth. Benchmark MapLibre GL JS with a WebGL/vector-tile
source against the existing Leaflet adapter before committing the map engine.

For the target scale—100,000 facilities and approximately 150,000 public graph
edges—the design recommendation is **MapLibre GL JS with WebGL and server-side
viewport or vector-tile clustering**, unless a documented benchmark shows the
current Leaflet path meets the same budgets without downloading global data.
MapLibre's WebGL renderer, vector sources, source clustering, heatmap layers,
and globe projection make it a strong candidate for the planned map, alternate
data views, and eventual 3D globe. Leaflet is useful as a compatibility/fallback
adapter, not the assumed scale architecture.

## What V1 teaches us

V1 loads all three datasets, filters arrays in the browser, recreates marker
layers after filter changes, and activates one unified marker-cluster layer
above a threshold. This is a valuable interaction baseline but it does not
scale as a public global read path. Preserve the user outcome—clusters lead to
individual detail—while moving data selection server-side.

## Candidate map strategies

| Strategy | Strength | Risk | Recommendation |
| --- | --- | --- | --- |
| Leaflet + MarkerCluster | Familiar, small migration cost, clear popup semantics | DOM marker cost and global-data temptation at 100k; coarse points need custom grammar | Keep adapter for fallback/benchmark |
| MapLibre + source clustering | WebGL, smooth viewport rendering, native cluster transitions | Tile/style/worker complexity and external tile decisions | Preferred candidate for production |
| MapLibre + server vector tiles | Best transfer bounds and stable large-scale rendering | Requires tile endpoint/cache/release invalidation design | Preferred when load tests justify it |
| Worker Supercluster over bounded pages | Portable and testable; no map-server dependency | Client index still limited to fetched subset; transfer can be expensive | Fallback for bounded API responses |
| Heatmap-first | Visually compelling; MapLibre supports a GPU-friendly heatmap layer | Collapses exact/coarse semantics and can imply measured density | Defer; not MVP default |

## Exact, city, and unmapped rendering

The frontend must not turn city centroids into facility pins. Use a distinct
area/halo symbol for city/coarse records, preserve the city label, and exclude
unmapped records from spatial placement. Clusters should expose composition when
the server can provide it. A later heatmap must have separate exact/coarse
layers, a declared denominator, a declared kernel/radius, and tests against
sparse and dense countries.

The benchmark corpus must include map view transitions between vector, satellite,
and (when enabled) globe projection, along with exact/coarse composition. A
satellite layer is provider-dependent. Prefer a licensed, documented raster
provider that is compatible with the selected MapLibre source/style pipeline.
Mapbox Standard Satellite is not assumed to be a drop-in MapLibre style: its
official compatibility is tied to the compatible Mapbox GL JS v3/SDK v11
renderer and Mapbox platform terms. If evaluated, it is an alternative stack
decision with its own attribution, API key handling, privacy, licensing, and
cost review. Google Street View is an optional exact-point provider integration,
not a map engine. Historical imagery such as Esri Wayback is possible only
where provider coverage and terms permit; it is not a globally reliable backend
capability.

Provider compatibility references: [Mapbox Standard Satellite](https://docs.mapbox.com/map-styles/reference/standard-satellite/),
[Mapbox GL JS migration requirements](https://docs.mapbox.com/mapbox-gl-js/guides/migrate/),
and [Mapbox imagery terms](https://www.mapbox.com/imagery). These references
inform evaluation; they do not select a provider or authorize credentials.

## Budgets for the first implementation

These are review budgets, not promises. Measure on a mid-range 2022 laptop and
an emulated mobile profile, with 100k synthetic facilities and 150k synthetic
edges. Record p50/p95 and payload sizes.

| Metric | Review budget |
| --- | ---: |
| Initial HTML-to-interactive shell | p95 ≤ 1.5s on local/nearby API; ≤ 2.5s mobile emulation |
| Initial JS transferred (compressed) | ≤ 250KB before map engine; ≤ 450KB with map route loaded |
| Search input to first response | p95 ≤ 500ms local API; stale response never replaces current |
| Filter application to list update | p95 ≤ 800ms end to end |
| Map pan/zoom to usable viewport result | p95 ≤ 1.0s at 100k synthetic facilities |
| Main-thread long task during map update | no task > 100ms in normal viewport |
| Database first page | use existing ≤800ms end-to-end review target |
| Database cursor page | ≤700ms end-to-end review target |
| Facility detail | ≤600ms end-to-end review target |
| Graph one-hop detail | ≤800ms end-to-end, bounded edge page |
| Browser discovery-record memory | ≤128MB at 100k synthetic scale |
| Graph rows rendered at once | ≤200; paginate/virtualize beyond |
| Accessibility zoom | usable at 200% and 320px width |

The existing backend evidence is more conservative at concurrency: 100k/150k
synthetic API runs show timeouts under heavier concurrency on the Windows host.
Do not turn the single-machine capture into a public capacity claim. The
frontend must avoid amplifying that pressure with request storms.

## Request and rendering rules

- Use AbortController/generation tokens for search, facets, detail, and viewport.
- Debounce search and map movement; coalesce filter changes behind Apply on
  mobile.
- Never request the global facility or graph dataset to render a viewport.
- Virtualize long Database tables and graph lists.
- Preserve the last valid result context while loading a replacement, but label
  it as previous/loading.
- Do not cache around suppression/release checks unless the backend contract
  supplies explicit invalidation semantics.
- Code-split the Map and Database routes while keeping the shell small.
- Keep imagery and graph visualization code-split: satellite/street/history
  controls and the graph canvas should not inflate the first map/database shell.

## Benchmark plan before engine lock

Run identical synthetic fixtures at 10k, 100k, and 150k facilities with exact,
city, and unmapped strata; 150k edges with exact/high/medium/low/conflicting
bands; urban and rural distributions; and query mixes from the UI-state matrix.
Compare Leaflet, MapLibre client clustering, and MapLibre/vector-tile or server
cluster candidates on transfer size, first point, pan latency, main-thread work,
memory, keyboard/list fallback, suppression correctness, exact/coarse rendering,
and satellite/vector toggle cost. Include a bounded interactive graph canvas
test with node/edge selection and an accessible edge-list fallback. The winner
is the one that meets budgets and semantics, not the one with the most impressive
demo.
