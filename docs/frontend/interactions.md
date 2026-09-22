# Interaction specification

## Search

Search is server-backed and debounced. A query is sent only after a short idle
window, is cancellable, and carries the current release/profile and filters.
The old V1 intent is preserved: facility names, DBA/organization text, animal
or activity terms, and category language should remain discoverable where the
projection exposes those fields. The UI must not claim a field is searchable
when the current endpoint does not support it.

Suggestions are a short, accessible list of real public records, not a second
data source. Each suggestion shows name, place, category, and precision. Enter
opens the first result or the full Database query; arrow keys move through the
list; Escape closes it. A no-results state explains the active scope and offers
“Search the database” rather than implying absence.

## Map queries and synchronization

The map requests a bounded bbox or radius query after a settled pan/zoom. The
client cancels or ignores stale generations. It requests only fields needed for
map/list rendering, then fetches detail on selection. The result list mirrors
the current query and uses cursor pagination for dense areas.

Map/list synchronization rules:

- Hover/focus on a list row previews its point without changing selection.
- Selection changes URL state and opens detail.
- Selecting a cluster zooms or opens a cluster summary; it does not silently
  pick one facility.
- A city/coarse point is a region signal, not a precise marker. Its visual
  encoding must not invite routing or street-level targeting.
- Unmapped records appear in Database and in the Map result rail when filters
  include them, but never as fabricated coordinates.

## Clusters, density, and city/coarse locations

The design must compare two strategies during implementation:

1. MapLibre native/source clustering or a vector-tile server cluster for
   viewport-scale points.
2. A worker-backed Supercluster-style index for a bounded client-side page.

Recommendation: use server/vector-tile clustering as the default at 100k
facilities, with a worker fallback for a bounded response. Never transfer the
global dataset to the browser. A cluster label means “public records in this
visible tile/query,” and its count is not an animal count or a completeness
claim.

City/coarse locations require a separate visual grammar:

- exact points use a restrained point symbol;
- city/coarse records use a halo or area marker with a visible “approx.” label;
- clusters show the composition of exact versus approximate records when known;
- unmapped records are represented only in the list/count context;
- heatmaps are not MVP default because they collapse precision and can look like
  a measured density claim. A later heatmap must separate exact and coarse
  strata, disclose the denominator and radius, and be tested against sparse
  countries.

## Filters

Filter groups are additive by default, with OR within a dimension and AND
between dimensions. This keeps V1 category semantics while making the rule
visible. Every applied filter appears as a removable chip and in the URL.

MVP filter groups:

- country and region/city where available;
- category/activity;
- source origin and source;
- display precision;
- lifecycle;
- relationship presence/type/confidence band;
- profile/release where the user explicitly selects them.

Facet counts are scoped to the current release/profile and active query. A facet
with no value is not silently removed; it can be explained as “not available in
this release.” Reset restores all filters and query defaults while preserving
the user's current page destination. Display preferences such as map style or
marker scale may remain separate from data reset.

## Facility detail

Detail opens from a list, point, suggestion, or stable URL. It preserves the
originating query context in a return link and uses a focus trap only when it is
presented as a modal sheet. Direct routes render a full page with the same
sections.

The primary action is “Copy link.” Source links open in a new tab with clear
attribution. Directions appear only for a public exact coordinate with an
eligible precision/review state. City/coarse and unmapped records show a
location limitation instead.

## Public graph connections

The graph is public once a release-scoped projection exists. It is not hidden
from ordinary users, but it is progressively disclosed so a casual visitor is
not overwhelmed.

Each edge row contains:

- endpoint name and category;
- `Exact` or `Inferred` type;
- inferred confidence band and numeric score when available;
- a plain-language method;
- supporting signal groups and contradictions;
- source references and observed/computed dates;
- ruleset version;
- a persistent disclaimer that inferred connections are estimates, not proof.

Confidence display:

| Band | Default language | Visual treatment |
| --- | --- | --- |
| Exact | “Source-supported connection” | strongest neutral emphasis |
| High | “Inferred · high confidence” | clear but qualified |
| Medium | “Inferred · medium confidence” | quieter, still visible |
| Low | “Inferred · low confidence” | quiet, filterable, never hidden by default |

Users can filter exact/high/medium/low and conflicting edges. No band is renamed
to “confirmed” unless the source itself asserts the relationship. The public
graph must not expose private source identifiers, raw evidence, or restricted
observations; public references are publication-safe source links/labels.

MVP graph scope is one-hop connections tied to a public facility/organization
record. Multi-hop traversal, graph canvas, and force-directed layouts are later
because they increase interpretation risk and performance cost.

## Share state

URLs encode only public, reproducible state: route, query, filters, release/
profile selection, cursor where stable, viewport, and selected facility ID.
They do not encode device location, private tokens, raw addresses, or analytics
identifiers. Copy-link success/failure is visible. A shared URL revalidates
publication and suppression on load; a stale link must fail closed or show the
current safe record state.

## Export

Export is a deliberate action with a confirmation summary:

- profile and release;
- active filters and sort;
- visible page versus server-bounded result;
- row limit and whether more pages exist;
- source/precision/confidence limitations.

CSV rows carry the same provenance, profile, warning, and graph confidence
labels as the UI. The client does not reconstruct an “all results” export by
silently crawling cursors. A later bulk snapshot may link to a release artifact
with its manifest and checksum.

## Language and accessibility

Retain the V1 language resource direction (de, en, es, fr) but do not block the
core product on translating technical source names. Language changes preserve
filters, focus, selection, and URL state. Every interactive control has a
visible or programmatic label. Reduced motion disables animated map transitions
and drawer motion. Keyboard users can reach search, filters, list, map controls,
detail sections, graph rows, and export without pointer-only gestures.

