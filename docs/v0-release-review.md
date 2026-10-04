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

At this preparation checkpoint, do not copy old retained-preview totals into a
new frozen inventory or present pre-integration counts as the final v0 pool.
Root integration must first finish the source imports and verify the protected
database backup. Then record the generated inventory digest and the independently
verified backup digest/byte size with that frozen evidence. Those values are
not supplied by this document and must not be inferred from earlier snapshots.

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

The current retained candidate importer stores source snapshots in the
isolated `real_preview` schema. Those rows are not `uec.observations`, do not
belong to `uec.release_members`, and cannot be promoted by the public release
commands. `pipeline/scripts/maintenance/import-candidate.py` is restricted to
an explicitly marked disposable loopback database and is a test-only bridge;
it is not authorized for the retained candidate database or a full release.
The reviewed-demonstration path is a small explicitly selected subset, not a
full-pool importer. Before v0 can advance, maintainers must use an already
approved canonical source importer or explicitly authorize and verify a
bounded, idempotent transfer from reviewed source snapshots into the canonical
`uec` release data model. No such transfer is performed by the inventory.

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
