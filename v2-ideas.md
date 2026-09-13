# Until Every Cage — V2 design and implementation roadmap

Status: proposed scope, ready to refine. Product names and technology choices remain proposals; the data-first priorities below reflect the developer's direction. Refined using selected ideas from the supplied Kimi K3 design document; decisions and unverified assumptions from that document are not automatically adopted.

## First priority: establish an auditable, continuously maintained data system

This roadmap is governed by [docs/ETHICS.md](docs/ETHICS.md). Every preservation, immutable-history, and reconstruction requirement below is subject to its controlled retention/removal exceptions. Removed sensitive material must not be reconstructed or republished. Government source origin is not a factual accuracy guarantee. [Policy implementation tasks](docs/governance/policy-implementation-todo.md) track the removal runbook, release checks, public policy page, and end-to-end verification; these are publication requirements, not implemented guarantees.

The current datasets are approximately a year old according to the developer and must all be preserved and migrated with an explicit `legacy` tag. Their exact source dates may be unknown. The migration date must never be presented as the date the underlying information was verified.

The first deliverable is a separate new database, fed by newly established automated or nearly automated acquisition workflows for **every existing source**. Weekly checks are the starting cadence, adjusted to each source's publication schedule and access requirements. This system must preserve historical observations, acquisition timestamps, transformations, and review decisions from its first run.

Connecting this data to the production website is a later, independent decision. The data system is a valuable milestone even while production continues using legacy data. Product redesign must not delay acquisition, archival, history, and auditability.

| Data boundary | Purpose | Rule |
| --- | --- | --- |
| Legacy archive | Preserve all existing files and tagged migrated records | Immutable originals, checksums, migration manifest, known dates and explicit unknowns; never silently relabel as freshly verified |
| New maintained database | Store fresh acquisitions, normalized records, and historical observations | Separate from the legacy archive and production data; every version traces to an acquisition run and source evidence |
| Production release | Serve a selected validated dataset to the public | Explicit promotion of a named release; acquisition success does not automatically change the website |

These boundaries do not require three physical servers. They require separate storage/database boundaries and explicit lineage so legacy, newly acquired, and publicly served data cannot be confused.

This document captures the initial codebase assessment, product direction, and an actionable backlog for reviving the project. The assessment is based on source inspection and a limited audit of the checked-in datasets, not a benchmark of the running application or a complete verification of upstream sources.

## Guiding principle

> “The horror of animal agriculture is much more and much closer than you can have imagined.”

Until Every Cage exists to help people understand the scale of animal exploitation, discover its infrastructure around them, and examine the evidence. V2 should make that principle tangible through public-facing experiences backed by trustworthy, reproducible data.

The project began as a portfolio piece. Its next iteration should use the developer's increased engineering experience to build something sustainable: useful to the public, activists, journalists, and researchers, and practical for a small team to maintain.

The strongest opportunity is a connected journey:

1. Understand the scale through a compelling visual story.
2. Enter a town or postcode and discover documented facilities nearby.
3. Open a facility page and inspect its sources and history.
4. Share a specific finding, export evidence, or contribute a correction.

The engineering foundation should serve this journey. Cleaner code alone is not the definition of success.

### A practical feature and design test

For each proposed change, ask whether it improves at least one of the following: local relevance, comprehension of scale, evidence quality, research usefulness, or maintainability. Infrastructure work qualifies through the trust and reliability it enables even when it has no visible storytelling effect.

- **Proximity:** Show distance from the visitor's chosen place where useful. Label straight-line distance explicitly and avoid precision beyond the underlying coordinates. Postcode/town entry must work without device geolocation.
- **Comprehension:** Use understandable time and scale comparisons derived from cited inputs. Do not extrapolate lifetime facility totals from a license/grant date and a present-day rate.
- **Discovery:** Explore optional estimate-then-reveal interactions and progressive disclosure. Always provide direct access to the evidence; the reveal should not become an obstacle or a game.
- **Documentary restraint:** Use clear language, arithmetic, and sources as the default storytelling tools. Distinguish quoted source terminology from project explanations. Avoid graphic shock imagery and preserve accurate activity labels rather than treating all animal-related facilities as slaughterhouses.
- **Location privacy:** Keep personalization optional, avoid retaining precise visitor locations by default, and disclose any location query sent to an external geocoder. Do not put a home address into a shared URL or analytics event.

## Product structure

Separate **Until Every Cage**, the umbrella project, from the map tool's name. The main domain can introduce the mission and host a collection of related tools that share data and methodology.

| Destination | Question it answers | Initial scope |
| --- | --- | --- |
| Map tool | Where is this happening around me? | Local search, filters, facility pages, evidence, sharing, export |
| Flagship visual story | How can the numbers possibly be this large? | One carefully sourced narrative about scale that leads into the map |
| Data and methodology | Where does this information come from? | Source catalog, coverage, freshness, release history, calculations, corrections |

### Product checklist

- [ ] Choose a descriptive map name and subtitle, with attribution to Until Every Cage.
  - **Why:** New visitors should immediately understand what the tool does. “Animal Agriculture Map — by Until Every Cage” is a working description, not a final brand.
- [ ] Evaluate the supplied naming candidates: Glasshouse, Abattoir Atlas, and The Facility Index.
  - **Why:** They offer different tradeoffs between memorable identity and descriptive clarity. Abattoir Atlas may imply a narrower scope than the dataset. Domain availability and name collisions remain unverified; no candidate is selected.
- [ ] Define navigation and URL structure for the umbrella site, map, stories, facilities, regions, and methodology.
  - **Why:** Each experience should be independently discoverable and shareable while connecting naturally to the others.
- [ ] Define the relationship between animal agriculture and broader exploitation categories.
  - **Why:** Existing research, breeder, dealer, and exhibitor records should remain useful without blurring the scope of agriculture-specific narratives or totals.
- [ ] Preserve existing shared map links during migration, including filter and viewport state.
  - **Why:** Existing links are part of the project's value and should continue to resolve meaningfully.
- [ ] Plan descriptive titles, indexable pages, canonical URLs, and social previews.
  - **Why:** Renaming the map alone will not make it easier to find or share.

## What the current code and data tell us

These findings identify refactor candidates. They do not establish that every repeated record is erroneous or that all data quality issues have been found.

| Finding | Evidence | Implication for V2 |
| --- | --- | --- |
| 50,750 location rows across nine countries, excluding APHIS and inspection files | `static_data/*/locations.csv` | Distinguish source rows from unique physical facilities before publishing counts. |
| Germany has 1,811 repeated establishment-ID groups; Mexico has 5,388 | Grouping the checked-in CSVs by `establishment_id`; samples include repeated records and activity variations | Define identity and reconciliation rules; do not blindly drop duplicates. |
| Zero-coordinate records include 962 in Germany, 420 in Denmark, and 665 in New Zealand | Limited CSV audit; this is not a comprehensive coordinate validation | Represent missing locations explicitly and report geocoding coverage. |
| Danish IDs are generated from row order | `src/bin/da-foedevarestyrelsen/main.rs` | IDs can change when a source is reordered, undermining history and links. |
| Classification is based on strings inside icon utilities | `static/modules/iconUtils.js` | Domain interpretation is mixed with rendering; unknown types default to processing and butcher labels map to slaughter. |
| Display labels can be objects, while filtering assumes a string | `iconUtils.js` and `FilterManager.js` | Introduce typed contracts and separate classification identifiers from translated labels. |
| A malformed location row fails parsing; APHIS parsing silently skips malformed rows | `src/lib.rs` | Validation must happen before publication, with explicit rejected-record reports. |
| Data is embedded at compile time | `src/lib.rs`, `include_dir!` and `include_str!` | Data releases require application rebuilds today. |
| API responses are cached without revalidation on cache hits | `static/sw.js` | Returning visitors can continue seeing old data after a backend update. |
| The client loads all three datasets and recreates markers on filter updates | `DataManager.js`, `MapManager.js` | Payload size and rendering work grow with global coverage; measure and redesign delivery. |
| Annual counter figures are hardcoded with informal source comments | `static/about.html` | Statistics need explicit scope, period, uncertainty, and reproducible calculations. |
| Source links are hardcoded by country and source values enter HTML templates | `popupBuilder.js`, `SearchManager.js` | Model citations as data and render untrusted source text safely. |
| Jest configuration and mocks exist, but no application test suite was found in the inventory | `package.json`, `jest.config.js`, `jest.setup.js` | Establish a small, meaningful verification baseline rather than assuming coverage exists. |

## Priority 1 — Build fresh acquisition, historical storage, and auditability for every source

### Preserve the legacy baseline first

- [ ] Archive every current dataset unchanged, with a checksum and manifest identifying its original path and available provenance.
  - **Why:** The existing collection is historical evidence and a migration baseline. Cleaning must not destroy the original inputs.
- [ ] Import current records into a separate legacy namespace/archive with `data_origin=legacy`, a snapshot ID, and migration timestamp.
  - **Why:** All current data is legacy, including records whose provenance is relatively complete. The tag must survive queries and exports.
- [ ] Record the developer's approximate age assessment separately from verified source dates; leave unknown retrieval and observation dates unknown.
  - **Why:** Filesystem timestamps and today's import date do not establish when the source was current.
- [ ] Preserve links between legacy identities and newly acquired records without replacing legacy history.
  - **Why:** Fresh evidence can corroborate or change an old record while the earlier observation remains inspectable.

### Establish new acquisition for every existing source

- [ ] Build a source registry covering every dataset underlying the nine countries, APHIS reports, and inspection records, including multiple sources within a country.
  - **Why:** Country coverage alone is not an acquisition inventory. Each upstream source needs its own workflow, owner/status, and freshness expectations.
- [ ] Make the registry machine-readable, with source ID, access method, URL, scope, attribution, cadence, adapter version, expected schema, and assisted steps; execute adapters through a common runner.
  - **Why:** Source configuration should be reviewable without reading scattered scripts. Complex parsing remains tested adapter code rather than being forced into an elaborate configuration language.
- [ ] Establish and test a new acquisition adapter for each source; use existing scripts as references rather than assuming they still work.
  - **Why:** Approximately year-old integrations must be revalidated against current upstream formats and availability.
- [ ] Prefer direct downloads or APIs when available; document repeatable assisted acquisition where full automation is impractical.
  - **Why:** Near automation is acceptable when the human step, input artifact, operator, and timing are auditable.
- [ ] Start with one complete adapter to prove the design, then roll it out across all existing sources before treating the data phase as complete.
  - **Why:** One source is an architectural checkpoint, not the scope of the data-first milestone.
- [ ] Record unavailable sources explicitly, with the blocker and a repeatable recovery or assisted acquisition plan.
  - **Why:** Legacy-only coverage must not be counted as an operating fresh-data integration.

### Retain history from the first acquisition

- [ ] Create the separate maintained database with durable facility IDs, immutable source snapshots, acquisition-run records, and append-only record versions/observations.
  - **Why:** Overwriting a current row loses evidence needed to establish what changed and reproduce previous results.
- [ ] Keep a queryable latest validated view alongside historical versions and release manifests.
  - **Why:** Current queries should be convenient without sacrificing the ability to reconstruct a prior release.
- [ ] Record `checked_at`, `retrieved_at` when a download occurs, source publication/effective dates when supplied, `ingested_at`, and first/last observation times.
  - **Why:** A successful weekly check does not mean the source published new information. Each timestamp should express exactly what happened.
- [ ] Schedule weekly checks by default, with explicit per-source overrides and documented manual steps.
  - **Why:** Regular collection builds history while respecting actual publication cadence. Weekly is a starting proposal, not a promise that upstream data changes weekly.
- [ ] Record unchanged, changed, failed, and review-required runs separately; deduplicate identical archived content by hash without dropping the run history.
  - **Why:** An unchanged successful check is evidence of monitoring, while a failure must not advance the last-successful timestamp or fabricate an observation.
- [ ] Version corrections, classification changes, merges, and splits with reasons and actor/tool versions.
  - **Why:** Historical differences can arise from project interpretation as well as upstream changes; auditors must be able to distinguish them.
- [ ] Test historical queries, reproducible releases, and backup restoration before relying on scheduled ingestion.
  - **Why:** A current table plus occasional backups is not a usable historical record, and history must survive operational failures.

### Define the domain model

- [ ] Define a facility as a physical site with a stable project ID.
  - **Why:** Source IDs, licenses, organizations, and physical locations are different things. Permanent pages and history require durable identity.
- [ ] Preserve source identifiers in a source-specific namespace.
  - **Why:** Identical IDs can occur in different datasets; a source ID must remain traceable to its original record.
- [ ] Separate facilities, organizations, source records, observations, and aggregate statistics.
  - **Why:** An inspection is an observation; an annual national total is not a facility attribute. Keeping these distinctions prevents misleading aggregation.
- [ ] Support multiple activities and species per facility.
  - **Why:** A single site can slaughter and process several species. A mutually exclusive icon category is insufficient as the domain model.
- [ ] Define explicit unknown, unavailable, and not-applicable values.
  - **Why:** Missing evidence must not silently become “processing,” zero animals, or a precise coordinate.
- [ ] Define dates for source publication, retrieval, observation, and project release.
  - **Why:** “Last updated” is ambiguous unless readers know what changed and when the evidence was recorded.
- [ ] Store coordinates with method, precision, source, and review status.
  - **Why:** A town centroid and a verified site location support different proximity claims.

### Audit and migrate existing datasets

- [ ] Inventory each source, its scope, retrieval method, known vintage, attribution, and reuse terms.
  - **Why:** Some datasets cover particular facility categories or administrative regions, not an entire national industry.
- [ ] Investigate repeated IDs and define deterministic reconciliation rules.
  - **Why:** Repeated rows may be duplicates, multiple activities, or distinct records about the same site. Preserve evidence during merges.
- [ ] Audit missing and invalid coordinates, country mismatches, and implausible location changes.
  - **Why:** Proximity is a central product claim and needs a reliable spatial foundation.
- [ ] Replace row-order-generated IDs with stable identities and preserve mappings from legacy records.
  - **Why:** Refreshes must not break facility histories or shared links.
- [ ] Move classification rules into versioned source adapters or shared domain transformations.
  - **Why:** The same record should have the same meaning in the map, API, export, and narrative tools.
- [ ] Preserve all current datasets as explicitly tagged legacy snapshots, retaining known provenance and documenting gaps.
  - **Why:** Migration does not make old data fresh. Existing coverage remains useful as historical evidence with honest limitations.

### Build the reproducible pipeline

Target flow:

`Acquire → archive raw source → normalize → validate → reconcile identities → append history → create validated data release`

Optional later step: `select validated release → promote to production`. Acquisition and historical storage must operate independently of this step.

- [ ] Implement one source adapter end to end before generalizing the framework.
  - **Why:** A working vertical slice reveals the actual abstractions needed. Start with a source whose format and identity rules are understood.
- [ ] Archive immutable raw downloads in object storage with URL, retrieval time, and content hash.
  - **Why:** Reproducing a release should not depend on the upstream site still serving the same file.
- [ ] Pin dependencies and record parser version, configuration, and transformation steps per run.
  - **Why:** A future maintainer should be able to reproduce how a published record was derived.
- [ ] Make processing deterministic and safe to rerun; cache geocoding results with provenance.
  - **Why:** Retries must not create duplicate facilities or repeatedly consume external geocoding resources.
- [ ] Produce validation reports and quarantine rejected records.
  - **Why:** Silent row loss and all-or-nothing runtime parsing both obscure the quality of published data.
- [ ] Generate release diffs for additions, changes, missing records, classification changes, and identity merges.
  - **Why:** Review should focus on what actually changed.
- [ ] Automate routine refreshes and flag exceptional changes for review.
  - **Why:** Schema changes, sharp count drops, coordinate shifts, and ambiguous merges deserve attention; ordinary updates should be low maintenance.
- [ ] Publish releases atomically and keep the previous successful release available.
  - **Why:** A failed ingestion run should not make the public application unusable or partially updated.
- [ ] Treat source disappearance as “no longer observed,” unless closure is documented.
  - **Why:** Missing records are not proof that a facility closed.
- [ ] Store reviewed corrections as attributed overrides with reasons and citations.
  - **Why:** A subsequent import must not erase valid manual corrections.
- [ ] Add source-specific schedules, freshness targets, run logs, and actionable failure notifications.
  - **Why:** Automation is useful only if failures and stale sources are visible.
- [ ] Generate a compact review artifact for each changed candidate release, including validation results, additions/removals, representative changes, and links to archived evidence.
  - **Why:** Review must fit a maintainer's available time. A pull request can review adapter/configuration changes or exceptional releases; weekly raw datasets do not need to be committed into Git.
- [ ] Expose separate quality dimensions: freshness, coordinate precision, source coverage, validation failures, and unresolved identity conflicts.
  - **Why:** A single letter grade or confidence score hides tradeoffs. Measurable dimensions let readers assess fitness for their use without implying unsupported certainty.
- [ ] Document how contributors add an adapter or review a correction, including fixtures, expected outputs, reviewer roles, and escalation rules.
  - **Why:** The project should be maintainable alongside full-time employment and allow useful contributions without relying on one person's undocumented knowledge.

**Initial checkpoint:** One source can be refreshed and reproduced from archived input; every normalized record traces back to evidence; failed runs retain the last validated release; rerunning the same input preserves identities and results.

**Data-phase completion criteria:** All existing data is archived and migrated with the legacy tag. Every existing source has a newly tested automated or documented assisted acquisition workflow; unavailable sources remain explicitly incomplete. The separate database retains dated observations and reconstructable releases, records weekly checks or documented cadence overrides, and preserves audit trails for transformations and reviews. Historical retrieval and restoration are tested. No production website migration is required to achieve this milestone.

## Priority 2 — Deliver the local discovery experience

- [ ] Add town/postcode search and an optional device-location entry point.
  - **Why:** Begin with a place the visitor understands and give them control over how they specify it.
- [ ] Add radius queries and a synchronized result list and map.
  - **Why:** Users should be able to answer “what is within this area?” without manually inspecting pins.
- [ ] Distinguish documented, geocoded facilities from records that cannot be precisely mapped.
  - **Why:** A map can hide missing-location records and overstate the completeness of a nearby result.
- [ ] Build permanent facility pages with activities, evidence, observation dates, location precision, and correction links.
  - **Why:** A popup is too constrained to support investigation, citation, and search discovery.
- [ ] Add regional summaries with coverage and freshness information.
  - **Why:** Summaries need to distinguish a sparse dataset from a genuinely low count of documented sites.
- [ ] Implement stable filter, selection, and viewport URLs, including browser back/forward behavior.
  - **Why:** Shared findings should reproduce the intended view.
- [ ] Improve exports with facility IDs, source citations, release IDs, filters, and coverage notes.
  - **Why:** Downloaded evidence must remain interpretable outside the application.
- [ ] Publish a documented read-only API and citable bulk releases once the schema and validation process are stable.
  - **Why:** Other researchers and tools can reuse the evidence independently of the website. Start with CSV and GeoJSON; add Parquet when analytical use warrants it. Include schema versions, checksums, attribution, and stable release identifiers.
- [ ] Support search by facility name, alternate name, source/certificate ID, and address, with explainable ranking.
  - **Why:** Investigators often arrive with partial records. Exact identifiers should take precedence over fuzzy matches, and search similarity must never silently merge identities.
- [ ] Add reviewed correction intake.
  - **Why:** Contributors need a practical way to improve the data, with a record of how changes were resolved.
- [ ] Design for mobile, keyboard navigation, readable contrast, and a useful non-map list view.
  - **Why:** The central experience should work across devices and interaction methods.

**Completion criteria:** A visitor can choose a place, understand documented nearby activity, inspect a facility's evidence, and share or export the finding with its source context intact.

## Priority 3 — Launch one flagship scale story

Reference: Matt Korostoff's *Wealth, Shown to Scale*, which uses scrolling distance to communicate magnitude. The animal-focused experience should develop its own narrative and connect directly to local discovery.

Suggested sequence: one animal → a group → a million → a billion → an annual population-specific estimate → “Where does this happen around you?”

“The Year” is a useful working concept: a dated annual account of a clearly defined population. Begin with legible individual marks, explicitly reveal the point at which each mark represents a larger group, then offer the transition into local discovery. A visible estimated-rate clock can complement the fixed annual total, but the two must not be combined as if they were independent counts.

- [ ] Choose one clear narrative and define its included populations and time period.
  - **Why:** Combining agriculture, fishing, laboratory use, and other categories without boundaries makes the story difficult to substantiate.
- [ ] Build a versioned statistics catalog with source, unit, period, low/high estimates, and calculation method.
  - **Why:** The same statistical evidence should power stories, counters, and downloadable methodology.
- [ ] Reconcile overlapping categories before calculating totals.
  - **Why:** Adding estimates from incompatible scopes or periods can double-count animals or imply unsupported precision.
- [ ] Prototype the narrative with sourced data and a small visual vocabulary.
  - **Why:** Validate whether the scale is understandable before investing in elaborate animation.
- [ ] Make every change of visual unit explicit.
  - **Why:** If a dot changes from one animal to a thousand, readers must be able to follow the arithmetic.
- [ ] Show uncertainty and explain how estimates derived from tonnage differ from individual counts.
  - **Why:** Uncertainty is part of the evidence, and can itself communicate how animals disappear into industrial statistics.
- [ ] Return periodically to individual animals and their experiences.
  - **Why:** Huge numbers can become abstract; the narrative should preserve what those numbers represent.
- [ ] Replace the existing counter with a sourced estimate based on actual elapsed time.
  - **Why:** Label it as an estimate from annual rates, not a live observation, and avoid timer-throttling drift.
- [ ] Provide chapter navigation, reduced motion, keyboard support, and an accessible text equivalent.
  - **Why:** An extremely long scroll should not be the only way to understand the story.
- [ ] Connect the ending to location search and provide useful advocacy or research next steps.
  - **Why:** Give visitors a path from understanding to further exploration and action.
- [ ] Validate every comparison and conversion with dimensional checks and cited inputs before writing headline copy.
  - **Why:** The supplied draft's approximate figures and population comparisons are ideas, not verified claims. A correct arithmetic conversion still needs a defensible input and period. Facility rates require facility-specific evidence; capacity bands are not measured output.
- [ ] Prototype a bounded, navigable story using reusable marks or canvas rather than one DOM element per animal.
  - **Why:** The browser should not need to render billions of objects. Keep scroll semantics honest, label any scale change, and avoid simulated progress that implies a literal distance-to-count mapping when none exists.
- [ ] Set a measured mobile performance budget and test comprehension with readers unfamiliar with the project.
  - **Why:** Animation quality and scroll depth alone do not establish understanding. Track whether readers can explain the units, find a citation, and continue to local evidence.
- [ ] Consider a dated annual edition with an immutable data release and visible corrections/version history.
  - **Why:** An annual edition is citable and shareable while weekly acquisition continues underneath it. Publishing a new edition should not silently rewrite an old one.

**Completion criteria:** Readers can explain the scale and its assumptions, inspect the underlying sources, navigate accessibly, and continue into the map.

## Technical direction to validate

| Component | Recommended starting point | Reason and decision gate |
| --- | --- | --- |
| API | Keep Rust/Axum | The current backend language is not the main constraint. Refactor its contracts and data access. |
| Database | Separate maintained PostgreSQL/PostGIS database plus legacy archive | Preserve immutable inputs and append-only observations from the first run; expose current and historical views independently of production. |
| Ingestion | Python with pinned dependencies and source adapters | Existing source-processing work can inform a reproducible pipeline. |
| Frontend | SvelteKit with TypeScript | Supports a mix of narrative pages, indexable facility pages, and interactive tools. Confirm developer preference before committing. |
| Mapping | Evaluate MapLibre against the required mobile workload | Benchmark realistic payloads, filtering, clustering, and detail interaction before selecting a replacement for Leaflet. |
| Storage and scheduling | Object storage plus scheduled ingestion jobs | Enough to establish immutable snapshots and automated releases without a large orchestration system. |
| Repository | One repository with clear web, API, pipeline, and schema boundaries | Keep coordination straightforward for a small team. |

### Engineering checklist

- [ ] Preserve useful existing behavior with focused regression checks, then replace its implementation where needed.
  - **Why:** URL sharing, filters, localization, and exports contain product knowledge worth retaining. Preserving behavior does not mean carrying forward the current coupling or known bugs.
- [ ] Archive large source files and historical assets before planning repository cleanup; verify archived checksums and retrieval first.
  - **Why:** A smaller repository helps contributors, but removing files is a separate implementation task after legacy preservation. This roadmap does not authorize an indiscriminate purge.
- [ ] Define one versioned machine-readable contract for normalized records, with compatibility checks across Python, Rust, and TypeScript.
  - **Why:** Shared schema validation should detect drift at the pipeline/API boundary rather than in browser rendering.
- [ ] Add localization key validation and keep stable domain identifiers separate from translated copy.
  - **Why:** Refactoring should preserve multilingual access and prevent display-label assumptions from affecting classification or search.
- [ ] Define versioned API contracts and generated or validated frontend types.
  - **Why:** Prevent source-specific fields and inconsistent label shapes from spreading across the UI.
- [ ] Add spatial filtering, pagination, aggregate queries, and on-demand facility detail.
  - **Why:** Visitors should not need every record worldwide to inspect their area.
- [ ] Benchmark representative mobile map workloads and choose payload/rendering strategy from results.
  - **Why:** Vector tiles, lightweight GeoJSON, and clustering are tools to evaluate against actual needs.
- [ ] Separate data release versions from application versions and implement explicit cache revalidation.
  - **Why:** Publishing new evidence must reliably reach returning visitors.
- [ ] Centralize application state and keep domain logic independent of DOM elements and translated labels.
  - **Why:** Filters, exports, URLs, and rendering should agree on the same underlying query.
- [ ] Render source text safely and validate exported cell content and external links.
  - **Why:** Automated imports bring externally controlled values into HTML and downloadable files.
- [ ] Add deployment health checks, structured diagnostics, database migrations, and backup/restore verification.
  - **Why:** The project needs observable failures and a tested recovery path as persistent state grows.
- [ ] Establish CI for schema validation, meaningful tests, type checks, and builds.
  - **Why:** The refactor should make changes easier to trust and review.
- [ ] Test stable IDs, classification rules, units, reconciliation, failed publication, spatial queries, and filter/export consistency.
  - **Why:** These behaviors protect the accuracy of the public claims.
- [ ] Add browser checks for local search, evidence pages, shared links, mobile layout, and accessibility.
  - **Why:** Technical correctness needs to translate into a working visitor journey.

## Delivery order and boundaries

1. **Legacy preservation:** Archive all current inputs unchanged and migrate them with explicit legacy provenance and honest date metadata.
2. **Independent data system:** Prove one adapter, then establish fresh acquisition for every existing source. Run scheduled or documented assisted updates into the separate database, retaining historical observations, validated releases, and audit trails. This is the first major deliverable.
3. **Local vertical slice:** Deliver location search → results → facility evidence → share/export using selected validated releases. Production integration is a separate promotion decision.
4. **Public relaunch:** Ship the umbrella site and one sourced narrative connected to local discovery.
5. **Expansion:** Add new sources beyond the existing inventory, regional reporting, and further tools. Historical storage is already operating; later work adds ways to explore it.

Use concrete completion criteria rather than committing to calendar estimates before the first source adapter and map prototype expose the work involved.

### Scope controls and decisions retained after comparison

- Data acquisition and historical storage remain first; the supplied proposal to ship the scroll story first does not match the developer's current priority.
- PostgreSQL/PostGIS remains the starting recommendation for the maintained database. SQLite-based options can be evaluated if operating constraints favor them; any alternative must satisfy the same historical, ingestion, and spatial requirements.
- TypeScript is the frontend direction; SvelteKit remains a proposal. Plain TypeScript with Vite is an alternative to compare against routing, indexable pages, localization, and contribution needs. Framework preference is not settled by either document.
- Tiles, a globe toggle, and a 3D renderer are not mandatory for launch. Choose rendering and delivery from measured needs.
- The inspected application serves stored APHIS CSVs; no live APHIS proxy was established by the assessment. A proxy is not part of the migration baseline.
- Avoid accounts, comments, social features, opaque risk scores, native applications, and distributed infrastructure in the initial scope. Revisit only for a demonstrated requirement.
- Calendar estimates and assumptions about weekly developer availability in the supplied draft are not commitments. Estimate after the first complete adapter and source inventory expose actual constraints.

### Valuable later, outside the first release

- [ ] Geographic change feeds, initially as citable regional reports or feeds before subscription infrastructure.
  - **Why later:** Useful once acquisition history is reliable. Distinguish “newly observed in this dataset” from “newly permitted,” “opened,” or “closed.” Permit alerts require actual dated permitting sources and cannot be inferred from first appearance in a facility directory.
- [ ] Small embeddable maps or statistical panels for researchers and newsrooms.
  - **Why later:** Reuse can extend reach after the core experience is stable. Embed the release ID, attribution, coverage context, and source link with the graphic.
- [ ] A timeboxed 3D narrative prototype, separate from the primary 2D investigation interface.
  - **Why later:** A descent from global scale to local evidence could be compelling, but throughput evidence must support any height encoding. Separate measured counts, estimates, capacity bands, and unknowns; disclose any logarithmic or capped scale and offer a 2D/reduced-motion equivalent. Do not infer a site's annual total from a broad size class.
- [ ] Documented ownership relationships and organization pages.
  - **Why later:** Potentially valuable for investigation, but relationships need their own sources, dates, and maintenance.
- [ ] Supply-chain connections where direct evidence exists.
  - **Why later:** Proximity or shared names do not establish a supply relationship.
- [ ] Additional visualizations and reusable embeds.
  - **Why later:** First validate that one story and the shared data model are useful and maintainable.
- [ ] Changes-over-time tools and regional change reports.
  - **Why later:** Public history interfaces can follow the first release; historical acquisition and storage are mandatory in the initial data phase.
- [ ] Broader international coverage.
  - **Why later:** New countries become easier to integrate once the adapter and review process work end to end.

## Success criteria

- All existing datasets remain recoverable as explicitly tagged legacy inputs and migrated records.
- Every existing source has a newly validated automated or documented assisted acquisition path, or an explicit unresolved blocker.
- The maintained database accumulates auditable history independently of whether production consumes it.
- Weekly checks or documented source-specific schedules distinguish unchanged data from collection failures and actual source updates.
- Earlier validated releases can be reconstructed from archived evidence and versioned transformations.
- Every displayed facility claim can be traced to a source record or reviewed correction.
- Every aggregate statistic exposes its scope, period, units, method, and uncertainty where applicable.
- Facility counts represent the defined entity, not an accidental count of source rows.
- Missing coverage is distinguishable from an absence of documented facilities.
- Data can refresh independently of application deployments, and failures preserve published availability.
- A new contributor can reproduce a source transformation from documented inputs.
- The local discovery journey works on representative mobile devices and with keyboard navigation.
- Visitors can move from scale to local evidence and share a useful result.

Do not allocate national slaughter estimates to nearby facilities without a defensible method. Do not equate a facility's presence with evidence of every practice discussed in a general narrative. The strength of the project comes from pairing clear advocacy with claims that withstand inspection.

## Open decisions

- Final map name and umbrella-site information architecture.
- First automated source and geographic focus for the local prototype.
- Frontend framework preference and mapping benchmark results.
- Statistical scope and narrative arc for the first story.
- Hosting budget and expected maintenance time; weekly source checks are the proposed default, with justified per-source overrides.
- Review rules for exceptional imports and community corrections.

## References

- [Background on Matt Korostoff's Wealth, Shown to Scale](https://www.lutheranpeace.org/the-wealth-gap-shown-to-scale/)
- [Fishcount estimates and research](https://fishcount.org.uk/) — distinguishes populations, periods, and estimate ranges; revisit the underlying papers when implementing statistical content.
- [PostGIS radius queries](https://postgis.net/documentation/tips/st-dwithin/)
- [SvelteKit rendering options](https://svelte.dev/docs/kit/page-options)
- [MapLibre guidance for large datasets](https://maplibre.org/maplibre-gl-js/docs/guides/large-data/)

Technical recommendations and statistical sources should be rechecked when implementation begins. The findings above describe the repository inspected during this planning discussion.
