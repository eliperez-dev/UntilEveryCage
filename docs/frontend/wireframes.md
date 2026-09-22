# Annotated documentation wireframes

These are documentation wireframes, not implementation markup. They describe
hierarchy and behavior; spacing and visual tokens are defined separately.

## Desktop Map (1440px)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ UEC                         MAP   DATABASE   Methodology  [release ▾]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ [ Search a place, facility, organization, or source                         ] │
│                                                                             │
│ ┌───────────────┐  ┌──────────────────────────────────────┐ ┌─────────────┐ │
│ │ RESULTS       │  │                                      │ │ FILTERS     │ │
│ │ 1,248 visible │  │              MAP CANVAS              │ │ Categories  │ │
│ │               │  │   cluster / exact / city / controls │ │ Location    │ │
│ │ Facility row  │  │                                      │ │ Precision   │ │
│ │ Facility row  │  └──────────────────────────────────────┘ │ Confidence  │ │
│ │ Facility row  │  ┌──────────────────────────────────────┐ │ [apply]     │ │
│ │ ...           │  │ coverage • release • partial status │ └─────────────┘ │
│ └───────────────┘  └──────────────────────────────────────┘               │
│                    DETAIL DRAWER (only when selected)                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

Annotations:

- The list is keyboard reachable before the map controls and mirrors the
  current viewport/query set.
- The map never loads all 100k facilities into the browser.
- Filter changes are transactional from the user's perspective: stale results
  are not presented as current; loading state preserves the last valid context.
- The coverage strip says “1,248 in this loaded result set” rather than implying
  global completeness.
- The detail drawer overlays the map without changing the canonical URL; the
  URL always changes to `/locations/{id}` plus encoded context.

## Desktop Database (1440px)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ UEC                         MAP   DATABASE   Methodology  [release ▾]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ [ Query... ] [Filters 3]                         [Export ▾] [Share]        │
│ 1,248 matching rows • official profile • release 2026-09 • cursor page     │
├──────────────┬──────────────────────────────────────────────────────────────┤
│ FACETS       │ Name / place       Category   Precision  Lifecycle  Updated │
│ Country      │─────────────────────────────────────────────────────────────│
│ Category     │ Facility A         Slaughter  Exact      Observed   2026-09 │
│ Precision    │ Facility B         Processing City       Unknown    2026-08 │
│ Confidence   │ Facility C         Lab        Unmapped   Not seen   2025-11 │
│ Source       │ ...                                                         │
│              │ [previous]                              [next cursor]        │
└──────────────┴──────────────────────────────────────────────────────────────┘
```

Annotations:

- Row click opens the shared detail surface; Enter does the same and Space
  preserves normal table semantics.
- Column labels and sort state are announced. Sort order is deterministic and
  cursor-compatible; the client never pretends a page is the full dataset.
- Export is explicit about release, profile, filters, row bound, and whether the
  downloaded set is the visible page or a server-generated bounded result.

## Detail surface

```
┌───────────────────────────────────────────┐
│ [close] Facility name       [share]       │
│ Category • country / city • lifecycle     │
│ Location: city-level approximation        │
│                                           │
│ OVERVIEW                                  │
│   map thumbnail or “no publishable point” │
│ EVIDENCE                                  │
│   source • dates • release • provenance   │
│ CONNECTIONS (public graph)                │
│   Exact  ─ source-supported               │
│   Inferred · medium  0.64                  │
│   signals / contradictions / sources      │
│ LIMITATIONS                               │
│   what this record does not establish     │
└───────────────────────────────────────────┘
```

The probability disclaimer appears immediately above the first inferred edge,
not only in a methodology page. “Inferred” never becomes “owned by,” “same as,”
or “part of” without the source assertion that supports that wording.

## Tablet (768px)

- Header keeps Map/Database visible and moves secondary links into a menu.
- Map uses a 40% result rail and 60% map at landscape; portrait switches to map
  with a bottom result sheet.
- Filters open as a full-height sheet with a persistent Apply/Cancel footer.
- Detail replaces the result sheet and supports a visible Back control.
- Database facet rail becomes a sheet; table keeps only identity, category,
  precision, lifecycle, and connection indicator columns.

## Mobile (320px minimum)

- Map canvas remains the first visual; result list is a bottom sheet with a
  count and one-line rows.
- Search is full-width and always available above the map.
- Filters open as a modal sheet with grouped disclosures; no horizontal
  scrolling is required for any control.
- Detail is a full-screen route with sticky title/back/share controls.
- Database becomes stacked result cards with an accessible table-like header;
  complex facets are sequential disclosures, never hover menus.
- A cluster or city/coarse result opens a clear summary before any individual
  selection is offered.

