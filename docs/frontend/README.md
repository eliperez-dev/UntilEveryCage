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

The maintainer's latest 2026-10-24 navigation revision uses six direct destinations:
`Map, Database, API | Contribute, About, FAQ`. Keep all six links in one compact
group with a fixed separator; do not spread the two groups across the header.
Center the six-link group in the masthead, with brand/logo left and Tools right;
do not push the navigation to the left. Preserve usable responsive navigation.
Tools retains release selection and map diagnostics.
Contribute opens Add a facility by default, with visible task links to switch
the form, plus submission tracking, community browsing and project/support links.
Only offer community browsing when a published community release is available;
submission intake is a separate capability. Database opens Browse records.
Selecting a result opens its full facility page directly, without an intermediate
preview panel. Mapped facility pages include an "Open in Map" action that centers
and selects that facility in the same release.
API combines full-release CSV downloads, paginated JSON, release IDs and the
self-hosted Swagger explorer. About restores the maintainer's supplied V1
manifesto with an 18-category estimate counter in a right-hand desktop column,
stacked on mobile. Its modeled visible updates run around 30 times per second
using elapsed time. The visible counter heading is exactly "Animals Killed Since
You Opened This Page", with no subtitle. Its 18 animal rows form one vertical
list at all widths, not a two-column grid. Rates and source notes remain in the owning model;
do not restore the removed Source and method disclosure. About contains the
manifesto and counter, without a Sources and methods section. The closing
"Until Every Cage is Empty" heading is followed by the project's existing logo.
FAQ briefly
explains the data path: acquisition, cleaning/standardization, address matching
and connections, then dated releases serving map/search/downloads through the
Rust API. It also covers contribution questions and help/support. Do not restore
a separate counter disclaimer or substitute a framework inventory for this flow.
Do not retain a duplicate Common questions section on About. Restore the
V1-style contact/support/credits footer, but not its obsolete version or
country-coverage claims. The footer opens with "An independent, open-source,
ad-free project." Its counter credit is "Counter Adapted from ADAPTT." with
ADAPTT linked to `https://www.adaptt.org/`. Do not append a feedback invitation
or expand these credits with internal explanations. Application semver comes from the backend's Rust
crate version; dataset release dates remain independent.
Old informational and download routes remain compatible aliases. Data access requires a published
release, independently of the local preview or submission pilot.
These links must appear
consistently in the public shell and local preview; following them must preserve
the selected preview context. Private submission forms use ordinary language;
publication warnings belong on public unreviewed community results. Contribute
is a direct header link. Keep the primary links compact on desktop and touch
screens without duplicating the consolidated pages in hover menus.
The main map has no white MapLibre compass/pitch control or separate drag
instruction banner. Inside Map View, small text directly beneath the options
says "Right-mouse to rotate / Left-mouse to pan".
Search map and Map View share viewport-edge insets,
colors, border treatment and typography on desktop and mobile.
Keep the compact map-view selector and 2D/3D toggle, native
gestures, accessible button names and provider attribution. Closing
a focused facility preserves the current camera; X, Escape, browser Back and
direct-selected URLs must agree. Map/Database links preserve only allowlisted
camera, style and release context, not raw search or arbitrary query strings.
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
- Light and dark interface modes are required before launch. This is a separate
  implementation task; dark mode alone is not completion of that requirement.
