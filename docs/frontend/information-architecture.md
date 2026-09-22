# Information architecture

## Top-level model

The public product has one compact header and two primary destinations:

```
Until Every Cage     MAP        DATABASE        About / Methodology      [release context]
```

The header is not a dashboard. It should remain available without competing
with the current task. On narrow screens, Map and Database become a two-item
segmented navigation control; secondary links move into an accessible menu.

### Routes

| Route | Purpose | Primary audience | Notes |
| --- | --- | --- | --- |
| `/map` | Place-first map discovery | Everyone | Default route; accepts viewport, query, filters, profile, and selected facility state |
| `/database` | Searchable result table | Researchers, journalists | Accepts query, facets, sort, cursor, profile, and selected facility state |
| `/records/{record_id}` | Target stable detail for any public record | Everyone | Canonical SEO-friendly route in the shared-record architecture; initial implementation is enabled only for record types with a public DTO |
| `/locations/{facility_id}` | Implemented facility detail route | Everyone | Current public facility route; becomes/redirects to the canonical record route only when that contract is implemented |
| `/methodology` | Data and limitations | Everyone | Required trust destination; not a primary tool |
| `/ethics` | Privacy, safety, corrections | Everyone | Existing governing policy surfaced plainly |

No `/graph` top-level destination is needed for MVP. The graph is a capability
within a facility detail page and a Database relationship filter. A later
dedicated graph workspace may be added only if real use demonstrates that one-
hop detail is insufficient.

## Shared shell

Every public route has:

- a concise site identity and two primary destinations;
- a persistent release/profile/coverage notice that can expand for details;
- a search affordance that routes to the appropriate surface rather than
  silently changing contexts;
- a methodology and ethics path;
- a non-color-only status vocabulary;
- a stable page title and shareable URL;
- no device-location permission prompt on first load.

## Map page

### Default question

“What documented facilities are around this place?”

### Regions

1. **Search header**: town, postcode, facility, organization, or source term.
2. **Map canvas**: primary visual field; points/clusters are fetched by viewport.
3. **Result rail**: semantic synchronized list of current viewport/query results.
4. **Filter tray**: collapsed by default; category, country/region, precision,
   lifecycle, source/profile, and graph filters.
5. **Coverage strip**: visible count, loaded-page status, release/profile, and
   honest caveats.
6. **Detail surface**: drawer on desktop, bottom sheet on mobile, split/full
   page for direct stable URLs.

The map and list are peers. A point never exists only as a visual marker, and a
list item never loses the ability to locate its map context when coordinates are
eligible. The intended global search bar searches the entire released database
(all record types and eligible fields), not merely the currently visible
viewport. Until the all-record index contract exists, the UI must disclose the
current facility/location search scope. Viewport loading is always a separate
bounded query used only to draw the map and its synchronized result rail.

## Database page

### Default question

“Show me the records and connections that meet these conditions.”

### Regions

1. **Query bar**: debounced text search with explicit fields in helper text.
2. **Facet rail**: country/region, category/activity, source origin, precision,
   lifecycle, profile, and relationship filters.
3. **Result table**: stable sort, cursor pagination, keyboard row navigation,
   column chooser with a restrained default set.
4. **Scope toolbar**: release, profile, visible/loaded result context, export.
5. **Detail surface**: shared with Map, with Overview, Evidence, Connections,
   and Limitations sections.

The database should feel like a calm research instrument: dense enough for
comparison, but not a spreadsheet dump. Advanced controls are progressive and
never hidden behind hover-only interactions. In the first implementation, the
table's production scope must match the current public location/search DTO;
evidence, event, source-record, and community rows remain design targets until
their public record-index contract exists.

## Shared record detail composition

The shared detail surface has this order for facilities, organizations,
evidence, inspections/events, source records, and later community records. In
MVP, only record types with a public DTO may use a production route; the others
are design fixtures and contract backlog, not hidden promises:

1. **Identity**: record type, canonical name/title, category/activity, place,
   lifecycle or event status.
2. **Location**: exact/city/coarse/unmapped label when spatial, map context,
   precision limitation. Non-spatial records say clearly that they have no map
   location.
3. **Evidence**: source origin, source name/link, retrieval/observation fields,
   release/profile, review/privacy/approval labels available in the DTO.
4. **Graph**: an interactive one-hop graph view plus accessible edge list. Nodes
   and edges are selectable; selecting an edge opens its relationship,
   confidence, signals, contradictions, provenance, and disclaimer; selecting a
   node previews it and opens that record's detail page. A facility node can
   also highlight its eligible map position. The list remains the authoritative
   accessible alternative to the visualization.
5. **Actions**: copy stable URL, share, export selected eligible fields, and
   directions only for eligible exact public coordinates.
6. **Limitations**: explicit unknowns and what the record does not establish.

Sections with no data are not fabricated; they show “Not available in this
release” with a reason when the contract provides one.

## Information scent and progressive disclosure

- Map labels answer **where** and **what type**.
- List rows answer **which record** and **why it is included**.
- Detail answers **what is known**, **where it came from**, and **how strong the
  connection is**.
- Methodology answers **how the system works** and **what it cannot claim**.

Do not put source IDs, confidence math, or raw matching signals in the default
hero area. Do not bury precision or publication warnings in a tooltip. Do not
make the graph canvas the only way to inspect a relationship.

## Record discoverability and SEO

Every eligible public record gets a deterministic canonical URL, server-rendered
or statically renderable title/description metadata, Open Graph/Twitter metadata,
JSON-LD appropriate to the record type, and inclusion in a release-aware sitemap
when publication policy permits. Metadata must describe the record as a
source-traceable entry, not imply global completeness or current operation.
Suppressed/restricted records do not leak through sitemap entries, search
suggestions, graph neighborhoods, structured data, or not-found wording.

The canonical URL is based on a stable opaque record ID:
`/records/{record_id}`. An optional readable slug may be appended for display or
sharing, but the canonical metadata URL remains the ID-only form so contextual
query parameters and slug changes do not create separate SEO pages. ID
resolution prevents renames from breaking links. Current facility
`/locations/{id}` links remain supported until a record-route contract is
implemented.
