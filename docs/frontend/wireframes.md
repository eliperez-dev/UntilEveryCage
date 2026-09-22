# Annotated documentation wireframes

These are documentation wireframes, not implementation markup. They describe
hierarchy and behavior; spacing and visual tokens are defined separately.

## Desktop Map (1440px)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ UEC                         MAP   DATABASE   Methodology  [release ▾]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ [ Search the entire database: place, facility, organization, evidence... ] │
│                                                                             │
│ ┌───────────────┐  ┌──────────────────────────────────────┐ ┌─────────────┐ │
│ │ RESULTS       │  │                                      │ │ FILTERS     │ │
│ │ 1,248 in view │  │       MAP CANVAS: vector / satellite │ │ Categories  │ │
│ │               │  │   cluster / exact / coarse / controls│ │ Location    │ │
│ │ Facility row  │  │                                      │ │ Precision   │ │
│ │ Facility row  │  └──────────────────────────────────────┘ │ Confidence  │ │
│ │ ...           │  ┌──────────────────────────────────────┐ │ [apply]     │ │
│ │               │  │ coverage • release • partial status │ └─────────────┘ │
│ └───────────────┘  └──────────────────────────────────────┘               │
│                    DETAIL DRAWER (only when selected)                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

Annotations:

- The search bar is global by product intent. During the initial implementation
  its helper text discloses the currently supported facility/location fields
  until the all-record index contract exists; a spatial result offers “show on
  map.”
- The list is keyboard reachable before the map controls and mirrors the
  current viewport/query set.
- The map never loads all 100k facilities into the browser.
- Exact records use the familiar restrained V1 pin family initially. City/coarse
  records use an area/halo/count glyph, never a fake facility pin. Mixed
  clusters disclose exact/coarse composition when available.
- The coverage strip says “1,248 in this loaded result set” rather than implying
  global completeness.
- The detail drawer overlays the map while changing the canonical URL to
  `/records/{id}` plus encoded context; an optional slug is cosmetic and
  `/locations/{id}` remains the current facility route until the record route
  exists.

## Desktop Database (1440px)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ UEC                         MAP   DATABASE   Methodology  [release ▾]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ [ Search the entire database... ] [Filters 3]       [Export ▾] [Share]      │
│ 1,248 matching rows • official profile • release 2026.09.1 • cursor page  │
├──────────────┬──────────────────────────────────────────────────────────────┤
│ FACETS       │ Name / place       Category   Precision  Lifecycle  Updated │
│ Country      │─────────────────────────────────────────────────────────────│
│ Category     │ Facility A         Slaughter  Exact      Observed   2026-09 │
│ Precision    │ Facility B         Processing City       Unknown    2026-08 │
│ Confidence   │ Evidence C         Evidence   Unmapped   Not seen   2025-11 │
│ Source       │ Organization D     Company    —          —          3 edges │
│ Relationships│ ...                                                         │
│              │ [previous]                              [next cursor]        │
└──────────────┴──────────────────────────────────────────────────────────────┘
```

Annotations:

- Row click opens the shared record detail surface; Enter does the same and
  Space preserves normal table semantics.
- Column labels and sort state are announced. Sort order is deterministic and
  cursor-compatible; the client never pretends a page is the full dataset.
- Export is explicit about release, profile, filters, row bound, and whether the
  downloaded set is the visible page or a server-generated bounded result.

## Shared record detail

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Record title • type • place/precision                         [copy URL]   │
├──────────────────────────────┬──────────────────────────────────────────────┤
│ OVERVIEW / EVIDENCE           │ CONNECTIONS                                  │
│ source, dates, limitations    │        [A]                                  │
│ map thumbnail if spatial      │       /   \  select edge for explanation     │
│                              │    [B]—[selected]—[C]                        │
│                              │      accessible edge list below             │
├──────────────────────────────┴──────────────────────────────────────────────┤
│ selected edge: A → parent organization • inferred · medium • 0.64          │
│ signals • contradictions • sources • ruleset • estimate disclaimer          │
└─────────────────────────────────────────────────────────────────────────────┘
```

The ruleset-estimate disclaimer appears immediately above the first inferred edge,
not only in a methodology page. “Inferred” never becomes “owned by,” “same as,”
or “part of” without the source assertion that supports that wording. Selecting
an edge opens its complete safe explanation. Selecting a node opens that
record's canonical page; a facility node can also highlight its eligible map
point or coarse area. For a shared-parent example, A's one-hop view shows
A → parent organization P; opening P's neighborhood is how a researcher reaches
B. The UI must not invent a direct A → B edge unless a future graph ruleset
explicitly publishes one. Non-spatial evidence and organization nodes remain
fully useful without a map position.

## Tablet (768px)

- Header keeps Map/Database visible and moves secondary links into a menu.
- Map uses a 40% result rail and 60% map at landscape; portrait switches to map
  with a bottom result sheet.
- Filters open as a full-height sheet with a persistent Apply/Cancel footer.
- Detail replaces the result sheet and supports a visible Back control.
- Database facet rail becomes a sheet; table keeps only identity, category,
  precision, lifecycle, and connection indicator columns.
- The graph canvas collapses above the accessible edge list; selecting a node
  uses the same stable route as desktop.

## Mobile (320px minimum)

- Map canvas remains the first visual; result list is a bottom sheet with a
  count and one-line rows.
- Search is full-width and always available above the map, with global scope
  explicit in its hint.
- Filters open as a modal sheet with grouped disclosures; no horizontal
  scrolling is required for any control.
- Detail is a full-screen route with sticky title/back/share controls.
- Database becomes stacked result cards with an accessible table-like header;
  complex facets are sequential disclosures, never hover menus.
- A cluster or city/coarse result opens a clear summary before any individual
  selection is offered.
- Graph visualization is bounded and secondary to the edge list; node selection
  navigates rather than creating an unbounded canvas.

