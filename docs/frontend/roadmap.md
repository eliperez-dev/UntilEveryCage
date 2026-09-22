# Frontend roadmap: public now, later, and deliberately open

This roadmap preserves ideas from the V2 proposal and maintainer review without
turning every attractive feature into an MVP dependency. The product remains
two primary destinations—Map and Database—with shared record detail pages.
It is a subordinate frontend feature backlog, not a second product readiness
tracker. The single source of truth remains
[docs/PRODUCT-READINESS.md](../PRODUCT-READINESS.md); each item below should be
linked to a readiness milestone or gap there.

Integration must add or maintain a single tracker link from the frontend
milestone in `docs/PRODUCT-READINESS.md` to this file. The link is the backlog
relationship; status, completion, and release gates belong in
`PRODUCT-READINESS.md`, not here.

## MVP / first public frontend

- Dark, minimal, English-only shell with translation-ready keys and locale
  architecture.
- Global database search distinct from bounded map viewport queries, initially
  limited to the currently supported public facility/location fields and
  visibly labelled as such.
- MapLibre benchmarked against the V1 Leaflet path; exact pins, city/coarse
  area/halo encodings, clusters, synchronized accessible list, and stable URLs.
- Neutral/vector basemap, with satellite as a selectable major view when a
  provider is configured and disclosed.
- Database facets, deterministic table, cursor pagination, bounded export, and
  named release/profile context.
- Shared detail architecture for every public record family; MVP production
  routes are gated to record types with public DTOs (currently facility/location
  detail plus facility/organization graph summaries).
- Public one-hop graph visualization plus accessible edge list for implemented
  facility/organization graph entities: selectable nodes/edges, public
  exact/inferred high/medium/low confidence, signals, contradictions, source
  references, and persistent disclaimers. Other record families activate after
  their public DTO contract is closed.
- SEO-safe record metadata, canonical links, release-aware sitemap, and honest
  completeness language.
- Accessible loading, empty, restricted, suppressed, stale, and failure states.

## Near-term enhancements

- Better custom facility pins after the V1 pin family has served as a baseline.
- Heatmaps with separate exact/coarse layers, explicit denominator/kernel, and
  sparse-country validation.
- Additional map data layers and comparison controls.
- A richer bounded graph canvas with relationship filtering and map-drawn edges
  from a selected facility.
- Street View provider integration for eligible exact coordinates, subject to
  provider availability, cost, privacy, and licensing.
- Historical satellite imagery comparison where a provider such as Esri Wayback
  supplies usable coverage and terms.
- Full public observation/history timelines, record-level evidence hashes, and
  richer source-document pages as backend contracts become public.
- Public evidence, inspection/event, source-record, and all-record search
  contracts, followed by their canonical pages, when the readiness tracker
  records those backend gaps as closed.
- Additional language bundles after the English MVP proves the message-key and
  layout architecture.

## Ambitious visualization work

- MapLibre globe projection / 3D globe view for global orientation.
- Time-aware satellite/history comparisons.
- Density, activity, and source-coverage layers with explicit semantics.
- Multi-hop graph exploration or a dedicated graph workspace, only after
  one-hop graph use demonstrates that it helps rather than confuses.
- GPU/worker graph layout for bounded subgraphs and shareable graph views.

## Community and contribution infrastructure

- Isolated intake for user tips, evidence, facilities, and corrections.
- Abuse/rate controls, consent and privacy screening, moderation queues,
  provenance, submitter communication, and audit history.
- Separate community profile/dataset with an explicit warning and no automatic
  promotion, merge, precise geocoding, graph publication, or release inclusion.
- Curated promotion workflow that creates source-qualified records and keeps
  the original submission linked but distinct.

## Explicit non-goals for the initial build

- No bright social feed, comments, accounts, gamification, or shock imagery.
- No fake centroid pins for facilities lacking exact coordinates.
- No claim that graph lines prove ownership, identity, wrongdoing, or a complete
  supply chain.
- No promise of global Street View or historical imagery coverage.
- No silent mix of profiles, releases, or community intake with the curated
  public dataset.

Every roadmap item should eventually be attached to a capability status in the
backend/frontend matrix and to a named release or milestone. The absence of a
feature from MVP is a sequencing decision, not deletion of the idea.
