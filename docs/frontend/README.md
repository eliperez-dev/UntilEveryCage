# V2 frontend design authority

Status: canonical V2 design guidance, with implementation under `frontend/`.
The V1 behavior inventory remains a migration reference, not a visual constraint.

## Active implementation routes

The production map follows this chain, including in a public container build:

```text
frontend/src/app/App.svelte
  → design-lab/DesignLab.svelte (data mode: public-release)
    → design-lab/variants/field/Field.svelte
      → design-lab/components/MapSurface.svelte
```

The `design-lab` folder name does not make these components preview-only.
Database and full-page records use `app/PublicDatabase.svelte` and
`app/PublicRecord.svelte`. Trace imports and the selected data mode before
changing a renderer; a similarly named layer helper may have no active caller.
Acceptance must exercise the public built frontend, not only a development
route or fixture mode.

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

The maintainer's 2026-10-24 navigation revision uses five direct destinations:
`Map, Database, API | Contribute, About`. Tools retains release selection.
Contribute opens Add a facility by default, with visible task links to switch
the form, plus submission tracking, community browsing and project/support links.
Only offer community browsing when a published community release is available;
submission intake is a separate capability. Database opens Browse records.
API combines full-release CSV downloads, paginated JSON, release IDs and the
self-hosted Swagger explorer. About combines the project manifesto, sources
and methods, help, and common questions in one page. Old informational and
download routes remain compatible aliases. Data access requires a published
release, independently of the local preview or submission pilot.
These links must appear
consistently in the public shell and local preview; following them must preserve
the selected preview context. Private submission forms use ordinary language;
publication warnings belong on public unreviewed community results. Contribute
is a direct header link. Keep the primary links compact on desktop and touch
screens without duplicating the consolidated pages in hover menus.
State that the code is open source and provide an
explicit GitHub path for code contributions on Overview and Contribute. Use
the same styled masthead on all pages. Informational pages use compact type,
short copy and modest spacing rather than oversized editorial sections.

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
- The current public client is English-only; a complete V2 localization system
  is not implemented. Multilingual UI is required before launch, after the
  targeted cleanup checkpoint. Spanish is the first bounded implementation,
  followed by German, French, Italian, Dutch and Danish. Keep source names and
  evidence in their original language and domain rules independent of locale.
- The V1 de/en/es/fr locale implementation is a historical migration reference,
  not proof that V2 language switching works. Product-level language and
  country-coverage gates live in `docs/PRODUCT-READINESS.md`.
