# MVP cuts and implementation sequence

## MVP surface

The first build includes:

1. Map route with global-search semantics over the currently supported public
   record fields plus separate bbox/radius viewport loading,
   exact/city/coarse/unmapped semantics, synchronized accessible list,
   category/location/precision/lifecycle filters, clusters, selectable
   vector/satellite basemaps, stable URL state, and detail drawer.
2. Database route with query, facets, deterministic rows, cursor pagination,
   selected columns, detail surface, bounded CSV export, and release context.
3. Public one-hop graph connections with exact/inferred/high/medium/low labels,
   explanations, contradictions, safe source references, filters, explicit
   estimate disclaimer, and a bounded selectable graph visualization paired
   with an accessible edge list.
4. Methodology/ethics links, accessible loading/empty/error states, share links,
   and privacy-aware actions.

## Later, not a launch blocker

- multi-hop graph traversal or an unrestricted graph workspace;
- heatmaps and animated density storytelling;
- full history timelines and record-level evidence hashes;
- lazy APHIS report detail until a V2 public endpoint is released;
- bulk snapshot downloads beyond the bounded CSV contract;
- device geolocation, accounts, comments, submissions, and social features;
- street view and historical satellite comparisons until provider contracts are
  evaluated;
- a flagship narrative scale story as a separate product surface.

These cuts keep the two core jobs coherent. They are not declarations that the
features lack value.

## Build order

### Phase 0 — Contract gate

- Treat the implemented graph routes and DTO as normative: use
  `/api/v2/graph/connections`, `/api/v2/graph/entities`, and
  `/api/v2/graph/entities/{entity_id}/neighborhood`, with the current field
  names and a single `confidence_band` query value.
- Confirm exact/inferred edge publication, suppression, profile separation, and
  public-zero behavior where the release has no eligible edges.
- Generate TypeScript types from the canonical contract or enforce drift checks.
- Add an explicit contract-gap gate for public evidence, inspection/event,
  source-record, organization-detail, and all-record search endpoints. The
  initial production build must use existing facility/location APIs and public
  facility/organization graph summaries only; unsupported record fixtures are
  design coverage, not a promise of working production routes.
- Link every frontend contract gap to `docs/PRODUCT-READINESS.md`, which remains
  the sole product readiness tracker.

### Phase 1 — Shell and data primitives

- Implement route shell, release context, request/error model, URL state,
  cancellable client, and accessible status announcements.
- Add typed repositories for list, facets, detail, export, and graph.
- Keep global search semantics distinct from the current implementation scope:
  disclose supported facility/location fields until the record-index contract
  exists.
- Build fixture scenarios from the representative matrix before visual polish.

### Phase 2 — Map and Database skeletons

- Implement semantic list/table first, then map adapter.
- Benchmark Leaflet/MapLibre candidates against the synthetic scale fixture,
  including exact/coarse visual strata and vector/satellite switching.
- Add filters, precision grammar, clusters, global search versus viewport query,
  and list/map synchronization.

### Phase 3 — Shared records, detail, and public graph

- Add shared record detail composition, canonical SEO URL rules, provenance,
  limitation language, graph canvas plus edge list, and endpoint navigation for
  the implemented facility/organization capabilities. Gate evidence,
  inspection/event, source-record, and community pages on their future public
  DTOs instead of shipping disconnected fixtures.
- Test exact, all inferred confidence bands, contradictions, suppression, and
  no-connection states across facility, organization, evidence, event, and
  source-record fixtures.

### Phase 4 — Quality and polish

- Keyboard/screen-reader pass, 320px/200% pass, reduced motion, localization,
  source-link safety, export scope, visual regression, and performance budgets.
- Verify satellite/provider disclosure, canonical metadata/sitemap behavior, and
  English-only message-key architecture.
- Test shared URLs across release/profile changes and suppression updates.

## Definition of frontend readiness

- All API fields are typed and capability statuses are honest.
- Map and Database answer their distinct questions without duplicate hidden
  clients.
- A user can always reach a semantic list alternative to the map.
- Public graph is available only through release-scoped public DTOs.
- Every UI state in `ui-state-matrix.json` has a fixture/test path.
- 100k/150k scale tests meet agreed budgets or document a bounded limitation.
- Accessibility, privacy, content, and export review pass before publication.
