# MVP cuts and implementation sequence

## MVP surface

The first build includes:

1. Map route with server-backed search, bbox/radius loading, exact/city/unmapped
   semantics, synchronized accessible list, category/location/precision/
   lifecycle filters, clusters, stable URL state, and detail drawer.
2. Database route with query, facets, deterministic rows, cursor pagination,
   selected columns, detail surface, bounded CSV export, and release context.
3. Public one-hop graph connections with exact/inferred/high/medium/low labels,
   explanations, contradictions, safe source references, filters, and explicit
   estimate disclaimer.
4. Methodology/ethics links, accessible loading/empty/error states, share links,
   and privacy-aware actions.

## Later, not a launch blocker

- multi-hop graph traversal or a graph canvas;
- heatmaps and animated density storytelling;
- full history timelines and record-level evidence hashes;
- lazy APHIS report detail until a V2 public endpoint is released;
- bulk snapshot downloads beyond the bounded CSV contract;
- device geolocation, accounts, comments, submissions, and social features;
- satellite base layer and advanced map-style customization;
- a flagship narrative scale story as a separate product surface.

These cuts keep the two core jobs coherent. They are not declarations that the
features lack value.

## Build order

### Phase 0 — Contract gate

- Land the release-scoped public graph projection and machine-readable DTO.
- Confirm exact/inferred edge publication, suppression, profile separation, and
  public-zero behavior where the release has no eligible edges.
- Generate TypeScript types from the canonical contract or enforce drift checks.

### Phase 1 — Shell and data primitives

- Implement route shell, release context, request/error model, URL state,
  cancellable client, and accessible status announcements.
- Add typed repositories for list, facets, detail, export, and graph.
- Build fixture scenarios from the representative matrix before visual polish.

### Phase 2 — Map and Database skeletons

- Implement semantic list/table first, then map adapter.
- Benchmark Leaflet/MapLibre candidates against the synthetic scale fixture.
- Add filters, precision grammar, clusters, and list/map synchronization.

### Phase 3 — Detail and public graph

- Add shared detail surface, provenance, limitation language, and graph rows.
- Test exact, all inferred confidence bands, contradictions, suppression, and
  no-connection states.

### Phase 4 — Quality and polish

- Keyboard/screen-reader pass, 320px/200% pass, reduced motion, localization,
  source-link safety, export scope, visual regression, and performance budgets.
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

