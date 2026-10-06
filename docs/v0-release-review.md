# v0 dataset release review

**Owner:** project maintainers. **Purpose:** guide the bounded human review and
freeze of the first public dataset version. This document is not release
approval, a publication record, or evidence that candidate intake has closed.
The controlling roadmap is [PRODUCT-READINESS.md](PRODUCT-READINESS.md); the
governing requirements are [ETHICS.md](ETHICS.md).

## Final publication assessment (2026-10-05)

### Short release report (2026-10-06)

**ELI5:** We had the records, but our importer threw away their name tags.
We fixed it and restored **115,069 facility/business labels** from the retained
files. No records were deleted, no locations changed, and nothing was fetched
again. The dataset has **not been published yet**.

**Recommendation: release the 13-source subset below as v0.**

| Proposed v0 output | Records |
| --- | ---: |
| Searchable | 63,601 |
| On the map | 48,756 |
| Searchable but unmapped | 14,845 |
| With restored names | 54,256 |
| Without supported name fields | 9,345 |

The unnamed records are from South Australia EPA (41), Belgium (1,794),
Brazil (3,143), and Catalonia (4,367). They need source IDs as labels unless
their names are recovered separately; this repair did not invent names or
extract ambiguous operator/contact fields. These are source-qualified records,
not a globally deduplicated count of physical sites.

**Keep the existing exclusions:** France I/II await a redistribution basis;
Denmark contributes its 565 core records; the previously identified privacy
exceptions stay withheld. The full 124,414-member frozen pool is unchanged.

**Verification:** all 16 focused tests passed against disposable PostGIS,
including dry-run, apply, replay, unchanged evidence and wrong-target rejection.
The real repair filled blank names only. The
[aggregate receipt](../data/reports/v0-name-repair-20261006.json) holds the exact
counts and digests; integrated CI is tracked on `eli/v2`.

The recommendation to accept an entirely unnamed release is superseded.
The details below are the earlier assessment and supporting evidence.

<details>
<summary>Earlier assessment and detailed release evidence</summary>

**Approved candidate scope remains unchanged:** fifteen frozen source snapshots,
187,940 observations and 124,414 source-qualified groups. The earlier
twelve-source recommendation was not a maintainer-approved scope change and
has been removed. No second candidate/scope approval is requested.

**Decision requested: the final, exception-qualified v0 publication stamp.**
This is not another candidate or scope approval. The decision below uses the
actual frozen cohort and preserves its full membership. Nothing has been
published, and the automated checks are not individual factual verification
or a guarantee of privacy/legal compliance.

### The publication decision in one place

| Proposed curated-default v0 output | Measured count |
| --- | ---: |
| Listable source-qualified records | 63,601 |
| Mapped records | 48,756 |
| Explicitly unmapped records | 14,845 |
| Sources contributing public records | 13 of the 15 frozen sources |
| Retained frozen membership, unchanged | 124,414 |

These are **proposed output counts, not published counts or globally
deduplicated physical facilities**. A read-only what-if used the shared
geometry selector, kept its geometry/provenance checks, and applied the
specific proposed exclusions below. Approval predicates were neutralized
only to measure the proposal; no approval events or visibility were written.
The complete member digest was recomputed and matches
`9aa0321f555c670c7454d3dcee8a00ee8c6a33845c8440cf94f23bed9b65fd2b`.

The stamp would accept these explicit treatments:

- **Privacy exceptions:** withhold 55 NPI, 12 Italian 1069 and one explicitly
  restricted Danish record. These 68 are precautionary flags, not findings
  that all are residences. The Danish record overlaps the scope exclusion
  below, so it is not subtracted twice. All 87 FSA withheld-address records
  have null canonical coordinates; do not reconstruct their withheld location.
- **Denmark:** publish the existing source-core 565 records, including 422
  mapped and 143 unmapped. Retain 58,230 non-core records privately for now:
  57,745 `other_regulated_premises` and 485 processing records outside the
  source's core scope. This does not classify them as unsafe or delete them;
  an optional broader public filter is not part of this default v0 decision.
- **France I/II:** retain all 2,516 records in the frozen pool, but do not
  publish them under an invented redistribution clearance. The exact
  [section I catalogue](https://www.data.gouv.fr/datasets/viandes-dongules-domestiques-meat-of-domestic-ungulates)
  and [section II catalogue](https://www.data.gouv.fr/datasets/viandes-de-volailles-et-lagomorphes-meat-from-poultry-and-lagomorphs)
  state “License Not Specified”; the ministry notice has conflicting reuse
  context. No fresh permission is required merely because a licence label is
  missing, but a defensible applicable distribution basis remains unresolved.
- **Other source rights:** accept the scoped reuse bases and attribution,
  snapshot-date, licence-exception and no-endorsement conditions in the source
  table below. Keep source licences distinct; do not assign a blanket CC0
  licence to the combined product. Preserve OSM/Geoapify attribution and
  mixed-coordinate origin rather than treating all points as government-only.
- **Known output limits:** the missing canonical facility names are an importer
  defect being repaired before publication, not an accepted release limitation.
  Belgium's 1,793 private locality points
  remain unmapped in the staged selector; its 1,794 records stay listable.
  No additional geocoding or identity-migration sprint is required for that
  disclosed Belgium limitation.

The proposed safety method is source-scoped public-field restriction plus a
full-population automated screen of retained address evidence, staged city
fields and explicit source restrictions, with the measured exceptions above.
It is **not** a representative manual residential assessment, a universal
multilingual detector, or factual confirmation of every facility. The stamp
must expressly accept that bounded method and its residual limits; absence of
a regex match is not independently a privacy clearance. Raw addresses,
contact fields, provider queries/responses and original payloads remain out
of public data-product rows. New identifying fields or source versions do not
inherit this decision.

**Stamp wording:** “I approve the exception-qualified v0 curated-default
dataset publication described in this packet for
`v0-candidate-2026-10-04-r3`, profile `official`, its exact frozen artifact and
member bindings, the stated screening method, source conditions, exclusions,
counts and output limitations. I authorize recording those scoped decisions,
validation, artifact generation and controlled dataset activation after the
integrated code's required CI passes.”

This authorizes the dataset, **not website deployment, community-data
publication, public graph activation, or certification of government facts**.
Application must recheck the exact digest, exclusions, rights and suppression
state; a changed binding or actual failed check is a specific blocker, not
grounds for another generic scope-approval cycle. Factual review remains
`unreviewed`, independently of project release approval.

### Actual evidence, not another proposed scope

The [row-free assessment receipt](../data/reports/v0-publication-assessment-20261005.json)
records read-only SQL against isolated `uec_v0_review_r3`, the existing release
validator, and a separate geometry-only what-if using the existing selector.
No source observations, candidate membership, review/rights events, release
state or public projection were changed.

| Check | Actual result | Meaning |
| --- | --- | --- |
| Candidate membership | 124,414 groups across fifteen sources | Matches frozen group count; not globally deduplicated physical facilities. |
| Release state | Candidate; zero visible members, cohort review documents, rights decisions and manifests | No publication occurred. |
| Existing validator | Blocked: `no_public_eligible_records`; zero duplicate observations and validation errors | Lack of current approval is expected before the stamp. The reported rights gate is vacuous: zero visible rows means zero evaluated rights requirements. It does not clear the sources. |
| Existing English address-risk signal applied to retained private evidence | 37 NPI groups; 12 Italy 1069 groups | Cases to assess or withhold, not confirmed residences. No-match is not clearance; the detector is not a universal multilingual residential test. |
| Explicit source restrictions | One Danish restricted group; 87 FSA withheld-address groups | Restrictions must survive publication. Withheld-address records may remain eligible and unmapped if their remaining fields are safe; do not reconstruct their location. |
| Canonical facility fields | Zero nonempty canonical names and street addresses | This staged projection omitted those fields; it does not mean the upstream evidence lacks them. Null names are permitted by the data-product contract, but this is a material search/detail usability limitation, not a new legal approval gate. |
| Geometry-only what-if, without privacy/rights exceptions | 48,818 mapped groups; 75,596 unmapped groups | Not approved/public totals. Approval eligibility was neutralized only in the read-only query to measure existing geometry behavior. |
| Belgium geometry parity | 1,793 private locality points; zero mapped groups in the staged selector | The staged observations have null canonical coordinates and label locality metadata `source_coordinates`/`city_postal`. They remain unmapped in the public selector. This is an actual projection discrepancy, not missing acquisition. |

The per-source geometry measurements are in the receipt. Source-location
fallbacks preserve 24,263 Italian 853 and 7,241 FSIS points despite absent
display-location discriminators. The initial diagnostic that tested only the
display-location discriminator was incomplete; the final 48,818 total comes
from the shared selector with its real fallback logic. It must not be
substituted for the previous 50,611 private-map count or represented as a
post-approval marker count.

### Source-rights assessment update

The exact
[national-government catalogue entry for Catalonia](https://datos.gob.es/es/catalogo/a09002970-registro-de-establecimientos-del-sector-de-la-alimentacion-animal-y-del-ambito-de-los-sandach)
identifies dataset `m48e-zdz9` and links its licence to
[Generalitat's reuse licence](https://web.gencat.cat/ca/generalitat/dades-indicadors/dades-obertes/llicencies).
This resolves the earlier missing dataset-to-licence association; the proposed
Catalonia deferral on that ground is withdrawn. Attribution, update-date,
no-endorsement and stated exception handling remain applicable. It is evidence
for the final scoped decision, not a retroactive public-release event.

France remains a named publication exception, not an unresolved whole-release
scope proposal:
the [Ministry notice](https://agriculture.gouv.fr/mentions-legales) contains
reuse/integrity and commercial-use restrictions alongside an Etalab footer.
This assessment does not silently choose the most permissive clause or remove
France from the approved frozen pool. The proposed final stamp withholds only
its public distribution while preserving its evidence.

The Italian catalogues identify IODL v2.0 and some OSM-derived coordinates
without row-level lineage. OSM is usable under its terms, not banned; preserve
the mixed-origin disclosure and record the applicable distribution treatment.
[OSM licensing](https://www.openstreetmap.org/copyright) and
[Geoapify terms](https://www.geoapify.com/terms-and-conditions/) remain separate
from facility-source rights and privacy. No unsupported blanket licence is
assigned to the combined dataset. Other source reuse evidence is retained in
[source-rights verification](#source-rights-verification-2026-10-05), without
repeating already completed research.

### Verified selective-exception path

The earlier claim that the recorder already supported individual exclusions
was inaccurate. Migration 064 now adds optional
`excluded_source_record_ids` to each immutable source/artifact review scope.
The recorder rejects malformed/duplicate UUIDs, foreign or missing membership,
and active restrictions not explicitly acknowledged by an exclusion. It keeps
the complete member count/digest, denies excluded-record publication and
default visibility, and excludes their approved geometry. Category exclusions
remain available; there is no new generic field-redaction engine.

All six focused tests passed on an actually migrated disposable PostGIS
database, with no skips. They cover old documents without the optional field,
dry-run/apply/replay and unchanged original evidence, restriction handling,
geometry and discovery/read-model exclusion. Repository hygiene and Python
compilation passed. The disposable database was removed after every run;
the real candidate and retained preview were unchanged. These are synthetic
implementation proofs, separate from the real-cohort screening/count evidence
and the maintainer's final publication decision. Required remote CI must pass
on the integrated code head before activation.


**Current checkpoint:** all fifteen frozen source snapshots passed append-only
taxonomy reconciliation on the isolated copy and retained preview. The
[current measured pool](../data/manifests/v0-candidate-20261004-taxonomy-inventory.json)
contains 187,940 observations, 124,414 source-qualified groups and 50,611
private-map-served groups. [Full candidate-only staging](../data/manifests/v0-candidate-20261004-r3-staging-custom-plan.json)
has now committed successfully in isolated `uec_v0_review_r3`: all fifteen
sources, 187,940 observations and 124,414 candidate release members, with zero
default-visible members or release manifests. Earlier failed runs are retained
as history below. No public release approval
has been recorded. Source snapshots are not globally deduplicated, reviewed,
operating or publishable facility counts.

## Candidate inventory boundary

The release-candidate pool is the latest successfully imported private source
snapshot per source in the retained local `real_preview` schema. The source
inventory tool is deliberately read-only: it begins one repeatable-read,
read-only database transaction and writes only a sanitized aggregate report.
It records exact snapshot, raw-artifact, normalized-handoff, adapter, schema,
and taxonomy-crosswalk provenance; reconciliation counters; source exclusion
and quarantine aggregates; private source/provider/coarse/unmapped location
counts; and the measured release/public graph projection totals.

After the UK, Denmark, and Netherlands imports have been integrated serially,
the operator may build the row-free inventory with:

```powershell
python pipeline/scripts/diagnostics/build_release_candidate_inventory.py `
  --output data/manifests/v0-release-candidate-inventory.json
```

The command requires `UEC_DATABASE_URL` (or `--database-url`). It fails closed
if its required preview/taxonomy schema is unavailable, refuses to overwrite
an existing output, and emits only the report path's completion receipt to
stdout. Its canonical `inventory_sha256` covers the measured content but not
the read clock, so an unchanged database snapshot yields the same content
digest on repeat. Keep the report as generated aggregate evidence; never add
private rows or hand-edit its counts. An absent source snapshot is unavailable,
not a zero-row source. The report's source count means snapshot presence only;
it does not mean that every registered source is current, complete, live-ready,
reviewed, approved, or published.

The inventory itself creates no candidate release: `release_id` is null and
its release-member count is zero. The report separately measures whatever
release, membership, manifest, map, and graph rows actually exist in the
database. This diagnostic never translates a private candidate count into a
public count or an approval state. A zero projection count describes only the
listed database relations during that transaction; it does not audit deployed
copies, CDN caches, exports, or other environments.

## Reacquired measured private inventory (not publication approval)

The repeatable-read inventory at
[`v0-candidate-20261004-reacquired-inventory.json`](../data/manifests/v0-candidate-20261004-reacquired-inventory.json)
measured 15 latest imported private snapshots after the authorized three-source
reacquisition: 187,940 observations grouped
into 124,414 source-qualified candidate groups. Of those groups, 50,611 meet
the current private map-feed geometry and scope checks. These counts are not
globally deduplicated facilities or rendered marker counts; coarse points may
share a rendered marker. The inventory digest is
`4227575dda8e2841beae6501ce71ae7789b23bebb7ce3e3d850e23905449326b`.
It measured zero release rows, members, manifests, public map/discovery rows,
and graph-public rows. That is the measured database state, not a deployment,
cache, or publication audit.

| Source snapshot | Observations | Candidate groups | Recorded acquisition mode |
| --- | ---: | ---: | --- |
| `au.npi.facilities` | 8,140 | 8,140 | archived replay |
| `au.sa.epa.licensed-activities` | 43 | 41 | live acquisition; broader source rows were excluded/quarantined |
| `be.locations` | 4,032 | 1,794 | live acquisition |
| `br.sif.registered` | 36,639 | 3,143 | reacquired live; exact raw/normalized evidence retained |
| `ca.ontario.meat-plants` | 460 | 460 | archived replay |
| `dk.smiley` | 58,795 | 58,795 | verified retained-artifact replay after live retrieval |
| `es.cat.feed-sandach` | 12,117 | 4,367 | archived replay |
| `fr.dgal.section-i` | 1,449 | 1,449 | offline handoff |
| `fr.dgal.section-ii` | 1,068 | 1,067 | offline handoff |
| `fsa_approved_establishments` | 4,291 | 4,291 | live acquisition |
| `fss_approved_establishments` | 595 | 595 | live acquisition |
| `it.1069-2009` | 9,962 | 6,539 | reacquired live; exact raw/normalized evidence retained |
| `it.853-2004` | 41,849 | 25,316 | offline handoff |
| `nl.nvwa.approved-food` | 1,259 | 1,176 | live acquisition |
| `us.fsis` | 7,241 | 7,241 | offline handoff |

“Live acquisition” and “offline handoff” describe recorded run provenance,
not source completeness, currentness, legal clearance, review, or readiness to
publish. The earlier twelve-source subset was not selected: the maintainer
chose on 2026-10-04 to reacquire all three evidence-blocked sources. All three
now have checksum-verified original captures, normalized handoffs and matching
private database provenance. Their imports first passed physical/provenance
reconciliation in the isolated review copy, then ran serially against the
retained preview. Italy's initial restricted-network failures were resolved by
the network-enabled existing runner; do not describe them as an upstream outage.
Brazil's observation increase is repeated source observations, not 12,465 new
facilities; its source-qualified group count changed from 3,147 to 3,143.
Prior snapshots are preserved and disappearance is not interpreted as closure.
The [reacquired-source API receipt](../data/manifests/v0-reacquired-sources-20261004.json)
verifies authentication and source-scoped list/detail access for all three,
plus 41 South Australian, zero Brazilian and 5,297 Italian private map-feed
features. It used an owned loopback API, stopped afterward; browser rendering
was not verified and no approval is inferred.

For Denmark, the current classification separates 565 core facility candidates
from 58,230 optional candidates rather than treating every source row as an
animal-facility marker. Provider results add accepted private points for 422
candidates; 143 still carry location uncertainty. In the Netherlands, 602
candidates have accepted provider-derived points while 574 remain uncertain.
Those results remain private enrichment, not evidence of factual facility
status or permission to publish. The UK source yielded only 6 accepted
candidates and remains low-yield. Keep source labels and activity evidence in
the private source record; these aggregates alone do not support relabeling or
merging candidates.

### Earlier staging attempts (historical)

All fifteen handoff packages passed the bridge's local evidence checks.
The post-reacquisition database backup has been restored into separate
`uec_v0_review_r2`, with migration 061 applied. At that historical checkpoint,
full canonical candidate staging was not complete; local handoff validation
alone did not prove it succeeded.
The first full-cohort attempt failed closed with
`observation_idempotency_conflict`: the bridge supplied latitude/longitude in
reverse order to `ST_MakePoint`. Its transaction left zero release rows and
members. The source captures and retained preview were not altered. The bounded
coordinate-order correction is integrated; all 13 focused bridge tests passed,
including real PostGIS coordinates, late rollback and same-freeze idempotency.
The corrected full-cohort attempt then failed closed with
`preview_candidate_taxonomy_mismatch` and rolled back. The completed
[read-only database preflight](../data/manifests/v0-candidate-20261004-preflight.json)
passed eleven sources, including all three reacquired sources. France I/II,
Italy 853, and US FSIS have blank legacy candidate taxonomy columns that differ
from the normalized-record projection. Their exact frozen snapshots do have
versioned assignment sets; a guarded review-copy-only reprojection additionally
failed the existing assignment-set idempotency check and rolled back. Do not
overwrite those assignments, bypass the checks, or silently exclude the four
sources. Reconcile their taxonomy evidence and projection semantics before
another full-cohort attempt. No retained source observations, addresses,
coordinates, or history were changed by either failed transaction.

The bridge now validates every source inside the same serializable transaction
before any canonical writes and reuses verified per-source manifest hashes
instead of hashing them for every observation. All 14 focused tests passed,
including the disposable real PostGIS integration test. This is not evidence
that the blocked real cohort staged successfully.
Do not describe any canonical v0 release as staged, validated, promoted, or
public until its exact bridge run and subsequent review/activation steps are
verified. The independently verified protected database backup is
`D:\UntilEveryCage-backups\database\v0-candidate-20261004-r2\uec-frozen.dump`
(77,838,741 bytes; SHA-256
`f286f464c9a1ff2ff6cb896e67f21f74811d7773bac2fa16e05699e1b7abc6e9`).
The archive was listed (668 entries), copied with matching hashes, and restored
successfully. Earlier backups remain intact. All three reacquired source runs
are additionally checksum-verified under
`D:\UntilEveryCage-backups\v0-source-evidence\reacquired-20261004`.

## Taxonomy reconciliation checkpoint (2026-10-04 PDT / 2026-10-05 UTC)

The preceding failures are historical. A subsequent attempt to synchronize
legacy taxonomy cache columns also failed and rolled back: migration 046
correctly makes the entire candidate row append-only. The final repair does
not update those columns, disable their trigger, or rewrite prior assignments.
It appends a new interpretation version, `uec-source-crosswalk-v2`, while
keeping category taxonomy `uec-taxonomy-v1`. The strict bridge verifier now
checks the exact current assignment set's lineage, display category and ordered
payload against the frozen group, using the same newest-set ordering as the
API. Direct mapping-method provenance and the two-observation France II group
are represented correctly without erasing their earlier v1 interpretation.

All fifteen sources passed actual reconciliation on the isolated copy and then
the retained preview. The [retained receipt](../data/manifests/v0-taxonomy-reconciliation-20261004.json)
records 124,414 candidate groups and 187,940 observations. Full candidate rows,
source observations, and prior v1 assignment history were hashed before and
after and checked unchanged. Both databases had zero release rows and members
after reconciliation. The [fresh measured inventory](../data/manifests/v0-candidate-20261004-taxonomy-inventory.json)
has digest `23adeac2487ee163e78918ba53f8aa01d274e2900cc4a8bf8b26e60cbd566d21`;
the 50,611 private-map-served group count is unchanged. Do not substitute the
47,211 summed import-time map counters for current geometry availability.

The reconciled database archive is
`D:\UntilEveryCage-backups\database\v0-taxonomy-reconciled-20261004\uec-frozen.dump`
(89,657,234 bytes; SHA-256
`413d006bccd3ddcac77ae6383ef838b8abe365bb085f565e06d8c8fd110129c4`).
Its container/disk hashes match, its archive lists 653 entries, and it restored
successfully into fresh `uec_v0_review_r3`. Existing migration 061 was then
applied only to that review database. The fresh freeze selects all fifteen
sources, excludes none, and reverified every handoff; its file SHA-256 is
`de8090190cc25a22fc21e9694303248a9e1cd168f6414c09a1795dafc34aae6b`.
The earlier backup and failed-run receipts remain preserved. Successful and
failed reconciliation receipts are also checksum-verified on D: under
`v0-source-evidence\taxonomy-reconciled-20261004\review-evidence`.

All 90 affected tests passed, including actual disposable PostGIS, immutable
stale candidate rows, mismatched/missing assignments, newest-version shadow
rejection, late rollback and same-freeze replay. Independent integration review
found no remaining issue; all six [CI jobs for the code repair](https://github.com/eliperez-dev/UntilEveryCage/actions/runs/37254629562)
passed on `fa13792d1e8dbd493c032b8e7994ba4c53d47a35`. These fixture/CI
results are separate from full-cohort staging. Staging of
`v0-candidate-2026-10-04-r3` initially failed with a taxonomy contract error in
the isolated restore and rolled back to zero canonical observations, releases
and members. Its [sanitized failure receipt](../data/manifests/v0-candidate-20261004-r3-staging.json)
is retained rather than overwritten. The cause was exact repeated semantic
claims in 262 of 595 Scottish observations, hidden by group-level merging.
The bridge now coalesces only exact semantic repeats in the derived assignment
set and validates every observation before canonical writes; raw observations,
different source evidence references and the frozen handoff bytes are preserved.
The [full offline preflight](../data/manifests/v0-candidate-20261004-taxonomy-observation-preflight.json)
passed all fifteen sources, 187,940 observations and 124,414 groups, with zero
invalid observation contracts and 503 exact repeated claims coalesced. All 91
affected tests passed with actual disposable PostGIS and independent review
found no evidence-loss or validation-placement issue. A subsequent slow run was
operator-stopped, not rejected by another taxonomy contract:
its [shutdown receipt](../data/manifests/v0-candidate-20261004-r3-staging-retry.json)
records SQLSTATE `57P01`, and rollback again left zero canonical observations,
releases and members. A tiny synthetic PostgreSQL probe reproduced a generic
sequential-scan plan retained after an analyzed-empty table grew to 20,000 rows;
a fresh lookup used the index. That demonstrates the planning risk, not the
exact plan inside the stopped connection. The bridge now disables automatic
statement preparation on its own connection; no server settings, schema rules
or source data were changed. All 91 affected tests passed again with actual
PostGIS. All six [CI jobs for this connection-only safeguard](https://github.com/eliperez-dev/UntilEveryCage/actions/runs/37267704007)
passed on `c85490530a0708202ae402b7b8a02e38af4eb0e4`.

### Successful full-cohort staging (2026-10-05)

The [generated staging receipt](../data/manifests/v0-candidate-20261004-r3-staging-custom-plan.json)
records `candidate_only_staged` for the same fifteen-source freeze. Independent
SQL checks confirmed 187,940 committed canonical observations, 124,414
source-qualified candidate facilities and release members, and fifteen
represented sources. The single release has status `candidate`, profile
`official` and `test_only=false`; this identifies real retained data, not
publication approval. All members have `default_visible=false`, and no release
manifest exists. The retained `uec` preview still has zero releases and members.
The [read-only post-staging inventory](../data/manifests/v0-candidate-20261005-r3-staged-inventory.json)
independently confirms this candidate state, zero promoted releases and zero
rows in the measured public projections; unavailable relations are labeled
unavailable rather than assigned invented zero counts. Its digest is
`122c51502f639326b3c9100414e604a08103f12e263828445c587d9f690b68c6`.

Coordinate evidence in the receipt counts **observations**, not unique groups
or map markers: 64,055 source-coordinate observations, 1,030 provider-derived
observations, 2,370 verified coarse-reference observations and 120,485 unmapped
observations. These sum to 187,940. The separate retained-preview measurement
remains 50,611 currently map-served source-qualified groups. Source coordinates
are not automatically an exact-address or rooftop claim.

The bridge's canonical freeze digest is
`bce1cd69dd2f37fbee3faf5d92079324ccc85fd4fbb1fc8419672dd6d1b76bbb`;
this is distinct from the freeze file-byte SHA-256 recorded above. Neither
digest nor the candidate status grants publication permission. Full-cohort
same-freeze replay was not rerun; replay/rollback were exercised in the actual
PostGIS test suite, and the complete frozen cohort was staged once successfully.

The staged review database is backed up on D: at
`D:\UntilEveryCage-backups\database\v0-candidate-staged-20261005-r3\uec-candidate.dump`
(181,321,962 bytes; SHA-256
`74051def8732e7193e373cacd0f27c7be92b4ba3cdafbf576f9394e846781fcf`).
Container/disk hashes match and the archive lists 654 entries. This newer
staged archive was not independently restore-tested; the earlier reconciled
baseline archive was actually restored before this successful staging run.

Closeout removed only the superseded isolated `uec_v0_review_r2` copy after
checking that it had no connections and that both D: backup hashes still
matched. Its measured database size was 1,042,035,171 bytes. The retained `uec`
preview and successfully staged `uec_v0_review_r3` remain intact. Owned
container dump copies, five D-backed temporary helpers/receipts and the tiny
synthetic query-plan probe were removed; the active freeze and source captures
remain available. There are four worktrees, including the unchanged primary,
frontend and community worktrees. Database/container cleanup does not claim
that Windows has physically compacted Docker's virtual disk.

Graph import/projection, human review, and public activation
remain separate, incomplete steps; no public approval has been created.

## Dataset identity

`v0` names the first public dataset milestone and is independent of the V2
website release and the legacy V1 application. The maintainer chose the simple
public label **v0**, not the earlier proposed CalVer label. The private frozen candidate's machine ID is
`v0-candidate-2026-10-04-r3`, bound to the new inventory and exact source
artifacts. The maintainer approved that frozen candidate as the v0 scope and
authorized release preparation, verification, and bounded release-enablement
engineering on 2026-10-05. That instruction is not a record of artifact-specific
rights clearance, privacy screening, individual factual confirmation, public
promotion, or website launch. The candidate remains frozen during this work.
Do not claim
a public v0 release exists until its release workflow has actually created it.

## Human review sprint

### Source-rights verification (2026-10-05)

Current publisher pages were checked for the frozen sources below. This is
licence/reuse evidence, not an artifact-scoped rights decision or privacy
approval. Exact candidate artifact digests remain in the linked taxonomy
inventory; do not substitute a current upstream download for the frozen bytes.
Licence exceptions, source dates, attribution and no-endorsement conditions
must accompany any approved output. A missing original capture remains
`not_retained`, not retrospectively byte-verified.

| Frozen source | Primary reuse evidence and remaining conditions |
| --- | --- |
| Australia NPI | [Exact Facilities CSV resource](https://www.data.gov.au/data/dataset/npi/resource/f83cdee9-ebcb-4f24-941b-34bb2f0996cf?inner_span=True) identifies CC BY 4.0; preserve Commonwealth/NPI credit and stated exceptions. This is the CSV, not the separately licensed GeoJSON resource. |
| South Australia EPA | [Government resource metadata](https://data.gov.au/data/dataset/https-www-waterconnect-sa-gov-au-content-downloads-dewnr-topo-epa-activities-sag-shp-zip/resource/26e076f3-c37f-4089-8f28-3f7c9afd997e) records CC BY 3.0 Australia and approximate locations; publisher-side catalogue verification was unavailable in this check. |
| Belgium FASFC | [Open-data terms](https://www.foodweb.favv-afsca.be/professionelen/praktisch/opendata/) support reuse with source/latest-update credit and non-misleading presentation; account for both operator-list and activity-code evidence. |
| Brazil SIF | [MAPA resource](https://dados.agricultura.gov.br/pt_PT/dataset/servico-de-inspecao-federal-sif/resource/97277e92-264a-4dc0-9aea-f87b8ea93798) records CC Attribution; retain MAPA credit and assess excluded personal/third-party material separately. |
| Ontario meat plants | [Catalogue](https://data.ontario.ca/dataset/provincially-licensed-meat-plants) records OGL-ON-1.0; contact data and third-party material are not cleared merely by that label. |
| Denmark Find Smiley | [Download/use conditions](https://www.findsmiley.dk/om-smiley/statistik-og-data/hent-smileydata) require authority credit and prohibit logo use; displayed individual smiley status has currentness/design requirements. A dated facility snapshot is not a claim of current smiley status. |
| Catalonia feed/SANDACH | [Exact national-government catalogue entry](https://datos.gob.es/es/catalogo/a09002970-registro-de-establecimientos-del-sector-de-la-alimentacion-animal-y-del-ambito-de-los-sandach) identifies `m48e-zdz9` and links Generalitat reuse licensing. Preserve source/update-date context, no endorsement and stated exceptions; this evidence is not a recorded release rights decision. |
| France DGAL I and II | [Source lists](https://agriculture.gouv.fr/liste-des-etablissements-agrees-ce-conformement-au-reglement-ce-ndeg8532004-lists-ue-approved) and [legal notice](https://agriculture.gouv.fr/mentions-legales) require citation/integrity and distinguish non-commercial reuse from commercial/advertising reuse requiring prior request. Do not describe these snapshots as unrestricted commercial open data without an applicable basis. |
| UK FSA | [Catalogue](https://www.data.gov.uk/dataset/2c80e0ce-ee1c-4f26-ba6f-1e1ae1bd8ee9/approved-food-establishments) records OGL; preserve the frozen snapshot date, attribution and licence exceptions. |
| UK FSS | [Source portal](https://www.foodstandards.gov.scot/open-data-portal/approved-establishments-in-scotland) records OGL v3; retain Scotland-only scope, frozen edition and attribution. |
| Italy 1069 and 853 | [1069](https://www.dati.salute.gov.it/it/dataset/stabilimenti-italiani-i-sottoprodotti-di-origine-animale/) and [853](https://www.dati.salute.gov.it/it/dataset/stabilimenti-italiani-gli-alimenti-di-origine-animale/) record IODL v2.0 and identify some coordinates as OSM-derived without identifying individual rows. Preserve attribution and assess the applicable ODbL/derived-database duties; do not silently label all coordinates exclusively Ministry-origin or impose a blanket OSM ban. |
| Netherlands NVWA | [Copyright policy](https://www.nvwa.nl/service/copyright) establishes a CC0 default with item-specific exceptions and no implied endorsement; privacy/third-party rights remain separate. |
| US FSIS | [Directory](https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory) offers the CSV; [USDA rights policy](https://www.usda.gov/about-usda/policies-and-links) permits copying/distributing public-domain material, requests USDA credit and identifies exceptions. This supports a conditional reuse basis, not a blanket assumption that every embedded item is unrestricted or a requirement for fresh permission solely because the CSV lacks a licence banner. |

Provider-derived geometry is separate evidence. [Geoapify terms](https://www.geoapify.com/terms-and-conditions/)
and [geocoding documentation](https://www.geoapify.com/geocoding-api/) support
storage/reuse subject to source attribution, OSM obligations and Geoapify credit
on the free plan. Preserve datasource provenance; provider permission does not
clear the original facility data, establish an operating-site address or resolve
privacy eligibility. Mixed-source outputs must retain their distinct terms;
this review does not establish one blanket licence for the combined dataset.

The real candidate validation dry run found 124,414 missing release-scoped
publication decisions, zero duplicate members and zero validation errors. Its
zero rights requirements/"cleared" status was vacuous because all members were
non-visible; it did not check or clear any contributing artifact. Full-cohort
decision recording, geometry parity and database activation failure tests are
the bounded engineering work authorized here. No decision events or public
projections have been created for this real candidate by these checks.

Review the frozen pool as a bounded whole, with source/profile-level decisions,
representative checks, and explicit exceptions. The review does not require
manual confirmation of every facility or every geocode/graph edge. It does
require proportionate review of each source snapshot's terms and redistribution
rights, scope/coverage, privacy signals and exclusions, classification rules,
source-date limitations, location precision, and failure modes. A valid source
address is not proof of an operating facility address; an accepted geocode or
private graph edge is not project approval.

For each proposed source/profile, record which exact artifact version is in
scope, whether it can be redistributed, required attribution, excluded
categories/records, material uncertainty, and the review authority/date. Keep
source origin, factual review, privacy eligibility, project approval, and
publication as distinct decisions. Where a source has opaque or unreviewed
activity mappings, confirm the taxonomy coverage and preserve `unclassified`,
`partial`, `ambiguous`, and quarantined states instead of silently treating
them as approved scope. Record lawful/private address and coordinate
restrictions without copying their payload into public-facing review notes.

The retained candidate importer stores source snapshots in the isolated
`real_preview` schema. The row-free inventory does not transfer those rows.
`pipeline/scripts/maintenance/import-candidate.py` remains restricted to an
explicitly marked disposable loopback database and is a test-only importer.
For bounded v0 preparation, `pipeline/scripts/maintenance/bridge-v0-candidates.py`
can stage an explicitly frozen full source selection into a separate
`uec_v0_review` database as a non-visible `candidate` release. It verifies the
authenticated normalized and graph handoffs against the exact latest private
preview snapshot, preserves every source observation and source-native group,
and records source-byte retention honestly: unavailable original bytes have
no fabricated locator or size. The command requires an explicit freeze file,
inventory digest, isolated loopback database, and `--candidate-only-ack`.
It creates no approval, rights decision, public projection, release manifest,
validation, or promotion. Same-freeze reruns are idempotent; conflicting
release IDs or changed source snapshots are rejected. Do not point it at the
authoritative private pipeline database. The bridge is not the publication
workflow; source/profile review, scoped cohort decisions and specific exceptions, rights decisions,
validation, and public-map contract work remain separate activation steps.

## Existing release activation path and remaining gates

### Bounded release-enablement verification

The cohort recorder now measures the exact frozen membership and prepares an
operator review document without approving it. Its release/artifact-scoped
decisions keep factual review, privacy screening, project approval, source
rights, classification interpretation, and geometry interpretation separate.
It supports source/artifact decisions, taxonomy-category exclusions and exact
source-record UUID exclusions without editing original facts. Arbitrary
field-level redactions are not supported by this recorder. Project release
approval does not certify every government-source statement as independently
verified. The [cohort contract](architecture/release-manifest-verification.md)
documents the dry-run and explicit application commands.

On 2026-10-05, additive migrations 062 and 063 were applied only to isolated
`uec_v0_review_r3`, after rechecking the staged D: backup checksum. The recorder
prepared ignored local `data/reports/v0-candidate-20261005-r3-unapproved-review.json`
for all fifteen source/artifact scopes and 124,414 members. All approval fields
remain pending/unapproved, and method/evidence references require an actual
operator decision. No review document, rights decision, visible member, or
release manifest was inserted. Before/after row-free digests agreed for all
198,895 retained canonical source records and 187,940 observations; neither
original evidence table changed. The retained private preview was not migrated.

The shared public geometry selector carries original source precision and
allowlisted provider/method/confidence metadata; source-reported, approximate,
exact, city and unmapped display states are distinct. Invalid or insufficient
geometry must not become a guessed public point. Synthetic disposable-PostGIS
proofs and actual-cohort measurements are separate evidence: passing fixtures
does not establish that this real cohort is approved or publicly rendered.
Fifty focused local integration tests passed, including the actual disposable
PostGIS cohort and geometry proofs without skips, plus 24 frontend wire/map
projection tests. An additional actual SQL proof confirms that a validated
synthetic release has zero default-public rows, while its private preparation
query has eight eligible rows: three mapped and five unmapped, with the excluded
record absent. The initial CI run caught an optional-property type error; the
minimal fix passed Svelte check with zero errors/warnings and the 24 focused tests.
Full activation/API evidence requires all six jobs passing for the exact
integrated commit in the [Tests workflow](https://github.com/eliperez-dev/UntilEveryCage/actions/workflows/tests.yml?query=branch%3Aeli%2Fv2), not a previous run.
Do not treat this preparation checkpoint as promotion or launch. The maintainer
explicitly authorized private pre-publication tile generation and eligible
null/unmapped records on 2026-10-05; neither decision authorizes public access
to restricted evidence or changes the public promoted-release gate.

Once the reviewed candidate set is represented in canonical release membership,
use the existing release contracts rather than treating the inventory as a
manifest or adding an alternate publication mechanism:

1. Verify every selected source/artifact against current acquisition and
   redistribution terms, privacy/suppression state, source scope, and the
   authorized maintainer review. Record exact release/profile-scoped source
   rights decisions; attribution text alone is not clearance.
2. Record the operator-authored cohort decision and any specific exclusions
   against the exact release/artifact/taxonomy bindings. Preserve factual review
   status independently of project release approval; no manual confirmation of
   every government-source fact is required. Privacy-ineligible or excluded
   members stay non-visible. Otherwise eligible unmapped records may remain
   listable without claiming a map location.
3. Run the existing release validation without `--mark-validated` first; inspect
   its row-free blockers and release/profile totals. The command only marks a
   release validated when the checks pass and an operator explicitly requests
   that transition.
4. Prepare the immutable `uec-release-manifest-v2`, including exact source
   coverage, source/raw artifact hashes, included-row counts, limitations,
   current suppression generation, review/publication state, and actual
   distributed artifacts (or an explicit no-artifacts declaration).
5. Build and verify private map artifacts for the validated release, then
   promote through the checked atomic activation workflow. Independently hash
   the canonical manifest and each distributed file. Confirm actual public
   projection counts and the versioned release identifier afterward. Private
   tile preparation does not enable public API access before promotion.
6. Exercise suppression/revocation, cache/export propagation, rollback, source
   attribution and visitor/provider disclosures for the actual deployment.
   Existing documentation records remaining cross-stage activation/revocation
   limitations; a successful inventory hash or promotion command does not close
   them.

Until these actions are complete, v0 remains a candidate-review milestone,
not a public release. The separate V2 website cutover remains governed by the
product readiness roadmap and may not be inferred from the dataset milestone.

The current private map feed is not a public-source-coordinate projection:
the measured public map and discovery relations are empty, and the inventory
does not prove how a future public projection will encode source-provided
coordinates, provider-derived points, or coarse references. Before public map
activation, verify the release-scoped projection and API preserve those
distinct provenance/precision classes, honor eligibility and suppression, and
render co-located coarse geometry consistently. The production Svelte frontend
is still deferred; production packaging, production-shaped end-to-end testing,
V1/V2 route comparison, and a controlled route cutover with V1 rollback remain
unfinished. Do not treat private map-feed eligibility as completion of any of
those gates.

## Evidence and limits

The diagnostic implementation and focused contract tests are
[`build_release_candidate_inventory.py`](../pipeline/scripts/diagnostics/build_release_candidate_inventory.py)
and [`test_release_candidate_inventory.py`](../pipeline/tests/test_release_candidate_inventory.py).
The database boundary is described in the
[private import contract](architecture/database-import-contract.md),
[release-manifest verification contract](architecture/release-manifest-verification.md),
[source-rights decisions](architecture/source-rights-decisions.md), and
[known activation defects](architecture/release-activation-defects.md).
The inventory is a snapshot of measured database state, not a legal
determination, a source-completeness claim, an accuracy certification, a
privacy clearance, or an authorization to publish.

</details>
