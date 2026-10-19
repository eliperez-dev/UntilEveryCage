# Frontend decisions and remaining implementation choices

The maintainer has made the product-direction decisions below. Remaining
choices are implementation/provider decisions, not reasons to reopen the basic
information architecture.

## Decided

1. **Public graph:** public, release-scoped, read-only graph is a core product
   feature. Exact and inferred edges remain visible; inferred edges are clearly
   banded high/medium/low, filterable, and accompanied by evidence/signals,
   contradictions, provenance, and an estimate disclaimer. A bounded
   interactive graph plus accessible edge list belongs on shared record detail.
2. **Shared records:** facilities, organizations, evidence, inspections/events,
   source records, and future community submissions share stable identity and
   detail architecture. Every eligible public record receives a canonical URL;
   only spatial records appear on the map.
3. **Search:** the prominent search searches the entire released database;
   viewport results are a separate map query.
4. **Location grammar:** exact points and city/coarse areas use different
   same-map visual encodings. No fake centroid facility pins. Heatmaps and
   other density views remain later until semantics are proven.
5. **Language:** English-only MVP with translation-ready architecture.
6. **Visual direction:** dark, minimal, serious, data-driven, restrained, and
   non-flashy. Reuse V1 pins initially; maintain a replacement path.
7. **Imagery:** satellite is a major selectable map view. Street View and
   historical imagery are optional/provider-dependent, with disclosure.
8. **Community:** future submissions/tips/corrections are isolated untrusted
   intake, never automatic promotion or merge.
9. **Release identity:** public dataset labels use the release date
   `YYYY-MM-DD`, as approved on 2026-10-18. Keep immutable `release_id` and
   `manifest_sha256` separate; V2 names the product, not the dataset.

Navigation revision authorized by the maintainer on 2026-10-04: the shared
header is **Map, Database | Contribute, About**. The latest refinement makes
Contribute a direct link to Add a facility, with visible task links switching
the unified form, visibly labeled **Choose a contribution type**. About uses a
text-only menu without an arrow and contains Overview (the manifesto),
Sources & methodology, FAQ and Help. Database groups Browse records,
Downloads and API documentation, with the old About/API URL preserved.
The Help/API additions and
clearer existing-record evidence guidance were requested on 2026-10-05.
Help uses short written guides and controlled tutorial media; Swagger exposes
only the implemented public read API, with published-release access boundaries.
Country and source links are optional on facility
intake. Private forms use clear labels and concise guidance, without technical
geocoding language or repeated review badges. Public community-unreviewed
warnings and private publication gates remain required. The follow-up density
revision calls for compact type and spacing, fewer headings and shorter copy,
with the same styled masthead across all pages. Overview and Contribute make
the open-source code and GitHub contribution path explicit.

The 2026-10-05 follow-up adds a compact shared informational footer, optional
private contact email, explicit receipt copy controls and practical status
guidance. Email collection does not enable delivery or receipt recovery.
Submission ID identifies intake; Record ID identifies an existing record.
Database category selections must query the complete backing dataset, while
displayed counts describe loaded results unless the API supplies a total.
Downloads describe the actual bounded public exports, never private preview
data or an unimplemented filtered/bulk export.

The next 2026-10-05 refinement makes Database and About ordinary links to
their default pages (Browse records and Overview). Hover reveals subpages;
keyboard access and Escape dismissal remain available. Touch uses a separate
compact pages control, preserving direct title navigation without an arrow.

## Final-review refinements (2026-10-18)

The maintainer requested these launch repairs, not another redesign:

Later naming pass: identify public dataset releases by their release date
(for example `2026-10-18`), not v0/v1 version names or internal candidate IDs.
Retain immutable internal identifiers and historical lineage. This presentation
decision does not rename stored releases, change membership or approve a release.

- Use compact, readable filters with an obvious Clear all action. Options and
  counts must use the same applicable scope as map/search. Show total matches
  separately from the loaded page; 100 loaded records is not a database total.
- Remove ordinary-interface governance rows, repeated internal candidate
  wording and speculative empty connection panels. Preserve real source/date/
  precision information, real connections and their confidence, backend access
  controls, and required context for public unreviewed community claims.
- Remove the disabled account placeholder, Help video, redundant Muted style
  and extra header strip. Street and Satellite remain available. Constrain the
  release selector to its menu instead of exposing an overflowing identifier.
- Use the existing V1 pin artwork by default, preserving clicks and approximate
  location grammar. Do not replace V2 taxonomy with V1 facility-type categories.
  The maintainer identifies an explicit V2 mapping specification from the
  taxonomy work; its separate colour specification has not yet been located.
  Palette reconciliation remains open. Neither the older visual brief nor
  current presentation-code hex values should be represented as that approval.
- Write concise visitor copy without em dashes. This does not authorize
  rewriting retained source-native evidence. Explain receipt status lookup in
  ordinary language, without repetitive lost-receipt warnings or a claim that
  unsupported recovery exists.

## Remaining implementation decisions

### Owner review queued after corrected-dataset deployment

Do not treat these notes as implemented or begin their repair sprint before
the corrected dataset is live and the sprint is approved:

- Darken the header to a deeper grey and agree the V2 category palette with
  the maintainer during the next visual pass.
- Make research columns and panels resizable. Rename Record Evidence to
  Facility details; make the detail panel draggable, resizable and collapsible,
  with viewport limits, reset and usable keyboard/mobile behaviour. The intended
  feeling is a compact research workbench, not a sparse dashboard.
- Measure and reduce database, facet and detail latency against the approved
  real release. Current owner observations were about ten seconds for database
  opening and three seconds for detail. Show total matches separately from the
  loaded page; do not introduce unrelated map-transfer optimizations.
- Restore all five contribution flows in production: facility, evidence,
  correction, duplicate and privacy/removal. The existing forms were not deleted;
  the public build does not expose the development-only intake backend. This
  requires a production intake path with a separate restricted write connection,
  abuse limits, status lookup and maintainer review, not a pilot-flag flip or
  automatic publication into the curated dataset. Accounts remain out of scope.
- Rewrite Overview, Sources & methodology, FAQ and Help in short, accurate
  visitor language, without internal pipeline terminology or em dashes. Remove
  misleading submission/status instructions until the corresponding workflow
  actually works. The maintainer may supply the final editorial copy.

The next sprint must verify all five contribution types end to end on the
production-shaped setup, retained receipt/status behaviour, read-only release
access, real-data latency, cold/warm navigation and owner-reviewed panel behaviour.
Finish with integration, exact-head CI and cleanup before claiming completion.

10. **Map engine:** benchmark MapLibre/WebGL against Leaflet; MapLibre is the
    preferred candidate, but measured transfer, pan, memory, accessibility, and
    provider behavior decide.
11. **Coarse encoding:** compare bounded-area, city aggregate glyph, halo, and
    list-first variants at dense/sparse zooms; retain the clearest honest one.
12. **Basemap providers:** select vector and satellite providers after checking
    attribution, licensing, API keys, privacy, cost, and offline/test behavior.
13. **Graph layout:** MVP uses a bounded radial/layered layout and a required
    accessible edge list. A force layout is deferred until a bounded usability
    test justifies it; never remove the edge-list alternative.
14. **Profile exposure:** official remains the default; decide when secondary or
    community profiles become explicit opt-in public routes.
15. **Export:** bounded server export is MVP; decide later bulk release snapshot
    UX when the named release workflow is exposed.

## Defaults for implementation

Keep the public graph visible from day one, put it below the record's
evidence/precision context, and ship the canvas with a list alternative. Let
measured performance and provider terms choose the technical map and imagery
stack. Do not let optional 3D, heatmap, or provider integrations delay the core
Map/Database/Record experience.
