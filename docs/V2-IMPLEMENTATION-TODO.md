# V2 Implementation TODO

This is the execution plan for the V2 overhaul: an auditable backend/data platform and a scalable frontend discovery experience.

Current evidence is summarized in [V2-BACKEND-PHASE-0-CLOSEOUT.md](V2-BACKEND-PHASE-0-CLOSEOUT.md). That report distinguishes verified backend behavior from unresolved public-production blockers.

The current production application remains V1 while this plan is executed. V2 must not be promoted merely because the API or frontend exists; promotion requires the relevant data, privacy, release, accessibility, performance, and rollback gates below.

## Current position

- [x] V1 production API and vanilla JavaScript frontend remain available.
- [x] V2 API routes, database projections, release metadata, provenance fields, and profile-aware responses exist.
- [x] V2 frontend compatibility mode exists behind `?api=v2` / local storage opt-in.
- [x] V2 pipeline structure and Denmark partial vertical slice exist.
- [x] Backend foundation is fully closed and certified for frontend integration; public-production blockers remain explicitly listed below.
- [ ] New frontend platform has been built.
- [ ] V2 frontend is wired to the live V2 backend.
- [ ] V2 has been promoted to replace V1 in production.

## Phase 0 — Close and certify the backend foundation

Goal: make the current backend/data-platform branch independently runnable, reviewable, and safe for frontend integration.

- [ ] Finalize the V2 API contract for list, detail, filters, pagination, profiles, provenance, errors, and release metadata.
- [x] Make database migrations reproducible from a clean database.
- [ ] Complete one source adapter end to end, including acquisition, archival, parsing, normalization, validation, import, identity, release creation, and rerun behavior.
- [ ] Preserve legacy inputs unchanged with checksums, manifests, explicit `legacy` provenance, and honest date metadata.
- [ ] Verify stable facility identity behavior and source-record traceability.
- [ ] Verify candidate release validation and explicit promotion.
- [ ] Verify failed imports leave the previous eligible release available.
- [ ] Verify the public API reads only from curated promoted projections.
- [ ] Verify privacy screening, publication eligibility, and suppression behavior for list and detail endpoints.
- [ ] Verify profile separation for official, secondary, and community views.
- [x] Verify backup/restore and historical release reconstruction for the synthetic suppression scenario.
- [ ] Add or finish operational runbooks, health checks, diagnostics, and failure handling.
- [ ] Record unresolved source-coverage and policy blockers explicitly.

### Current Phase 0 audit blockers

These are confirmed gaps or unavailable verification evidence. They must not be treated as complete merely because related schema or documentation exists.

- [x] Replace production database transport with Rustls-backed PostgreSQL connections; retain `NoTls` only for explicitly local/development mode. Deployment-level TLS verification remains open.
- [x] Establish a formal migration version/checksum record for incremental deployments; clean PostGIS migration execution and idempotent rerun are certified for the disposable E2E environment.
- [x] Run the disposable Docker/PostGIS backup-restore evidence and isolated API E2E modules; the full multi-class harness remains a separate runner-concurrency issue.
- [ ] Complete suppression propagation verification for V2 historical/API projections, exports, caches, reimports, and restores.
- [x] Decide and implement the explicit screened-but-unreviewed community profile contract, including persistent warnings and separate counts.
- [ ] Establish authorized maintainer/reviewer availability, publication pause behavior, retention/removal ownership, and operational correction handling.
- [ ] Audit deployed visitor privacy, logging, CDN/tile/geocoder/error services, and retention behavior.
- [ ] Publish and monitor a real `security.txt` route rather than only retaining the template.
- [x] Resolve the JavaScript test runner environment/configuration failure before relying on the frontend gate.

On 2026-09-13, the Rust suite passed 65 tests and the Python unittest suite passed 57 tests with 3 expected skips in the canonical clean runner. The runner uses the same PowerShell entrypoint in local and GitHub Actions environments, starts a disposable database on an isolated port, applies all 21 migrations, and removes its volume afterward. Jest passed 13 tests. Isolated public API (5), community API (5), and seeded API (12) E2E tests passed. These results support the Phase 0/1 implementation claims; operational and production-policy blockers remain listed below.

### Phase 0 exit criteria

> Backend V2 is independently runnable and safe for frontend integration, although source coverage may remain incomplete and explicitly documented.

## Phase 1 — Freeze the frontend/backend contract

Goal: prevent the new frontend from inheriting database-shaped or V1-specific assumptions.

- [x] Define a versioned machine-readable contract for all public V2 responses.
- [x] Define typed frontend domain models, preferably generated or validated from the API contract.
- [x] Add representative synthetic fixtures for list, detail, empty, restricted, and community cases.
- [x] Add contract tests between Rust API responses and frontend expectations.
- [x] Define stable URL and query semantics for filters, profiles, pagination, search, and map views.
- [x] Preserve independent source origin, factual review, privacy screening, project approval, and publication profile fields.
- [x] Define release-ID and cache-revalidation behavior; the current V2 client performs no durable caching.

### Phase 1 completion evidence

The V2 client now validates publication-critical fields at the API boundary using `v2Contract.js`, with TypeScript declarations in `v2Contract.d.ts` and synthetic fixtures under `static/modules/__fixtures__/`. The contract rejects malformed envelopes, privacy-ineligible records, and unreviewed community records without the required persistent warning. Ethical community E2E coverage verifies approved and screened-unreviewed claims are available only through the community profile, the warning survives direct detail links, and unscreened claims remain absent. Final validation passed: Rust 65 tests, Jest 13 tests, Python 57 tests (4 expected skips), public API E2E 5 tests, community API E2E 5 tests, and seeded API E2E 12 tests. The first disposable PostGIS startup may require one automatic recreation under Docker Desktop resource churn; the hardened fixture retries the complete migration set in a fresh disposable environment.

### Phase 1 exit criteria

> The frontend can be developed entirely against stable V2 types and fixtures without depending on the live database.

## Phase 2 — Build the frontend platform

Goal: replace the growing vanilla-JS/DOM-coordinator architecture with a scalable application foundation.

- [ ] Choose and document the frontend framework and build strategy.
- [ ] Introduce TypeScript and strict domain/API types.
- [ ] Separate API client, domain state, view models, components, map integration, and export logic.
- [ ] Replace global mutable state with centralized, testable application state.
- [ ] Add route-aware URL state.
- [ ] Add a query/cache layer with cancellation and stale-request handling.
- [ ] Make loading, empty, error, restricted, and unavailable states first-class views.
- [ ] Remove inline event handlers and unnecessary `window` globals.
- [ ] Establish component, unit, integration, accessibility, and browser-test conventions.
- [ ] Preserve localization as domain-independent translated presentation.

### Phase 2 exit criteria

> The new frontend has a maintainable platform boundary and can render V2 fixtures without the old V1 `DataManager`/DOM coupling.

## Phase 3 — Build the discovery experience against fixtures

Goal: prove the new product and visitor journey before live API integration.

- [ ] Build the application shell and navigation.
- [ ] Build map, result-list, search, and facility-detail views.
- [ ] Build source/provenance, lifecycle, precision, and publication-context panels.
- [ ] Build official/secondary/community context and warnings.
- [ ] Build shareable URLs and preserved filter state.
- [ ] Build export flows that preserve provenance and release context.
- [ ] Build localized narrative and methodology surfaces.
- [ ] Validate mobile layouts and touch interactions.
- [ ] Validate keyboard navigation and screen-reader behavior.
- [ ] Support reduced motion and accessible alternatives to map interactions.

### Phase 3 exit criteria

> A complete visitor journey works with fixture data: discovery → results → facility evidence → share/export.

## Phase 4 — Add scalable search, map, and data access

Goal: move beyond V1's full-dataset browser loading model.

- [ ] Add server-side text search.
- [ ] Add server-side country, region, category, source, profile, precision, and lifecycle filters.
- [ ] Add radius and bounding-box queries.
- [ ] Add viewport-based map loading and clustering where measurement supports it.
- [ ] Use cursor pagination for large collections.
- [ ] Add on-demand facility detail loading.
- [ ] Add separate aggregate/statistics queries with explicit scope, period, units, method, and uncertainty.
- [ ] Add query cancellation, retry, and stale-response protection.
- [ ] Add release-aware cache invalidation.
- [ ] Benchmark representative mobile map workloads.

### Phase 4 exit criteria

> The frontend does not need to load the worldwide dataset into browser memory and remains usable on representative mobile devices.

## Phase 5 — Wire the frontend to V2

Goal: replace fixture data with the real V2 platform after the frontend and backend boundaries are stable.

- [ ] Replace fixture providers with the V2 API client.
- [ ] Verify every view handles loading, empty, error, unavailable, restricted, and no-promoted-release states.
- [ ] Verify list, map, detail, search, filters, pagination, and exports use consistent query state.
- [ ] Verify release metadata and provenance remain visible where required.
- [ ] Verify stable facility links and shared URLs.
- [ ] Verify restricted records cannot appear through alternate routes, profiles, historical views, or exports.
- [ ] Verify the frontend never silently falls back from V2 to V1 with different semantics.
- [ ] Retire the compatibility adapter after the new frontend no longer needs it.

### Phase 5 exit criteria

> The completed frontend uses V2 end to end and preserves the V2 publication, privacy, provenance, and release semantics.

## Phase 6 — Run V1 and V2 in parallel

Goal: compare systems and build confidence before production migration.

- [ ] Keep V1 as the production default during the comparison period.
- [ ] Expose V2 through an explicit preview or feature flag.
- [ ] Build comparison reports for country counts, coordinates, precision, identity, categories, provenance, lifecycle, and restrictions.
- [ ] Classify V1/V2 differences as source change, reconciliation, policy, suppression, missing coverage, or defect.
- [ ] Test representative facilities and countries manually.
- [ ] Run browser accessibility and mobile checks.
- [ ] Run performance and failure-mode checks.
- [ ] Confirm diagnostics do not expose sensitive payloads.
- [ ] Test rollback from V2 to V1.

### Phase 6 exit criteria

> Differences between V1 and V2 are understood, documented, and acceptable for the intended release scope.

## Phase 7 — Promote V2 frontend and backend together

Goal: make V2 public only after the complete system passes its release gates.

- [ ] Pass the backend release gate.
- [ ] Pass the frontend accessibility and mobile gate.
- [ ] Pass the provenance and data-credibility gate.
- [ ] Pass the privacy and suppression-propagation gate.
- [ ] Pass the export and share-link gate.
- [ ] Pass the performance and availability gate.
- [ ] Verify the rollback path.
- [ ] Update public documentation, methodology, coverage, and limitations.
- [ ] Keep V1 available as a controlled fallback until the migration is stable.

### Phase 7 exit criteria

> V2 is the public system and its claims, restrictions, source lineage, and limitations are accurately represented.

## Phase 8 — Continue the maintained V2 platform

Goal: operate V2 as a durable project rather than a one-time rewrite.

- [ ] Add and validate acquisition adapters for every existing source or document explicit blockers and assisted paths.
- [ ] Run source-specific schedules and actionable failure notifications.
- [ ] Maintain historical releases and reconstruction tests.
- [ ] Maintain suppression and correction workflows across reimports, caches, exports, restores, and old releases.
- [ ] Add new countries only through the established adapter/review/release process.
- [ ] Add change-over-time tools only when observation history supports the claims.
- [ ] Add narrative, statistical, and embeddable experiences without bypassing release and provenance controls.
- [ ] Review frontend performance, accessibility, localization, and contributor workflows continuously.

### Phase 8 exit criteria

> V2 is independently refreshable, historically auditable, privacy-aware, scalable, and extensible without returning to the V1 architecture.

## Working rule

The intended dependency order is:

```text
backend foundation
    → API contract and fixtures
    → frontend platform
    → fixture-based product
    → scalable queries and map behavior
    → live V2 wiring
    → V1/V2 comparison
    → production promotion and ongoing operation
```

“Frontend wiring last” means live integration happens after the frontend and backend boundaries are stable. It does not mean postponing API modeling, types, or contract fixtures until the end.

## Governing references

- [V2 design and implementation roadmap](../v2-ideas.md)
- [V2 location API contract](architecture/api-location-contract.md)
- [V2 data pipeline plan](architecture/data-pipeline-plan.md)
- [Ethics policy](ETHICS.md)
- [Policy implementation checklist](governance/policy-implementation-todo.md)
