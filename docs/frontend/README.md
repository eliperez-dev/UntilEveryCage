# Current V2 frontend instructions

**Owner:** project maintainer. This is the single current frontend specification.
The [product roadmap](../PRODUCT-READINESS.md) owns scope/readiness; this guide
owns approved behavior and copy. Do not rebuild from deleted wireframes or old
Git versions. The V1 contract is a migration reference, not V2 design authority.

## Implementation and references

The public map follows:

```text
frontend/src/app/App.svelte
  -> design-lab/DesignLab.svelte (public-release)
    -> design-lab/variants/field/Field.svelte
      -> design-lab/components/MapSurface.svelte
```

The folder name does not make it preview-only. Database and full record pages
are `app/PublicDatabase.svelte` and `app/PublicRecord.svelte`. Trace active imports.
Technical setup/tests: [frontend/README.md](../../frontend/README.md).
Wire contracts: [API index](../api/README.md), not duplicate frontend DTO docs.
[V1 behavior inventory](v1-behavioral-contract.md) and its JSON retain tested
migration requirements. The [capability matrix](capability-matrix.json) and
[UI-state matrix](ui-state-matrix.json) are legacy design/test references:
where their prose differs, this guide owns current UI instructions and current
API schemas own supported fields. They are not additional roadmaps.

## Layout and navigation

- Compact, serious, data-driven interface. No unsolicited redesign, oversized
  cards, decorative labels, glow, filler or large empty spaces.
- One centered navigation group: `Map Database API | Contribute About FAQ`.
  Brand/logo left, Tools right; all six destinations remain usable on mobile.
  No old hover-subpage navigation, disabled account placeholder or extra header strip.
- Release selection/history and diagnostics belong in Tools, not a separate
  header Release button. Display dataset dates; retain immutable IDs internally.
  Application semver comes from the backend Rust crate, not a frontend constant.
- Map is the default discovery surface; Database is the compact research table.
  Existing informational/download routes remain compatible aliases.
- Search map and Map View use the same viewport-edge spacing, surfaces, borders
  and typography. Controls must not overlap at narrow widths.
- Resize applicable panels by dragging edges, not plus/minus width buttons.
  Do not change panel layout without the maintainer's specific approval.

## Map

- Use MapLibre, the existing V1 PNG pin family and V2 taxonomy mappings.
  Do not substitute the six legacy type names for the V2 classification model.
  Processing is grey; do not invent approval for an undocumented palette.
  Preserve current category meanings until the maintainer agrees a change.
- Default cluster radius is 30 px. Clusters group geographically, not into a
  visible square grid. Exact and approximate records participate in clustering;
  do not make areas disappear between zoom levels or clear valid markers while
  replacement data/index work settles.
- A single approximate record uses the regular category pin, an accessible
  approximation cue and no cluster-style `1`. Do not flash fallback dots.
  On selection/inspection, show a red geographic area 500 metres across
  (250-metre radius), not a fixed-pixel circle or invented confidence interval.
  Use supported source extent where available. No permanent approximation legend.
- Street/Satellite selector and adjacent 2D/3D toggle form one compact Map View.
  Directly below: `Right-mouse to rotate / Left-mouse to pan`.
  No separate hint banner or white MapLibre compass/pitch control on the main map.
- Native terrain is lazy, true-scale and has a usable flat fallback.
  Keep provider attribution; changing style/camera must not rebuild facility data.
- Clicking a real pin, PNG, cluster or search result must work on cold load.
  Closing detail with X, Escape or Back leaves the focused camera in place.
  Preserve allowlisted camera, style, selection and release context on navigation.
  Public URLs omit fixture parameters such as `scenario=default`.
- Unmapped records stay searchable without invented map points. Do not turn an
  approximate location into exact directions or a street-address claim.

## Search and Database

- Search the released database, not only the visible viewport or loaded page.
  Use only fields supported by the actual public endpoint; all-record-family
  search is a future contract, not an implied feature.
- Country, source and activity/category filters use the same scope as results.
  Provide Clear filters, query totals distinct from loaded-page counts, and
  usable loading/error states without a map-covering loading popup.
- Debounce/cancel stale requests; preserve input and pagination semantics.
  OR within a filter dimension, AND between dimensions.
- Browse-record links open the full facility page directly. Do not restore
  the intermediate database preview panel.
- API offers full-release CSV, explicitly bounded exports, paginated JSON and
  the self-hosted Swagger explorer. Do not silently crawl the whole database
  in the browser to render a map or open a facility.

## Facility details and connections

- Full page order: facility name and chain-icon Copy facility link action;
  Location facts; single-record map; activities and remaining facts.
  No separate copy-record-ID button or repeated Record Evidence heading.
- Map detail has an `Open facility page` link, selected-release context and
  close control. It fills the mobile viewport with scrollable content.
- Full mapped records have `Open in Map`, centering/selecting that facility
  in the same release. Unmapped records have no location map/action.
- Single-record previews use the existing providers/pins: source/exact
  satellite zoom 15; approximate street zoom 9. Do not fetch the global point
  projection for these previews or invent an address from a locality.
- Show the broad category once, then distinct human-readable activities.
  Source classification is inline, not a disclosure. Format underscores and
  technical activity labels; retain original values in data. Show all
  affirmative species/activities and supported slaughter/product estimates.
  Use `animals`, not `head`, in presentation.
- Group available address/locality, coordinates, source method/provider and
  recorded confidence in Location. Label native points
  `Source-provided coordinates`; do not invent confidence or validation.
- Hide unknown lifecycle and internal taxonomy/crosswalk versions from UI.
  Do not hide useful original classifications or source evidence.
- Exact and inferred connections remain public and filterable at all available
  confidence bands. Use `Exact source`, `Inferred`, and `Source` for the
  source-assertion method. Keep real evidence/signals accessible, not repeated
  general disclaimer paragraphs. No human-confirmed connection state.
- A loaded record with no connections shows `None`, without Relationship or
  Confidence controls. Keep controls when filters caused an otherwise nonempty
  list to have no matches. Loading, errors and empty results remain distinct.
- Use only public graph routes and supported entity mappings. An organization
  summary does not gain a fabricated facility page. A canvas limit or API page
  bound is not a graph storage cap.
- APHIS controls appear only for relevant APHIS records, fetch on request and
  retain error/retry states. Search-page metadata references are not full
  inspection/annual/exception report files; do not claim missing years exist.

## Contribution behavior

Contribute opens Add a facility; visible task links switch among facility,
evidence, correction, duplicate and privacy/removal. Bug reports save into the
system and return confirmation/tracking, never an email draft.
Existing-record actions preselect their target. Reuse normal category pins
and taxonomy choices in location intake.

Use one Track submission link, with its capability in the fragment and status
credentials sent in a POST body. Accounts, uploads, automated email and receipt
recovery are not implemented. Public community browsing is offered only for an
eligible published community release; intake never automatically changes the
curated map, graph or counts. The [contribution contract](../governance/user-submitted-data.md)
and [production runbook](../deployment/production-operations.md) own operational details.

## Exact copy and informational pages

Use supplied wording verbatim. No em dashes in authored visitor copy, internal
candidate/projection jargon, repeated category summaries, unsolicited warning
blocks or polite filler. Preserve source-native evidence, provider attribution
and required public unreviewed-community context.

- About uses the supplied V1 manifesto. Counter is on the right on desktop,
  stacked on mobile. Exact title: `Animals Killed Since You Opened This Page`.
  No subtitle; all 18 animal groups form one vertical list at every width.
  Update from elapsed time around 30 times per second, isolated from map rendering;
  respect reduced motion and hidden tabs.
- Rates/source notes remain in the model. Do not restore counter Source and
  method or About Sources and methods sections, or relocate them as replacement copy.
- The closing `Until Every Cage is Empty` heading is followed by the existing logo.
- Footer opens `An independent, open-source, ad-free project.` No feedback invitation.
  Credit `Counter Adapted from ADAPTT.`, linking ADAPTT to
  `https://www.adaptt.org/`. Retain project/support/code links and distinct
  software/data licences; do not restore obsolete country/version claims.
- FAQ explains the data path, contribution questions and support. Its current
  data-path paragraph is: "Government datasets are collected, cleaned and
  standardized, with links back to their sources. Address lookups add
  coordinates, and matching connects related records. Dated releases supply
  the map, search and downloads through a Rust API."
- No duplicate Common questions block on About or tutorial video in Help.

## Boundaries and acceptance

Release/profile eligibility and current restrictions apply to UI, APIs, caches,
history and exports. Never expose private routes/tokens/raw evidence in the
public bundle. Keep community submissions separate from curated records.
Device location is optional and is not persisted by default.

Maintain keyboard access, visible focus, reduced motion, screen-reader labels
and usable narrow/zoomed layouts. Test the actual public built route and real
approved data where available; synthetic unit/negative tests supplement, not
replace, real-data acceptance.

English-only dark UI is the current state. Languages, light/dark mode and
persistent cluster-index reuse remain launch requirements in the roadmap,
not features this guide claims implemented. Do not reopen map-engine selection
or rewrite approved visual behavior while implementing them.
