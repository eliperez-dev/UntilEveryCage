# Product readiness and V2 roadmap

**Canonical authority:** this document is the sole product-level readiness and
overall V2 roadmap authority. It answers what is complete, what is verified,
what blocks release, and what comes next. Supporting documents provide
evidence for particular systems, sources, policies, or review packets; they do
not replace this page or make an overall completeness claim.

## Authority and scope

This page covers product completeness for the V2 platform and the controlled
replacement of the current V1 public application. It does not grant publication
approval, source permission, privacy clearance, or maintainer authority. The
governing policy is [ETHICS.md](ETHICS.md); its implementation checklist is
[governance/policy-implementation-todo.md](governance/policy-implementation-todo.md).

Use [source-status.json](source-status.json) for source-level status and
[governance/v2-mvp-claim-evidence.json](governance/v2-mvp-claim-evidence.json)
for implementation claims. A count in this document is an aggregate candidate
or evidence count, never a count of approved, accurate, operating, or
publishable facilities unless explicitly labelled that way.

## Verified checkpoint

- **Baseline:** repository checkpoint `D6 integration commit` (D6 private real-edge cohort; 2026-09-21 UTC).
- **Current public product:** V1 remains production and the public default.
- **V2 frontend:** Svelte/TypeScript fixture and local synthetic preview; it is
  not the production replacement and has no configured external tile service.
- **Public release:** no V2 public release has been created or promoted.
- **Evidence:** D1's [contract convergence ledger](api/v2-product-convergence-gap-ledger.md),
  [V1 behavioral contract](frontend/v1-behavioral-contract.md), and row-free
  [data readiness report](../data/manifests/d1-data-readiness-report.json), and
  the B3 France, Denmark, and US private rehearsal manifests are the latest
  supporting records at this checkpoint. Historical source packets
  remain linked below for provenance and review context.

### Current private candidate evidence

These figures are retained only as safe aggregates; raw and restricted payloads
remain private. They describe acquisition/normalization handoffs, not release
readiness.

| Evidence family | Aggregate observed | State and limitation |
| --- | ---: | --- |
| APHIS registrations | 2,552 | normalized private candidate; review, privacy, and approval remain open |
| APHIS FY2025 annual reports | 995 | separate evidence family; not a facility master |
| APHIS inspections | 1,075 input / 1,071 accepted / 4 exact duplicates | inspection observations, not a complete inspection history |
| APHIS combined packet | 4,618 accepted; 2,121 identity links held | identity links remain held for review; no silent merge |
| FSIS current directory | 7,241 | private current candidate; source terms, identity, location, and review remain open |
| FSIS legacy comparison | 7,101 | legacy V1-derived comparison; not a currentness claim |
| France | 2,517 accepted | private candidate; source and publication gates remain open |
| Italy 853/2004 | 47,375 input / 41,849 accepted / 5,526 quarantined | repeated recognition/activity identities require review |
| France private lifecycle rehearsal | 2 sections; synthetic candidate release only | rerun, suppression, and zero-public-row checks passed; source terms, identity, geospatial, and approval gates remain open |
| Denmark private lifecycle rehearsal | 58,398 handoff rows in aggregate report | fail-closed private rehearsal; facility identity, coordinate, review, and publication gates remain open |
| US private lifecycle rehearsal | 4 source profiles; 5 synthetic candidates | deterministic rerun and private suppression checks passed; no database import, release, promotion, or public exposure |

Supporting source evidence includes the [APHIS refresh](aphis-lane1-refresh-2026-09-19.md),
[US source boundary](countries/us/README.md), [France handoff](countries/france/sprint02-handoff-20260919.md),
and [Italy review packet](review-packet-italy.md). No private rows or payloads
belong in this roadmap.

### D1 real-data-shaped readiness boundary

D1 established a row-free, private readiness boundary for FSIS, Italy, France,
and Denmark. These are not approved or public facilities:

| Measure | Strict aggregate | Interpretation |
| --- | ---: | --- |
| Provisional source-local candidates | 34,840 | FSIS 7,241; Italy 25,316; France union 2,283. No canonical cross-source merge. |
| Numeric source coordinates | 31,990 | FSIS 7,241; Italy 24,749; coordinate/privacy review pending. |
| City/postal geocode candidates | 2,850 | Italy 567; France 2,283; coarse placement only, never an exact facility point. |
| Public API rows | 0 | Publication is blocked pending terms, privacy, review, approval, and release authority. |
| Denmark observations | 58,766 | Source observations only; facility identity is unresolved and must not be counted as facilities. |

The complete row-free corpus and its limitations are recorded in
[d1-data-readiness-report.json](../data/manifests/d1-data-readiness-report.json)
and [d1-real-data-shaped-test-corpus.json](../data/manifests/d1-real-data-shaped-test-corpus.json).
The B3 rehearsals now exercise the private lifecycle with sanitized fixtures and
row-free aggregate reports for France, Denmark, and the US. They do not assert
that the corresponding real captures are approved, and they create no public
API rows, release promotion, deployment, or human approval. Database-backed
E2E remains an environment-dependent follow-up gate.

## Status vocabulary

Use exactly one status for each roadmap item or gate:

- **Complete and verified** — implemented and supported by linked, reproducible evidence.
- **Implemented, not exercised** — code or documentation exists but the intended path has not been verified.
- **In progress** — active work has a defined owner and next action.
- **Blocked: engineering** — a technical dependency prevents progress.
- **Blocked: human review** — terms, privacy, factual review, approval, or another authorized decision is required.
- **Deferred** — intentionally sequenced after a named roadmap milestone.
- **Not started** — no implementation or review work has begun.

Do not infer a green product or publication state from passing tests. Acquisition,
import, review, geocoding, approval, promotion, and publication are separate
states and must be reported separately.

## Current product state

| Workstream | Status | Current truth | Next action |
| --- | --- | --- | --- |
| Backend and database | Complete and verified | Rust/Axum API, PostGIS schema, migrations, release/profile concepts, provenance, suppression-aware projections, shared private pipeline, and append-only graph/evidence persistence boundaries are tested in synthetic and disposable PostGIS environments. | Close the remaining live-wire contract and durable release/revocation gaps. |
| API contract | Complete and verified | D1 froze the current frontend-facing DTO/query contract, wire schemas, compatibility notes, and convergence gaps with targeted drift tests. It is exercised against synthetic/local contracts, not a reviewed real release. | Exercise the frozen contract against a named reviewed private release. |
| Frontend product | In progress | V2 is a developer preview using fixtures/local synthetic data; V1 vanilla JavaScript remains public. | Approve information architecture and visual direction, then build a production Svelte frontend. |
| Data acquisition | In progress | Several current private captures and source adapters exist; many countries remain reconnaissance-only or adapter/fixture-only. | Select one bounded first release and complete its source-specific terms and provenance review. |
| Identity and reconciliation | Blocked: human review | Source-local identities, deterministic links, and probabilistic candidate edges are retained with score, confidence band, method, features, contradictions, provenance, disclaimer, and ruleset metadata. Imports remain review-required; cross-source merges and claim transfer are never automatic. | Adjudicate a bounded sample and publish only scoped, evidenced relationships. |
| Geospatial readiness | In progress | Geocoding is disabled or tightly bounded in current private handoffs; provider, precision, privacy, and review state must remain explicit. | Complete source-specific coordinate/privacy review and a production geocoder/provider decision. |
| Privacy and suppression | In progress | Policy and synthetic suppression paths exist, but independent durable restriction, replay, cache, and cross-V1/V2 propagation controls remain release gates. | Implement and exercise the durable ledger, pre-service restore gate, and suppression crosswalk. |
| Operations and deployment | Blocked: engineering | Local/private environments and runbooks exist; production proxy trust, visitor/provider audit, artifact inventory, rollback, and operational ownership are not fully verified. | Complete deployment/provider audit and an operator-run private release drill. |
| Publication and release authority | Blocked: human review | No current candidate has completed all source, privacy, factual, project-approval, and release-authority gates. | Obtain authorized review for the bounded first release; do not infer approval from acquisition or tests. |

### Data lifecycle states

The product readiness state is not a single data count:

```text
acquisition → normalization/quarantine → candidate import → factual/privacy review
→ geocoding review → project approval for a named release/profile
→ promotion → publication
```

An acquired or imported record is not reviewed. A reviewed record is not
approved. An approved record is not promoted. A promoted record is not public
until publication is explicitly verified. Suppression and removal can interrupt
the chain at any stage and also apply to older releases, caches, exports,
reimports, and restores.

## Launch gates

All gates below must be green for a controlled V2 public cutover. “Green” means
the linked evidence exists and the relevant human decision is recorded where
required.

| Gate | Status | Evidence | Next action |
| --- | --- | --- | --- |
| Governing ethics and privacy controls | In progress | [ETHICS.md](ETHICS.md), [policy checklist](governance/policy-implementation-todo.md) | Close outstanding implementation controls and verify behavior, not just prose. |
| Source terms and redistribution | Blocked: human review | [source rights decisions](architecture/source-rights-decisions.md), source-specific assessments | Record terms decision for each source in the first release. |
| Candidate acquisition and provenance | In progress | [source status](source-status.json), [D1 readiness report](../data/manifests/d1-data-readiness-report.json), [B3 private rehearsal manifests](../data/manifests/france-golden-country-private-2026-09-18.json) | Re-run selected sources with retained provenance and safe aggregate validation; keep Denmark observations separate from facility identity. |
| Identity and factual review | Blocked: human review | [US source boundary](countries/us/README.md), [Italy packet](review-packet-italy.md) | Adjudicate held links, quarantines, and contradictions without name/address guessing. |
| Coordinate and address privacy | In progress | [geospatial readiness](current-geospatial-readiness.md), [geocoding operator](geocoding-operator.md) | Complete precision, residential/private-location, provider, and review-state checks. |
| API and release contract | Complete and verified | [V2 API contract](api/v2-contract.md), [D1 convergence ledger](api/v2-product-convergence-gap-ledger.md), [MVP claim evidence](governance/v2-mvp-claim-evidence.md) | Exercise the frozen contract against a named reviewed candidate release. |
| Suppression and revocation | Blocked: engineering | [suppression runbook](governance/suppression-runbook.md), [release manifest guidance](architecture/release-manifest-verification.md) | Add durable restriction ledger, replay gate, cache invalidation, and V1↔V2 crosswalk. |
| Frontend accessibility and performance | In progress | [frontend README](../frontend/README.md), [reviewed demonstration plan](reviewed-demonstration-release.md) | Redesign and test responsive, accessible, performant real-data-shaped views. |
| Deployment and visitor privacy | Blocked: engineering | [visitor privacy inventory](governance/visitor-privacy-inventory.md), [production operations](deployment/production-operations.md) | Verify proxy trust, logging/provider disclosures, rollback, monitoring, and ownership. |
| Authorized release approval | Blocked: human review | [reviewed demonstration release](reviewed-demonstration-release.md), [ETHICS.md](ETHICS.md) | Name the release/profile, record approval, and verify every public projection. |
| Public cutover and rollback | Not started | [V1/V2 reconciliation](architecture/v1-v2-reconciliation.md) | Run private E2E, parallel comparison, cutover rehearsal, then obtain explicit launch approval. |

## Roadmap

### C1 — Repository clarity and canonical readiness

**Status: Complete and verified.** Established this page as the sole product-level roadmap,
archive historical overall-roadmap inputs, clarify the Denmark launcher, and
add deterministic documentation consistency checks. This sprint must not alter
data, migration history, publication behavior, or policy meaning.

### D1 — V2 product convergence

**Status: Complete and verified for the D1 scope.** Frozen the current V2
contract and convergence gaps, captured the V1 behavioral requirements, and
created a row-free FSIS/Italy/France/Denmark readiness boundary. The data
boundary is a private test shape, not a reviewed release; visual direction and
production frontend implementation remain on the next branch.

Evidence: [contract ledger](api/v2-product-convergence-gap-ledger.md),
[V1 behavioral contract](frontend/v1-behavioral-contract.md), and
[D1 readiness report](../data/manifests/d1-data-readiness-report.json).

**Next branch:** `eli/v2-frontend-overhaul`, based on the completed D1 head.

### B3 — Repository consolidation and backend handoff

**Status: Complete and verified for repository operations.** The registered
worktree set was reduced from 80 to exactly 2: the canonical V2 checkout and
the retained dirty root checkout. The dirty root was left untouched. Fourteen
detached heads were retained under durable archive refs and a verified bundle;
the restricted private archive verified 5,784 evidence files and 3,819
content-addressed objects with no evidence or commit loss. The private archive
location and row contents remain intentionally undisclosed.

Cleanup accounting is kept by category rather than added together: 37.72 GiB
of generated caches were removed, and retired worktree content was removed in
three separately reported groups of 2.83 GiB, 8.24 GiB, and 8.66 GiB. No
publication, deployment, promotion, or human-approval state changed.

**Completed next backend step:** D2 shared private pipeline readiness now
converges the first-wave adapters on one repeatable private lifecycle, with
aggregate-only manifests, suppression/idempotency checks, and a path to later
scheduled refreshes. D3 extends that same runner to eleven facility adapters
and two evidence-event adapters; no second orchestration architecture was
added. **Next backend step:** exercise authorized live acquisition paths and
onboard the next source cohort through this same runner; do not add scheduling
until those paths are ready.

### D2 — Shared private pipeline readiness

**Status: Complete and verified for the D2 fixture/private contract and
disposable database E2E; live acquisition remains source-specific follow-up.**
The shared runner now supports one
source, an explicit selection, or all seven registered first-wave sources in a
deterministic sequential plan. It preserves source artifacts, runs the existing
private lifecycle, isolates failures, supports bounded retries and resume, and
keeps candidate output review-required with publication disabled. The seven
fixture-ready sources are `dk.smiley`, `be.locations`,
`ca.ontario.meat-plants`, `ca.cfia.federal-meat`, `fr.dgal.section-i`,
`fr.dgal.section-ii`, and `it.853-2004`.

The row-free synthetic D2 rehearsal passed all seven sources, including exact,
city, unmapped, restricted, and quarantine states, failure isolation, resume,
idempotent reporting, and the injected candidate-import boundary. The
disposable Postgres/PostGIS E2E was subsequently run twice: 35 synthetic
source records, 21 private candidate observations, 21 review events, and zero
releases were observed, with the second run inserting no duplicates. These
results establish fixture, local-artifact, and disposable private-import
readiness only; they do not establish live acquisition health, publication
approval, geocoding approval, or a recurring scheduler. See
`pipeline/common/refresh_runner.py`,
`pipeline/sources/first_wave.py`, and
`pipeline/tests/test_d2_e2e_readiness.py`.

### D3 — Source expansion and live-readiness boundary

**Status: Complete and verified for fixture/local-artifact orchestration;
live acquisition and publication remain blocked.** The shared runner now
registers exactly eleven facility sources (`dk.smiley`, `be.locations`,
`ca.ontario.meat-plants`, `ca.cfia.federal-meat`, `fr.dgal.section-i`,
`fr.dgal.section-ii`, `it.853-2004`, `us.fsis`, `de.locations`,
`fsa_approved_establishments`, and `fss_approved_establishments`) plus two
evidence-event sources (`us.aphis` and `us.inspections`).

The mixed sequential rehearsal succeeded for all 13 sources in both fixture
and local-artifact modes. The live-acquisition rehearsal selected all 13,
made zero network requests, and failed closed for all 13 because source terms
and operator authorization are not yet satisfied. Facility adapters use the
candidate boundary; APHIS and inspections use the separate private evidence
sink and cannot enter the facility importer or graph/public release path.

The D3 result is therefore private pipeline readiness, not live readiness. No
source is marked runtime healthy, no source is publication-eligible, and no
scheduler, secret, promotion, deployment, or public release was added. See
`pipeline/common/d3_live_operations.py`,
`pipeline/sources/d3_facility.py`,
`pipeline/sources/us/evidence.py`, and
`docs/d3-live-operations-onboarding.md`.

### D4 — Accountability graph persistence and evidence linking

**Status: Complete and verified for private persistence and synthetic graph
rehearsal; human identity evaluation remains open.** The 11 facility and two
evidence-event D3 handoff types now have a shared append-only private graph
import boundary. Facility candidates persist source-qualified facilities,
organizations, relationship observations, claims, and source-scoped
crosswalks. APHIS and inspection events persist in a separate evidence sink;
they cannot enter the facility importer or public graph projections.

The importer is loopback-only and requires an explicit disposable database
marker. It rejects released or universal-identity handoffs, supports bounded
batches and interrupted-run resume, and is idempotent on identical handoffs.
All imported rows remain private, review-required, privacy-pending, and
publication-ineligible. Candidate identity edges retain lower-confidence leads
with confidence score/band, matching method, contributing features,
contradictions, provenance, disclaimer, and algorithm version; they never
execute a merge, transfer claims, or authorize publication. APHIS-to-FSIS
automatic links remain zero.

The Docker-backed synthetic proof imported one facility handoff for each of 11
facility sources and one evidence handoff for each of two evidence sources,
reran all 13 with zero duplicates, and observed zero public graph rows. The
row-free control-plane rehearsal also covers corruption isolation, kind
mismatch rejection, lineage events, suppression, fail-closed private access,
and bounded 10,000-record scale. No real corpus was imported, and no human
adjudicated sample exists yet; therefore precision, recall, and production
identity quality remain unmeasured.

Evidence: `pipeline/common/graph_persistence.py`,
`pipeline/common/identity_candidates.py`,
`pipeline/tests/e2e/test_d4_graph_persistence.py`, and
`data/manifests/d4-private-graph-e2e.json`.

### D5 — Real private-corpus graph rehearsal and acquisition readiness

**Status: Complete for the demonstrated real-private scope; source-specific
graph and handoff gaps remain explicitly blocked.** Hash-verified retained
private handoffs for France Sections I/II, Italy 853/2004, FSIS, and APHIS
were restored outside the repository and exercised against a disposable
Postgres/PostGIS database. Four facility handoffs imported successfully:
51,607 source records, 35,073 source-qualified facility entities, 51,607
source-native identifier observations, and 98,490 claims. A rerun inserted
zero duplicates. The public graph projection remained empty.

The row-free analyzer observed 7,241 FSIS exact source-ID observations, 995
APHIS exact source-ID evidence observations, 39,020 Italy VAT/fiscal-identifier
candidate observations, and 5,000 probabilistic review candidates (the
configured analysis cap). Automatic merges and APHIS↔FSIS links remained zero;
precision and recall remain unmeasured because no human adjudication was
available.

This rehearsal also found two real integration gaps. Italy's handoff emitted
unknown source observation dates; the importer now falls back to the handoff
retrieval timestamp for required database lineage fields while retaining the
source uncertainty. The Italy handoff still emits no organization entities, so
its VAT/fiscal observations and probabilistic candidates are not materialized
as graph organization/candidate-edge rows. The archived APHIS handoff declares
`entity_scope=aphis_observation` rather than the D4 `evidence_event` contract,
so it remains blocked until the adapter contract is aligned. These are
recorded blockers, not inferred graph connections.

Evidence: [D5 graph analysis](d5-real-graph-analysis.md),
[D5 acquisition readiness](D5-ACQUISITION-READINESS.md),
`pipeline/common/real_private_graph.py`, and
`pipeline/common/d5_connection_analysis.py`. No raw rows or private paths are
committed here.

### D6 — Private real-edge cohort and graph API convergence

**Status: Complete for a bounded private real-edge cohort; inferred-edge
materialization and publication remain open.** The duplicate migration was
resolved to one authoritative `044_graph_connection_edges` schema. Its only
connection types are `exact` and `inferred`; grouped signals compound with
diminishing returns and penalties, and every edge carries a versioned
explanation. The private API exposes confidence, source/entity, conflict,
suppression, and cursor filters without a human-confirmed workflow or public
projection.

The disposable Postgres/PostGIS rehearsal materialized 47,375 Italy source
records, 18,689 organizations, 25,639 facilities, and 25,326 exact
source-asserted edges. It produced zero public edges and zero inferred edges
in the database pass. The offline aggregate diagnostic consumed 54,159 rows
across five authorized handoff families and returned capped pages of 100 exact
and 100 inferred candidates. Positive and negative controls were proven from
source assertions and forbidden-pair rules: 47,375 positive controls, two
negative controls, and zero automatic APHIS↔FSIS edges. No raw rows or private
paths are committed here.

Evidence: [D6 aggregate report](../data/manifests/d6-real-graph-e2e.json),
the `044_graph_connection_edges` migration, and the focused D6/API tests.
France, FSIS, and APHIS graph-edge materialization, real inferred-edge proof,
and any publication or promotion remain explicit follow-up work.

### Product convergence (remaining release work)

**Status: In progress.** Exercise the frozen contract against a named reviewed
private release, close the remaining release/revocation gaps, and carry the
behavioral contract into the frontend overhaul. France, Denmark, and US now
have sanitized private lifecycle rehearsals, but none is a reviewed release.
Keep fixture/local synthetic data and the row-free real-data-shaped corpus
available during implementation.

### Production V2 frontend

**Status: Deferred.** Build the redesigned Svelte frontend against the frozen
contract, including responsive/accessibility/performance work and complete
empty, restricted, error, provenance, and uncertainty states. Keep V1 routes and
rollback available during transition.

### First reviewed private release

**Status: Not started.** Select one bounded candidate family (FSIS is the current
leading candidate, subject to terms/privacy/review decisions), complete the
acquisition → import → review → geocoding → approval chain, and create a private
named release. APHIS research evidence remains a separate family unless an
explicit scoped relationship is approved.

### Private end-to-end trial

**Status: Not started.** Run the production-shaped frontend and API against the
reviewed private release. Test discovery, maps, profiles, evidence, exports,
suppression, revocation, mobile, accessibility, performance, and operator
recovery without public promotion.

### V1/V2 parallel comparison

**Status: Not started.** Compare route behavior, identity/suppression outcomes,
coverage labels, and user-critical journeys. Resolve differences explicitly;
do not silently replace V1 records or call absence closure.

### Controlled cutover

**Status: Not started.** Obtain explicit maintainer approval, deploy the named
release with public access paused during migration, verify current restrictions,
provider settings, rollback, monitoring, and visitor-facing disclosures, then
switch traffic while retaining a defined V1 rollback window.

### Expansion

**Status: Deferred.** Add further countries, source families, accountability
evidence, and richer story experiences only after the first complete release path
is repeatable and safe. Each addition gets its own source, privacy, identity,
geospatial, approval, and publication decision.

## Update discipline

- Update this page in the same integration change as any material readiness change.
- Every **Complete and verified** claim must link to repository evidence or a named,
  reproducible test result.
- Keep aggregate counts separate from row-level payloads; never copy private data here.
- Keep acquisition, import, review, geocoding, approval, promotion, and publication
  states explicit; do not collapse them into “complete.”
- Record the checkpoint commit/date and the evidence scope whenever the baseline changes.
- If evidence conflicts, mark the item blocked or in progress and record the conflict
  rather than choosing the more favorable claim.
- Source-specific status belongs in `source-status.json` and its supporting packet;
  this document links to it and summarizes only the product consequence.

## Decision-log rules

Record a decision here when it changes product scope, release sequencing, a launch
gate, a canonical entrypoint, or the meaning of a readiness status. Each entry
must include date, decision, scope, evidence, owner/authority, and the next review
point. Policy amendments belong in [governance/ethics-changelog.md](governance/ethics-changelog.md),
and source rights decisions belong in [architecture/source-rights-decisions.md](architecture/source-rights-decisions.md).

| Date | Decision | Scope | Evidence / authority | Next review |
| --- | --- | --- | --- | --- |
| 2026-09-20 | Establish this document as the sole product-level readiness and overall V2 roadmap authority. | V2 product completeness and V1 replacement sequencing. | C1 approved scope; governing policy remains [ETHICS.md](ETHICS.md). | At the next integration sprint or any material gate change. |
| 2026-09-20 | Keep V1 public and V2 private/local until a reviewed named release completes all launch gates. | All public application surfaces. | [V2 API contract](api/v2-contract.md), [source status](source-status.json), [reviewed release guidance](reviewed-demonstration-release.md). | Before private E2E trial. |
| 2026-09-20 | Accept the France, Denmark, and US sanitized private lifecycle rehearsals as backend readiness evidence only; no rehearsal changes approval, publication, or facility identity status. | B3 selective convergence integration. | [France rehearsal](../data/manifests/france-golden-country-private-2026-09-18.json), [Denmark rehearsal](../data/manifests/denmark-private-golden-rehearsal-2026-09-18.json), [US rehearsal](../data/manifests/us-private-golden-rehearsal-2026-09-18.json). | Re-run against a named reviewed private release before frontend cutover. |
| 2026-09-21 | Accept D6's bounded Italy source-asserted exact-edge cohort as private graph/API readiness evidence; keep inferred materialization and publication blocked. | D6 integration. | [D6 aggregate report](../data/manifests/d6-real-graph-e2e.json), authoritative 044 schema, focused and standard test suites. | Add real inferred-edge materialization and repeat the private E2E trial before frontend cutover. |
