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
9. **Release identity recommendation:** use CalVer `YYYY.MM.N` as the human
   display convention, pending explicit maintainer approval; keep the existing
   `release_id` and `manifest_sha256` separate, and keep software/API versions
   as SemVer.

## Remaining implementation decisions

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
