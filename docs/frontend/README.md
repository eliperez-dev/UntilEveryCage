# V2 frontend design authority

Status: design specification for implementation planning, revised after maintainer review, 2026-09-22

This folder defines the fresh V2 frontend direction. It is intentionally
documentation-only: it contains no Svelte, HTML, CSS, JavaScript, image, or
runtime asset changes. The existing V2 preview is disposable scaffolding. The
V1 behavior inventory remains the migration baseline; it is not a visual
constraint.

## Product decision

V2 has two primary destinations:

1. **Map** — the default, quiet place-first discovery experience.
2. **Database** — the dense, research-oriented search and export experience.

The target architecture gives every public record a stable, canonical detail
URL. Facility detail is a shared drawer/split/fullscreen state, not a third
top-level destination, while organizations, evidence, inspections/events,
source records, and future community submissions use the same record model and
detail architecture. MVP production routes remain gated by the currently
implemented public DTOs.
Spatial records can appear on the map; non-spatial records remain searchable
and graph-connected without being assigned a fake point. Graph connections are
a public product feature within map detail, record detail, and database search;
they are not a separate social network or a claim of universal identity.

The product principle is **quiet on first contact, powerful when investigated**.

## Reading order

- [principles and audiences](principles.md) — **Canonical**
- [backend capability matrix](capability-matrix.json) — **Canonical** interface inventory
- [information architecture](information-architecture.md) — **Canonical**
- [wireframes](wireframes.md) — **Canonical**
- [interaction specification](interactions.md) — **Canonical**
- [UI state matrix](ui-state-matrix.json) — **Canonical** interface states
- [content, terminology, and safety](content-and-safety.md) — **Canonical**
- [visual direction and tokens](visual-direction.md) — **Canonical**
- [performance and technology assessment](performance-and-technology.md) — **Reference**
- [MVP cuts and implementation sequence](implementation-sequence.md) — **Canonical**
- [release and shared record model](release-and-record-model.md) — **Canonical**
- [future roadmap](roadmap.md) — **Reference**, subordinate to product readiness
- [maintainer approval decisions](approval-decisions.md) — **Canonical**

The normative V1 migration inventory is [v1-behavioral-contract.md](v1-behavioral-contract.md) — **Reference** for migration.
The design review explicitly includes the actual V1 implementation in
`static/app.js`, `static/modules/MapManager.js`, `SearchManager.js`,
`FilterManager.js`, `popupBuilder.js`, `ExportManager.js`, and
`translationManager.js`: marker clustering, debounced search and suggestion
behavior, category semantics, URL-restorable map state, popup/detail discovery,
exports, lazy reports, and locale behavior are migration inputs rather than
visual constraints.
The product-level readiness tracker is [../PRODUCT-READINESS.md](../PRODUCT-READINESS.md) — **Canonical**.
The roadmap in this folder is subordinate to that tracker; it must not become
a competing completion ledger.

## Non-negotiable boundaries

- Public output is release/profile scoped and suppression-aware.
- Exact and inferred graph edges are both discoverable, but a ruleset score is never
  presented as fact, ownership, universal identity, or supply-chain proof.
- Exact, city/coarse, and unmapped records are visibly distinct.
- Source origin, factual review, privacy screening, project approval, and
  publication are separate labels.
- A missing record does not prove closure or absence.
- Device location is optional and is not persisted in URLs or analytics.
- Private preview routes, raw evidence, credentials, and retained private rows
  never enter the public bundle. Public graph reads use only the release-scoped
  `/api/v2/graph/*` projection; the `/api/private/graph/*` routes remain
  operator-only. Public graph edges are intentionally discoverable, with
  exact/inferred and high/medium/low confidence shown together with their
  evidence and limitations.
- MVP is English-only, but all user-facing copy uses stable localization keys;
  domain data and rules never contain translated strings.
- The V1 behavioral contract's checked-in de/en/es/fr locale behavior remains a
  historical migration baseline. The V2 launch decision supersedes it with an
  English-only MVP while preserving translation-ready architecture.
