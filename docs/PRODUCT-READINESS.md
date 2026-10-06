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

## v0 dataset release sequence

**Owner approval, 2026-10-06:** the explained 13-source subset is approved as
**v0 — Early Access**: 63,601 searchable records, 48,756 map locations,
14,845 unmapped records and 54,256 names. Keep the stated France, Denmark and
record-specific exclusions. This is the release decision, not another
candidate/scope approval. Approval is recorded, full-cohort validation passed,
and local activation built the 63,601-row approved discovery read model.
Website deployment has not occurred. The D: backup was independently restored
to `uec_v0_dev`; both databases passed the immutable-manifest, migrations and
public-count checks. The reference `uec_v0_review_r3` is read-only by default.

All future data-backed development and new integration/feature acceptance
tests use verified disposable v0 copies; preserve the frozen reference.
The [baseline workflow](development.md#approved-v0-development-baseline)
is binding; fixture-only success does not establish real-data readiness.

**Before website launch:** complete a separate **v1 dataset release**, and
provide persistent v0 historical access. Historical views must serve the
frozen release rather than silently switching to new data, while honoring
current corrections, privacy restrictions and source-rights changes. The
current active-release-only API must not make v0 disappear when v1 activates;
historical selection is a launch requirement, not a claim it already works.

The [actual publication assessment](v0-release-review.md#final-publication-assessment-2026-10-05)
preserves the approved fifteen-source candidate scope; no second scope approval
is requested. The approved exception-qualified packet specifies 63,601
curated-default listable records: 48,756 mapped and 14,845 unmapped, from 13
sources. All fifteen source snapshots and 124,414 frozen members remain
retained. The packet names the 68 precautionary privacy holds, Denmark's
58,230 non-core scope exclusions (one overlapping privacy hold), France's
2,516 rights-pending records and the Belgian unmapped limitation.
The name-import defect was repaired on 2026-10-06: 115,069 retained labels
restored, without changing frozen records or coordinates. The approved public
subset has 54,256 named records; 9,345 lack supported normalized name fields.
The [short release report](v0-release-review.md#short-release-report-2026-10-06)
replaces the earlier recommendation to accept an unnamed release.
The exact membership digest was recomputed unchanged. Record-level exceptions
pass all six actual disposable-PostGIS tests with no skips. The owner has now
given the final release approval; no further generic scope or publication
stamp is needed. Local activation and backup/restore baseline verification are
complete. Frontend/community integration now uses the approved official v0
read model: the reviewed map, database search, public record pages, bounded
downloads and local contribution intake share the API. Real-v0 acceptance
passed on both an isolated migrated restore and the persistent development
copy. Cold map startup, closing search, record selection, pan/zoom and basemap
switching were checked locally; pan/zoom and basemap switching issued no extra
map-feed requests. Intake does not add records to the released dataset.
The isolated test database and sprint worktree were cleaned up; the frozen
reference remains unchanged. This is local integration, not website deployment,
historical-release selection, public account setup or public contribution launch.

**Maintainer decision: 2026-10-03.** Dataset release names are independent of
the V2 website and the legacy V1 application. `v0` is the first public dataset
release; `v1` is a later dataset release, potentially adding countries and
source families. V0 is now approved and locally promoted; v1 does not exist yet.

1. **Candidate sprint:** the proposed UK location-recovery, Denmark integration,
   and Netherlands onboarding sprint closes the v0 candidate intake window.
   Its integrated, verified output becomes the v0 release-candidate pool, not
   an automatically approved or published dataset. Record exact source
   snapshots, hashes, transformations, counts, and outstanding exclusions.
2. **Human-review sprint:** the maintainer reviews that bounded pool and records
   source/profile-level publication decisions, representative checks, and
   specific exceptions. Do not create a blanket requirement for manual
   confirmation of every facility, geocode, or exact/inferred graph edge.
   Existing privacy, terms, evidence, and release controls still apply.
3. **Public v0 data release:** after approval and verification of the applicable
   publication controls, publish the approved snapshot as v0 and freeze its
   membership and source versions. A candidate may be excluded or deferred;
   a new country or optional frontend feature must not restart candidate intake
   or postpone v0 solely because it is unfinished.

Freeze means no silent refreshes or additions to the published snapshot.
Corrections, suppression, and necessary removals still apply to v0 and its
caches/exports under [ETHICS.md](ETHICS.md); record changes transparently.
Further acquisition may continue privately toward v1 without altering v0.
The public data release and the V1-to-V2 website cutover are separate milestones;
an unfinished optional visualization is not a data-release gate.

**Historical candidate checkpoint (2026-10-05; superseded by the approval above):**
UK, Denmark, and Netherlands private imports and
bounded geocoding are integrated. South Australia EPA, Italy 1069, and Brazil
SIF were reacquired and their exact captures imported on 2026-10-04 under the
maintainer's instruction. The [taxonomy-reconciled inventory](../data/manifests/v0-candidate-20261004-taxonomy-inventory.json)
reconciles fifteen source snapshots: 187,940 observations and 124,414
source-qualified candidate groups; 50,611 groups meet current private map
geometry/scope checks, not a globally deduplicated facility or marker count.
All fifteen handoffs passed local bridge evidence checks. The earlier
[database preflight](../data/manifests/v0-candidate-20261004-preflight.json)
found stale taxonomy caches in France I/II, Italy 853, and FSIS. The verified
[append-only reconciliation](../data/manifests/v0-taxonomy-reconciliation-20261004.json)
now appends `uec-source-crosswalk-v2` sets for all 124,414 current groups in
both the isolated copy and retained preview. The category taxonomy remains
`uec-taxonomy-v1`; original candidate rows, source observations, and earlier
v1 assignments are unchanged. No trigger was disabled or migration added.
A checksum-verified reconciled D: backup has been restored into fresh
`uec_v0_review_r3`, with existing migration 061 applied. Full candidate-only
staging of `v0-candidate-2026-10-04-r3` initially failed with repeated Scottish
taxonomy claims and rolled back. The bounded exact-repeat correction passed
all 187,940 frozen observation contracts and 91 affected tests, including real
PostGIS. The [full frozen-cohort staging receipt](../data/manifests/v0-candidate-20261004-r3-staging-custom-plan.json)
now records `candidate_only_staged`: all fifteen sources, 187,940 canonical
observations and 124,414 candidate facilities/release members. Independent SQL
checks confirmed the committed totals, fifteen represented sources, candidate
status, zero default-visible members and zero release manifests. These are
source-qualified groups, not globally deduplicated or operating facilities.
The retained preview still has zero releases and members.
At that candidate checkpoint, graph projection, human review, and public
activation were incomplete; the candidate work alone did not authorize
publication. The subsequent 2026-10-06 decision above approved v0 and local
activation completed. Public graph projection remains outside this integration
sprint. The source registry and immutable
release-manifest machinery exist, but the retained private preview is not a
populated public release. The v0 review must identify its exact source versions
and distinguish frozen candidate evidence from approved release membership. This
sequence governs near-term dataset delivery; historical sprint descriptions
below remain evidence, not reasons to reopen the expansion scope.

The bounded maintainer review and its measured evidence are routed through
[the v0 release review](v0-release-review.md); that packet is not a second
product roadmap or publication authorization.

**Historical release-enablement decision (2026-10-05; activation completed
2026-10-06):** the maintainer approved frozen
`v0-candidate-2026-10-04-r3` as the v0 scope and authorized bounded engineering
for full-cohort decision recording, public geometry parity, atomic activation
and rollback, and source-rights verification. The implementation is integrated;
50 focused local tests, including actual disposable-PostGIS cohort/geometry
proofs, passed. The final independent verification gate is all six jobs green
for the exact current `eli/v2` commit in the [Tests workflow](https://github.com/eliperez-dev/UntilEveryCage/actions/workflows/tests.yml?query=branch%3Aeli%2Fv2);
an older green run is not evidence for newer code. The initial enablement run
caught a frontend optional-property type error, reproduced and corrected with
zero Svelte check errors/warnings and all 24 focused frontend tests passing.
approval of sprint scope does not supply missing factual/privacy/rights
outcomes or authorize website launch. Candidate intake stays closed, original
evidence stays immutable, and public graph readiness remains a separate check.
The isolated candidate now has additive migrations 062/063 and an unapproved
local review template binding all fifteen scopes and 124,414 members. Source
record and observation digests are unchanged; actual cohort decisions, rights
decisions, visible members and manifests remain zero. Source reuse conditions
and the remaining operator decisions are in the [v0 packet](v0-release-review.md).

## Verified checkpoint

**Historical retained private preview checkpoint (2026-10-02):** the latest-source snapshot
contains 115,419 observations and 64,446 candidates, of which 49,580 are
map-visible (45,417 numeric source points and 4,163 coarse references); 14,866
candidate groups have no rendered point. The API's 4,886
`unmapped_candidate_count` is the unmapped location-class subset, not all
no-point candidates. NPI/Ontario/Catalonia updates were hash-verified archived
replays, not fresh acquisitions. The replay manifest records source hashes,
aggregate results, and limits. The Australian NPI Geoapify pilot's initial
24 authentication failures were preserved. After the saved key was corrected,
24 user-authorized recovery requests authenticated: 22 required review and
2 were unresolved; no point met the existing private-display rule. Three
additional diagnostic lookups did not change that rule or display state.
The 24-target pilot scope is separate from the configurable provider daily
allowance; the earlier self-imposed 24-request daily cap is not a provider
quota or a reason to delay authorized work. These baseline map counts remain
unchanged. See [source status](source-status.md) for the current run boundary.
See the [row-free pilot manifest](../data/manifests/au-npi-geoapify-pilot-20261003.json).
Catalonia has 2,370 local coarse
references and 1,997 unresolved candidates. All public/release rows remain
zero; no source release is authorized. See the [current source status](source-status.md)
and [geospatial replay manifest](../data/manifests/geospatial-replay-integration-20261002.json).

- **Baseline:** D6.2 remains the reusable-backend architecture checkpoint (2026-09-21 UTC). On 2026-09-24, seven named official sources completed strict live private E2E through acquisition, candidate processing, disposable-database import, and run verification. Their combined private result is 64,701 observations, 42,875 candidates, 41,110 map-visible candidates, and 1,765 listable but unmapped candidates. SQL verification confirmed zero public rows. These are source-scoped private observations, not publication approval or recurring service health.
- **Current public product:** V1 remains production and the public default.
- **V2 frontend:** reviewed Svelte/TypeScript map and community/search UI exist;
  integration against the approved v0 API is in progress. It is not externally
  deployed or the production replacement.
- **Public release:** v0 is approved and locally promoted, with 63,601 searchable
  records and 48,756 map locations. External website launch still requires v1,
  historical v0 access and the remaining launch gates.
- **Evidence:** D1's [contract convergence ledger](api/v2-product-convergence-gap-ledger.md),
  [V1 behavioral contract](frontend/v1-behavioral-contract.md), and row-free
  [data readiness report](../data/manifests/d1-data-readiness-report.json)
  support the architecture history. The latest source-level acquisition and
  private E2E state is summarized in the strict-live section below and
  [source-status](source-status.md); earlier B3 manifests remain historical
  backend rehearsal evidence.

### Earlier private candidate snapshots

These earlier safe aggregates are retained as checkpoint history; the
2026-09-24 strict-live section below supersedes them as the latest source-level
acquisition baseline. They describe acquisition/normalization handoffs, not
release readiness. Raw and restricted payloads remain private.

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

Supporting source evidence is routed from [source status](source-status.md) to
canonical country pages and row-free manifests. No private rows or payloads
belong in this roadmap.

### Strict live private E2E verification — 2026-09-24

All seven bounded source runs used official live data. The database contained
private candidates only; the public projection remained empty. A one-time live
E2E is not a recurring operational monitor, does not establish source
completeness, and does not resolve source-specific terms, privacy, identity,
classification, factual-review, or release-approval gates.

The per-source acquisition routes, observation/candidate counts, recurring
monitor state, and open source-specific gates are in the canonical
[source-status table](source-status.md#current-baseline).
Across the combined candidate set, 41,110 were map-visible and 1,765 were
listable but unmapped. These are private readiness counts only. No public rows
were created, and no source is authorized for public release by this result.

The latest verified run for each source can differ from the combined 2026-09-27
database checkpoint above. Denmark and CFIA were verified on 2026-10-01; each
source is configured as eligible for the private preview but is absent from the
active preview database. Their strict runs used isolated disposable databases.

| Source | Latest verified run (UTC) | Parsed | Accepted private candidates | Quarantined | Mapped / unmapped | Active preview DB | Open blockers |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| Denmark Find Smiley | 2026-10-01 04:01:38 | 58,815 | 58,765 | 50 | 0 / 58,765 | No | All accepted candidates held for privacy review; category, currentness, and publication review remain open. |
| CFIA federal meat | 2026-10-01 03:54:16 | 874 | 858 | 16 | 0 / 858 | No | Source effective date and Last-Modified are absent; privacy, completeness, and publication review remain open. |

### D1 real-data-shaped readiness boundary

D1 established a row-free, private readiness boundary for FSIS, Italy, France,
and Denmark. These are not approved or public facilities:

| Measure | Strict aggregate | Interpretation |
| --- | ---: | --- |
| Provisional candidate groups | 35,073 source-scoped | FSIS 7,241; Italy 25,316; France 2,516 (1,449 + 1,067). The separate France union metric is 2,283 after subtracting 233 exact cross-section overlap signals; no records are merged across sources. |
| Usable nonzero source coordinate groups | 31,504 | FSIS 7,241; Italy 24,263; coordinate/privacy review pending. |
| City/postal coarse groups | 3,336 | Italy 1,053; France union 2,283; includes city fallback for 486 rejected zero/zero coordinate groups. |
| Rejected zero/zero coordinate groups | 486 | Italy groups with no usable nonzero pair; all have actual source city values and are coarse only. |
| Public API rows | 0 | Publication is blocked pending terms, privacy, review, approval, and release authority. |
| Denmark latest source run | 58,815 parsed / 58,765 accepted / 50 quarantined | 2026-10-01 private E2E; accepted candidates are not facility-identity or publication claims. |

The complete row-free corpus and its limitations are recorded in
[d1-data-readiness-report.json](../data/manifests/d1-data-readiness-report.json)
and [d1-real-data-shaped-test-corpus.json](../data/manifests/d1-real-data-shaped-test-corpus.json).
The B3 rehearsals now exercise the private lifecycle with sanitized fixtures and
row-free aggregate reports for France, Denmark, and the US. They do not assert
that the corresponding real captures are approved, and they create no public
API rows, release promotion, deployment, or human approval. Database-backed
E2E remains an environment-dependent follow-up gate.

### Retained private preview taxonomy application — 2026-10-01

The authoritative retained private preview database (`uec` in
`uec-offline-fsis-private-postgres-1`) received the additive taxonomy migrations
at 2026-10-01 19:05:21 UTC and an idempotent, source-scoped `uec-taxonomy-v1`
projection. Its latest-source baseline remains 90,164 observations, 60,218
candidates, 36,840 numeric plus
1,793 coarse map-visible candidates (38,633 total); the taxonomy write added
35,073 candidate assignment sets, 35,674 assignment rows, and four immutable
source crosswalks without changing source rows or the public projection. Coverage
is intentionally partial:

All three migration ledger entries were applied at 19:05:21 UTC. The verified
full logical backup is
`D:\UntilEveryCage-backups\database\taxonomy-pre-reprojection-authoritative-20261001-113806\uec.logical.dump`
(SHA-256 `2EF936FCB99CB973618AAF74AE1655EC874DA799EDE2C6F426DDBD6D22162A93`);
the backup was restored and its full latest-source ledger compared before
application. No backup was deleted.

| Source | Latest candidates | Persisted taxonomy coverage |
| --- | ---: | --- |
| `fr.dgal.section-i` | 1,449 | Mapped from exact normalized artifact evidence |
| `fr.dgal.section-ii` | 1,067 | Mapped from exact normalized artifact evidence |
| `it.853-2004` | 25,316 | Explicitly unclassified; no direct category mapping asserted |
| `us.fsis` | 7,241 | 7,082 unmapped and 159 unclassified; no positive primary assignment asserted |
| `au.npi.facilities`, `au.sa.epa.licensed-activities`, `be.locations`, `es.cat.feed-sandach`, `fsa_approved_establishments`, `it.1069-2009` | 25,145 combined | No assignment rows written; source artifacts were not recovered with exact hash/identity evidence, so these remain outside this partial projection and require artifact recovery before reprojection. |

Aggregate persisted rows comprise 2,124 `processing_and_preparation` and 993
`slaughter` mapped assignments, 25,475 `unclassified` candidate sets, and 7,082
`unmapped` candidate sets. This is not all-source taxonomy coverage or source
classification approval. Original preview/category fields, observation and
candidate counts, coordinate/map counts, and public rows were not changed. The
database projection was replay-checked for idempotency. Live API/browser
verification was not performed in this application context; preview-service
authorization and UI behavior remain a separate validation gate. The verified
database backup and per-source recovery matrix are retained outside the
repository in the approved private backup location.

### Historical source evidence recovery checkpoint — 2026-10-01

The following dated figures describe the pre-geospatial-replay snapshot and
are retained as history. The current 2026-10-02 retained-preview totals and
source-specific replay state are stated in the Verified checkpoint above.

The six recovered runs are now the latest source evidence in the authoritative
private database. Latest-per-source totals are 90,166 observations, 60,220
candidates, and 38,634 map-visible groups (36,841 numeric, 1,793 coarse); all
60,220 candidate assignment sets and 61,775 assignment rows are retained, with
zero public rows. The only baseline delta is IT 1069 (+2 observations, +2
candidates, +1 map-visible). France, IT 853, and FSIS assignments remain
preserved. Belgium has 1,794 directly mapped grouped candidates; UK FSA has
3,204 partial and 1,087 unmapped derived groups. IT 1069 and Spain remain
unclassified, while the two Australian sources remain candidate/ambiguous;
none of those four sources gained a confirmed positive primary assignment.
Exact run IDs, source counts, retained artifact hashes, and the pre-import
backup checksum are recorded in the
[source evidence integration manifest](../data/manifests/source-evidence-integration-20261001.json).

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
| Frontend product | In progress | V2 remains a private developer preview; V1 vanilla JavaScript remains public. The [frontend specification](frontend/README.md), [V1 behavior contract](frontend/v1-behavioral-contract.md), and staged [implementation sequence](frontend/implementation-sequence.md) are the active design and migration references. | Build the approved Map and Database frontend; close linked contract gaps before enabling unsupported record families. |
| Data acquisition | In progress | Several current private captures and source adapters exist; many countries remain reconnaissance-only or adapter/fixture-only. | Select one bounded first release and complete its source-specific terms and provenance review. |
| Identity and reconciliation | Complete and verified for private graph semantics | Source-qualified exact and inferred edges are retained with score, confidence band, method, signals, contradictions, provenance, disclaimer, and ruleset metadata. The graph has no human-confirmed state; cross-source universal merges and claim transfer are never automatic. | Continue source-specific quality/terms/privacy work; publication still requires independent release approval. |
| Geospatial readiness | In progress | Geocoding is disabled or tightly bounded in current private handoffs; provider, precision, privacy, and review state must remain explicit. | Complete source-specific coordinate/privacy review and a production geocoder/provider decision. |
| Privacy and suppression | In progress | Policy and synthetic suppression paths exist, but independent durable restriction, replay, cache, and cross-V1/V2 propagation controls remain release gates. | Implement and exercise the durable ledger, pre-service restore gate, and suppression crosswalk. |
| Operations and deployment | Blocked: engineering | Local/private environments and runbooks exist; production proxy trust, visitor/provider audit, artifact inventory, rollback, and operational ownership are not fully verified. | Complete deployment/provider audit and an operator-run private release drill. |
| Publication and release authority | Blocked: human review | No current candidate has completed all source, privacy, factual, project-approval, and release-authority gates. | Obtain authorized review for the bounded first release; do not infer approval from acquisition or tests. |

### E2 Australia NPI source onboarding

E2 added `au.npi.facilities` to the shared source registry and runner. Its
strict live private E2E now verifies 8,140 input rows, 8,116 listable
candidates, and 24 quarantined rows. An exact same-database importer replay
preserved those counts; no coordinates were map-visible and no public rows
were written. This one-time result does not establish complete NPI coverage,
recurring health, privacy clearance, or publication approval. Preserve annual
release/correction history and keep source addresses/coordinates private.
Synthetic contract tests still cover schema-drift detection and lifecycle
outputs. See [E2 aggregate evidence](../data/manifests/e2-australia-npi.json)
and [source status](source-status.md).

### Catalonia SANDACH source onboarding

The `es.cat.feed-sandach` lane completed one strict live private E2E for the
Catalonia feed register: 12,117 accepted observations, 224 quarantined rows,
and 4,367 municipality-grouped/listable candidates. Exact same-database replay
preserved the aggregate and the authenticated source-scoped list/search/detail
checks passed; the no-coordinate source returned an empty viewport and zero
public rows. This is Catalonia-only, one-time verification, not Spain-wide
coverage, privacy clearance, recurring monitoring, or publication approval.

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
| Identity and factual review | Blocked: human review | [US source boundary](countries/us/README.md), [Italy source research](country-recon-it.md) | Adjudicate held links, quarantines, and contradictions without name/address guessing. |
| Coordinate and address privacy | In progress | [geospatial readiness](current-geospatial-readiness.md), [geocoding operator](geocoding-operator.md) | Complete precision, residential/private-location, provider, and review-state checks. |
| API and release contract | Complete and verified | [V2 API contract](api/v2-contract.md), [D1 convergence ledger](api/v2-product-convergence-gap-ledger.md), [MVP claim evidence](governance/v2-mvp-claim-evidence.md) | Exercise the frozen contract against a named reviewed candidate release. |
| Suppression and revocation | Blocked: engineering | [suppression runbook](governance/suppression-runbook.md), [release manifest guidance](architecture/release-manifest-verification.md) | Add durable restriction ledger, replay gate, cache invalidation, and V1↔V2 crosswalk. |
| Frontend accessibility and performance | In progress | [frontend README](../frontend/README.md), [frontend backlog](frontend/roadmap.md), [reviewed demonstration plan](reviewed-demonstration-release.md) | Redesign and test responsive, accessible, performant real-data-shaped views; keep unsupported record/search capabilities linked as explicit gaps. |
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

**Status: Launchpad and design specification complete; implementation deferred.**
E1 provides a one-command local stack, deterministic representative and scale
fixtures, typed public graph client/contract checks, and a documentation-only
two-destination Map/Database design package grounded in the V1 behavior
inventory. Build the redesigned Svelte frontend against that package, including
responsive/accessibility/performance work and complete empty, restricted,
error, provenance, and uncertainty states. Keep V1 routes and rollback
available during transition.

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
| 2026-10-06 | Approve and locally promote v0 — Early Access; establish it as the real-data development baseline. | 13-source curated subset: 63,601 searchable, 48,756 mapped, 14,845 unmapped; frozen reference and verified writable copy. Website launch requires v1 and historical v0 access. | Maintainer final publication approval; [baseline contract](../pipeline/contracts/development-baseline.json), [baseline workflow](development.md#approved-v0-development-baseline), and short v0 release report. | Verify frontend/community integration against a disposable v0 copy; no second generic publication stamp. |
| 2026-10-05 | Approve the frozen fifteen-source candidate as v0 scope, using the public label v0; authorize bounded release-enablement engineering, not website launch. | Exact `v0-candidate-2026-10-04-r3`, cohort recording, geometry parity, activation/rollback, and source-rights checks; no new countries or platform overhaul. | Maintainer approval in this chat; [v0 review packet](v0-release-review.md). Source-specific rights, privacy and publication outcomes remain separate recorded decisions. | At integrated tests/CI and before any real publication decision or promotion. |
| 2026-10-03 | Close v0 candidate intake after the UK/Denmark/Netherlands expansion sprint, then conduct human review and publish an approved frozen v0 dataset; later expansion belongs to v1. | Dataset release sequence, separate from V2 website delivery and legacy V1. | Maintainer instruction in this chat; [v0 release sequence](#v0-dataset-release-sequence). Candidate status is not publication approval; applicable ethics and publication controls remain required. | At candidate-sprint integration and before public v0 publication. |
| 2026-09-20 | Establish this document as the sole product-level readiness and overall V2 roadmap authority. | V2 product completeness and V1 replacement sequencing. | C1 approved scope; governing policy remains [ETHICS.md](ETHICS.md). | At the next integration sprint or any material gate change. |
| 2026-09-20 | Keep V1 public and V2 private/local until a reviewed named release completes all launch gates. | All public application surfaces. | [V2 API contract](api/v2-contract.md), [source status](source-status.json), [reviewed release guidance](reviewed-demonstration-release.md). | Before private E2E trial. |
| 2026-09-20 | Accept the France, Denmark, and US sanitized private lifecycle rehearsals as backend readiness evidence only; no rehearsal changes approval, publication, or facility identity status. | B3 selective convergence integration. | [France rehearsal](../data/manifests/france-golden-country-private-2026-09-18.json), [Denmark rehearsal](../data/manifests/denmark-private-golden-rehearsal-2026-09-18.json), [US rehearsal](../data/manifests/us-private-golden-rehearsal-2026-09-18.json). | Re-run against a named reviewed private release before frontend cutover. |
| 2026-09-21 | Accept D6's bounded Italy source-asserted exact-edge cohort as historical private graph/API readiness evidence; D6.1 supersedes its inferred-edge wiring gap. | D6 integration. | [D6 aggregate report](../data/manifests/d6-real-graph-e2e.json), authoritative 044 schema, focused and standard test suites. | Complete D6.2 full-corpus runtime and source-boundary gates before frontend cutover. |
| 2026-09-21 | Accept D6.1 matcher/persistence wiring and a bounded authorized real-data rehearsal as private runtime evidence; keep full-corpus and release claims blocked. | D6.1 matcher, private persistence, and API. | Integrated commit `7cf766f1`; 343-row retained Italy subset produced 207 inferred edges, one conflicting control, one negative control, 100-row API page, idempotent rerun, and zero public edges; [D6.1 report contract](../pipeline/common/d61_verification.py). | Run the full retained corpus in a bounded production-shaped job; keep public projection empty. |
| 2026-09-22 | Define exact and inferred as the only private graph connection types; do not add a human-confirmed state or make adjudication a prerequisite for private edge persistence. | D6.2 contract freeze lane. | [Backend contract freeze](api/v2-backend-contract-freeze.md), [graph contract](api/private-graph-contract.md), and graph/API tests. | Revisit only if a future product decision changes graph semantics. |
| 2026-09-22 | Accept D6.2 as the final reusable-backend architecture checkpoint; freeze major backend redesign while continuing source onboarding, deployment, and release work. | D6.2 integration. | [D6.2 closure manifest](../data/manifests/d62-backend-closure.json), full retained Italy rehearsal, source-boundary checks, legacy ledger, contract-freeze tests, and standard suite. | Begin serious frontend work and treat future backend changes as measured maintenance or source-specific onboarding. |
| 2026-09-22 | Accept E1 as the frontend launchpad/design checkpoint; keep the existing V2 UI disposable and expose graph relationships only through the release-scoped public projection. | E1 integration. | [Frontend design authority package](frontend/README.md), [development dataset boundary](frontend-development-dataset.md), [public graph contract](api/public-graph-contract.md), launchpad and typed-client tests. | Implement the fresh Map and Database frontend after maintainer review; benchmark map rendering at the documented synthetic scale. |
| 2026-09-22 | Accept E2 Australia NPI onboarding as an implemented private adapter/runner contract, while keeping live acquisition, local-artifact import, privacy/terms review, and publication blocked. | `au.npi.facilities`. | [E2 aggregate evidence](../data/manifests/e2-australia-npi.json), NPI adapter and shared-runner tests. | Provide the retained artifact for a real local-artifact rehearsal and review source-specific release gates. |
| 2026-09-22 | Keep V1 public during the V2 redesign; treat the earlier V2 preview as disposable and retain the approved Map/Database design and migration stages. | Frontend direction and V1/V2 transition. | [Frontend design package](frontend/README.md), [V1 behavioral contract](frontend/v1-behavioral-contract.md), and [frontend implementation sequence](frontend/implementation-sequence.md). | Revisit only if the approved design or cutover gates change. |
