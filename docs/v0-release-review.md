# v0 dataset release review

**Owner:** project maintainers. **Purpose:** guide the bounded human review and
freeze of the first public dataset version. This document is not release
approval, a publication record, or evidence that candidate intake has closed.
The controlling roadmap is [PRODUCT-READINESS.md](PRODUCT-READINESS.md); the
governing requirements are [ETHICS.md](ETHICS.md).

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

## Final measured private inventory (not the final source selection)

The repeatable-read inventory at
[`v0-candidate-20261004-inventory.json`](../data/manifests/v0-candidate-20261004-inventory.json)
measured 15 latest imported private snapshots: 175,473 observations grouped
into 124,417 source-qualified candidate groups. Of those groups, 50,610 meet
the current private map-feed geometry and scope checks. These counts are not
globally deduplicated facilities or rendered marker counts; coarse points may
share a rendered marker. The inventory digest is
`6f73244963ab11fbc78883e1e6e41661b1d2f64b5ce7b3fa3948d18f355daf3c`.
It measured zero release rows, members, manifests, public map/discovery rows,
and graph-public rows. That is the measured database state, not a deployment,
cache, or publication audit.

| Source snapshot | Observations | Candidate groups | Recorded acquisition mode |
| --- | ---: | ---: | --- |
| `au.npi.facilities` | 8,140 | 8,140 | archived replay |
| `au.sa.epa.licensed-activities` | 43 | 41 | live acquisition; broader source rows were excluded/quarantined |
| `be.locations` | 4,032 | 1,794 | live acquisition |
| `br.sif.registered` | 24,174 | 3,147 | live acquisition; exact retrieval evidence still needs resolution |
| `ca.ontario.meat-plants` | 460 | 460 | archived replay |
| `dk.smiley` | 58,795 | 58,795 | verified retained-artifact replay after live retrieval |
| `es.cat.feed-sandach` | 12,117 | 4,367 | archived replay |
| `fr.dgal.section-i` | 1,449 | 1,449 | offline handoff |
| `fr.dgal.section-ii` | 1,068 | 1,067 | offline handoff |
| `fsa_approved_establishments` | 4,291 | 4,291 | live acquisition |
| `fss_approved_establishments` | 595 | 595 | live acquisition |
| `it.1069-2009` | 9,960 | 6,538 | live acquisition; exact supporting evidence still needed |
| `it.853-2004` | 41,849 | 25,316 | offline handoff |
| `nl.nvwa.approved-food` | 1,259 | 1,176 | live acquisition |
| `us.fsis` | 7,241 | 7,241 | offline handoff |

“Live acquisition” and “offline handoff” describe recorded run provenance,
not source completeness, currentness, legal clearance, review, or readiness to
publish. The provisional 12-source review subset currently totals 141,296
observations and 114,691 source-qualified candidate groups; 45,273 groups meet
the same current private map-feed geometry and scope checks. It is not a final
selection. `au.sa.epa.licensed-activities`, `it.1069-2009`, and
`br.sif.registered` remain deferred pending the exact evidence gaps above. The
maintainer must choose whether to defer them or reacquire/resolve their
evidence; do not silently substitute this provisional subset for that choice.

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

All twelve provisional handoff packages passed the bridge's evidence checks.
Their freeze metadata is prepared locally; final source selection awaits the
maintainer's choice to defer or reacquire the three evidence-blocked sources.
The database backup has been restored into separate `uec_v0_review`, with
migration 061 applied, but canonical candidate staging has not yet run.
Do not describe any canonical v0 release as staged, validated,
promoted, or public until its exact bridge run and subsequent review/activation
steps are verified. The independently verified protected database backup is
`D:\UntilEveryCage-backups\database\v0-candidate-20261004\uec-frozen.dump`
(71,598,797 bytes; SHA-256
`31f1dabb319b279bd796901825320610fa37cd357eff0c07de4d2d7864e79b9d`).

## Dataset identity

`v0` names the first public dataset milestone and is independent of the V2
website release and the legacy V1 application. The current naming recommendation
is CalVer `2026.10.1-rc.1`; this is pending maintainer choice and is not a
machine release identifier. Before freezing, maintainers must choose a stable
machine `release_id`, profile, ruleset/version labels, and whether a candidate
release should use a separate pre-release version. Bind those choices to the
frozen inventory digest and exact source artifact digests. Do not claim a v0
release exists until the canonical release workflow has actually created it.

## Human review sprint

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
workflow; source/profile review, per-record review outcomes, rights decisions,
validation, and public-map contract work remain separate activation steps.

## Existing release activation path and remaining gates

Once the reviewed candidate set is represented in canonical release membership,
use the existing release contracts rather than treating the inventory as a
manifest or adding an alternate publication mechanism:

1. Verify every selected source/artifact against current acquisition and
   redistribution terms, privacy/suppression state, source scope, and the
   authorized maintainer review. Record exact release/profile-scoped source
   rights decisions; attribution text alone is not clearance.
2. Ensure every selected canonical observation has a current, release-scoped
   project review outcome that passes the applicable factual, privacy, and
   publication gates. Quarantined, restricted, unresolved, or excluded evidence
   remains out of release membership unless a documented review resolves it.
3. Run the existing release validation without `--mark-validated` first; inspect
   its row-free blockers and release/profile totals. The command only marks a
   release validated when the checks pass and an operator explicitly requests
   that transition.
4. Prepare the immutable `uec-release-manifest-v2`, including exact source
   coverage, source/raw artifact hashes, included-row counts, limitations,
   current suppression generation, review/publication state, and actual
   distributed artifacts (or an explicit no-artifacts declaration).
5. Promote through the existing checked workflow, build and verify the public
   discovery/map artifacts, and independently hash the canonical manifest and
   each distributed file. Confirm the actual public projection counts and
   versioned release identifier after these steps.
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
