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

- **Baseline:** repository checkpoint `D6.2 integration` (full retained Italy-corpus runtime, source-boundary contract, legacy ledger, and frontend contract freeze; 2026-09-21 UTC). Major backend architecture is now frozen.
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
| Backend and database | Complete and verified for reusable architecture | D6.2 completed the full retained Italy-corpus matcher/import path, source-boundary runner contract, legacy evidence ledger, and frontend-facing contract freeze. Major backend redesign is frozen. | Continue country/source onboarding, deployment operations, and release work without reopening platform architecture unless a measured gap requires it. |
| API contract | Complete and verified | D1 froze the current frontend-facing DTO/query contract, wire schemas, compatibility notes, and convergence gaps with targeted drift tests. It is exercised against synthetic/local contracts, not a reviewed real release. | Exercise the frozen contract against a named reviewed private release. |
| Frontend product | In progress | V2 is a developer preview using fixtures/local synthetic data; V1 vanilla JavaScript remains public. | Approve information architecture and visual direction, then build a production Svelte frontend. |
| Data acquisition | In progress | Several current private captures and source adapters exist; many countries remain reconnaissance-only or adapter/fixture-only. | Select one bounded first release and complete its source-specific terms and provenance review. |
| Identity and reconciliation | Complete and verified for private graph semantics | Source-qualified exact and inferred edges are retained with score, confidence band, method, signals, contradictions, provenance, disclaimer, and ruleset metadata. The graph has no human-confirmed state; cross-source universal merges and claim transfer are never automatic. | Continue source-specific quality/terms/privacy work; publication still requires independent release approval. |
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
rehearsal.** The 11 facility and two
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
and bounded 10,000-record scale. No real corpus was imported. Precision/recall
against an adjudicated sample is not a prerequisite for retaining private
exact or inferred edges; publication quality, source terms, privacy, and
release approval remain separate gates.

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
APHIS exact source-ID evidence observations, and 39,020 Italy VAT/fiscal-
identifier candidate observations. Its historical 5,000 probabilistic-candidate
diagnostic cap is superseded by the D6.1 indexed, resumable matcher; it is not a
product storage limit. Automatic merges and APHIS↔FSIS links remained zero.

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

**Status: Historical bounded exact-edge cohort; superseded by D6.1 for inferred
edge materialization.** The duplicate migration was
resolved to one authoritative `044_graph_connection_edges` schema. Its only
connection types are `exact` and `inferred`; grouped signals compound with
diminishing returns and penalties, and every edge carries a versioned
explanation. The private API exposes confidence, source/entity, conflict,
suppression, and cursor filters without a human-confirmed workflow or public
projection.

The disposable Postgres/PostGIS rehearsal materialized 47,375 Italy source
records, 18,689 organizations, 25,639 facilities, and 25,326 exact
source-asserted edges. It produced zero public edges and zero inferred edges in
the database pass because the pre-D6.1 persistence path did not invoke inferred
materialization. The offline aggregate diagnostic consumed 54,159 rows across
five authorized handoff families and returned API pages of 100 exact and 100
inferred candidates. Positive and negative controls were proven from source
assertions and forbidden-pair rules: 47,375 positive controls, two negative
controls, and zero automatic APHIS↔FSIS edges. No raw rows or private paths are
committed here.

The D5 collision count remains explicitly classified as zero repetition, zero
expected fanout, zero true conflict, zero malformed, and zero missing; D5 had
no private row payloads in its checked-in analyzer, so this is not a
corpus-wide absence claim.

Evidence: [D6 aggregate report](../data/manifests/d6-real-graph-e2e.json),
the `044_graph_connection_edges` migration, and the focused D6/API tests.
France, FSIS, and APHIS graph-edge materialization and any publication or
promotion remain source/release follow-up work; D6.1 supplies the private
inferred-edge proof for its bounded authorized subset.

### Product convergence (remaining release work)

**Status: In progress.** Exercise the frozen contract against a named reviewed
private release, close the remaining release/revocation gaps, and carry the
behavioral contract into the frontend overhaul. France, Denmark, and US now
have sanitized private lifecycle rehearsals, but none is a reviewed release.
Keep fixture/local synthetic data and the row-free real-data-shaped corpus
available during implementation.

### D6.1 — Real inferred-edge verification and API/reporting gate

**Status: Complete for bounded authorized real materialization; full-corpus
runtime remains the final D6.2 gate.** The
D6.1 aggregate report schema records candidate totals, persisted exact/inferred
totals, ambiguous blocks and reason counts, negative/conflicting controls, API
page observations, and the zero-public-output invariant. The matcher now uses
deterministic indexed blocks with resumable batches, explicit oversized-block
reporting, source-qualified endpoints, and no global 5,000-generation cap.
The private persistence path invokes that matcher before bounded idempotent
edge upserts. Private API pages remain limited to 100 rows per response; this
is a page bound, not a storage cap. Inferred responses retain source-qualified
evidence references, match/ruleset metadata, and the disclaimer that confidence
is a deterministic ruleset estimate rather than a measured probability.
Inferred edges never merge identities, transfer claims, or authorize
publication.

The mandatory disposable Docker/Postgres rehearsal consumed one authorized
retained Italy handoff subset (343 real rows selected from a 41,849-row source
handoff) and persisted 207 inferred edges, one conflicting control, and one
negative control. The API-shaped database page returned 100 inferred edges,
the rerun was idempotent, and the public relationship projection remained at
zero. This proves runtime wiring and the private boundary for the bounded
subset; it is not a claim that the entire retained corpus has been imported.
Inferred edges are algorithmic evidence, not human-confirmed edges, and remain
private until an independent release/profile permits publication. No private
rows, raw paths, or real-data fixture are committed. Full-corpus runtime
counts and any release/publication claim remain blocked.

Evidence: integrated at `7cf766f1` and verified by the operator-retained
aggregate D6.1 rehearsal report; [D6.1 report contract](../pipeline/common/d61_verification.py),
[D6.1 diagnostic](../pipeline/scripts/diagnostics/d61-verification.py),
[aggregate/API tests](../pipeline/tests/test_d61_verification.py), and the
[mandatory real rehearsal assertion](../pipeline/tests/e2e/d61_rehearsal.py).

### D6.2 — Backend architecture closure and contract freeze

**Status: Complete and verified; final foundational backend sprint.** D6.2 closes the
remaining seams without adding countries, redesigning graph semantics, or
introducing scheduling/publication. Its gates are: full retained-corpus
inferred-edge runtime with bounded memory and deterministic resume;
source-runner operational states that fail closed before unauthorized network
access; metadata-only certification of the checked-in legacy archive; and the
frontend-facing DTO/error/pagination/provenance contract freeze.

When integration evidence passes, this sprint marks the reusable backend
architecture as complete and frozen for frontend integration. Continuing work
then becomes source onboarding, source-specific acquisition/terms/privacy,
deployment, and release operations—not a new backend architecture phase.
Human review remains a gate for rights, privacy, factual claims, approval, and
publication. It is not a graph connection state or a prerequisite for private
exact/inferred edge persistence.

The mandatory disposable Docker/Postgres rehearsal consumed 41,849 accepted
Italy observations and accounted for 5,526 quarantined source rows. The
disk-backed matcher staged 41,849 rows, considered 67,323 pairs, emitted 776
candidate pairs, and persisted 267 distinct private inferred edges (one
conflicting control). It completed in 1,047.5 seconds with observed Python
working-set memory of approximately 56 MiB; no global candidate cap was used.
The rerun reported 41,849 already-present items and inserted zero duplicates;
a controlled persisted-checkpoint resume also completed from offset 41,849 with
unchanged edge counts.
The authenticated private API traversed 267 edges as pages of 100, 100, and 67;
public rows and edges remained zero. Endpoint placeholders were zero and all
persisted edges remained private and not eligible for publication.

The source-boundary lane now reports honest live, assisted, terms-blocked,
schema-drift, and failed states for the 13 registered D3 sources, preserving
previous validated state and failing closed before unauthorized network access.
The legacy ledger certifies 63 checked-in artifacts by aggregate hash/size
metadata only; all remain metadata-only and not eligible for publication.

Evidence: [D6.2 aggregate closure manifest](../data/manifests/d62-backend-closure.json),
[backend contract freeze](api/v2-backend-contract-freeze.md), [legacy status
ledger](../data/manifests/legacy-status.json), the standard suite (361 Python
tests plus 64 adapter/contract tests), Rust tests (83), and the hosted CI run.
No private rows or private filesystem paths are committed.

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
| 2026-09-21 | Accept D6's bounded Italy source-asserted exact-edge cohort as historical private graph/API readiness evidence; D6.1 supersedes its inferred-edge wiring gap. | D6 integration. | [D6 aggregate report](../data/manifests/d6-real-graph-e2e.json), authoritative 044 schema, focused and standard test suites. | Complete D6.2 full-corpus runtime and source-boundary gates before frontend cutover. |
| 2026-09-21 | Accept D6.1 matcher/persistence wiring and a bounded authorized real-data rehearsal as private runtime evidence; keep full-corpus and release claims blocked. | D6.1 matcher, private persistence, and API. | Integrated commit `7cf766f1`; 343-row retained Italy subset produced 207 inferred edges, one conflicting control, one negative control, 100-row API page, idempotent rerun, and zero public edges; [D6.1 report contract](../pipeline/common/d61_verification.py). | Run the full retained corpus in a bounded production-shaped job; keep public projection empty. |
| 2026-09-22 | Define exact and inferred as the only private graph connection types; do not add a human-confirmed state or make adjudication a prerequisite for private edge persistence. | D6.2 contract freeze lane. | [Backend contract freeze](api/v2-backend-contract-freeze.md), [graph contract](api/private-graph-contract.md), and graph/API tests. | Revisit only if a future product decision changes graph semantics. |
| 2026-09-22 | Accept D6.2 as the final reusable-backend architecture checkpoint; freeze major backend redesign while continuing source onboarding, deployment, and release work. | D6.2 integration. | [D6.2 closure manifest](../data/manifests/d62-backend-closure.json), full retained Italy rehearsal, source-boundary checks, legacy ledger, contract-freeze tests, and standard suite. | Begin serious frontend work and treat future backend changes as measured maintenance or source-specific onboarding. |
