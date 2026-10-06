# Release manifest verification

Promotion stores an immutable machine-readable `uec-release-manifest-v2` with the release/profile IDs, ruleset and projection schema versions, generated/retrieved timestamps, current suppression generation, source coverage, eligible row counts, independent review/publication state, limitations, supersession, and an inventory of declared distributed files. Supply each file with a repeated `--artifact <path>` option; promotion hashes the file bytes and records its basename, size, and SHA-256. If there really are no distributed files, the operator must explicitly pass `--no-distributed-artifacts`. Map releases additionally stage private XYZ MVT tiles with `pipeline/scripts/maintenance/build_public_map_artifacts.py` and pass the resulting `map-artifact.json` using `--map-artifact-manifest`. Promotion checks release/profile identity, the unchanged suppression generation, and each tile hash before placing the versioned object under `manifest.map_artifact`. `--manifest <path>` exports the canonical JSON whose SHA-256 is stored in `uec.release_manifests`; the CLI result printed to stdout is a separate operation receipt. Obtain the manifest from a trusted project channel, verify its SHA-256 against the stored digest, then hash each listed artifact locally.

The workflow does not discover distributed files or prove that the operator supplied a complete inventory. An empty declared inventory is not evidence that no files were distributed. `source_coverage` is aggregate coverage metadata; record-level provenance remains in the public projection rows. A release must have an exact `cleared` entry in `uec.source_rights_decisions` for every source artifact contributing visible output. Coverage can still report `attribution_required` when source metadata carries an attribution obligation; attribution is not the rights decision. The bulk packager refuses missing, unknown, restricted, out-of-scope, or ambiguous decisions. Hashing at promotion does not freeze later distribution bytes. The database promotion and writing `--manifest` to disk are separate operations; if the file write fails, the database manifest remains stored and an operator must recover and verify it before distribution. These limits require operational review before making a full release-integrity claim.

Migration 062 adds a bounded, whole-cohort review path for an isolated frozen candidate. Prepare a local template from the exact candidate and measured membership; it includes the member count/digest and one scope per contributing source artifact, not a hand-authored source-record list:

```powershell
python pipeline/scripts/stages/record-release-cohort-review.py `
  --prepare <candidate-release-id> --expected-database <uec_v0_review_database> `
  --output data/reports/release-cohort-review.json
```

The output must stay in ignored local storage. Preparation is serializable and read-only for the database. It leaves factual review `unreviewed`, privacy `pending`, publication ineligible, rights `unknown`, and classification/geometry interpretation unreviewed; method/evidence references and reviewer attribution are empty. A maintainer must author every decision and provide explicit method and evidence references before the document passes validation. The file allowlist rejects extra fields so source rows, addresses, coordinates, credentials, and free-form payloads cannot be embedded.

Run a row-free dry-run first. The command compares the document's release/profile/ruleset, freeze and inventory hashes, exact member count/digest, artifact digests, taxonomy/crosswalk versions, suppression state, and complete source/artifact coverage. The member digest is deterministic over ordered release/facility/observation/source-record/artifact bindings and the complete current taxonomy assignment payload. Apply is explicit and atomic:

```powershell
python pipeline/scripts/stages/record-release-cohort-review.py `
  --review data/reports/release-cohort-review.json `
  --expected-database <uec_v0_review_database>

python pipeline/scripts/stages/record-release-cohort-review.py `
  --review data/reports/release-cohort-review.json `
  --expected-database <uec_v0_review_database> --apply
```

Apply appends `uec.release_cohort_review_documents` and source/artifact scope rows, release-scoped publication events, and matching append-only rights decisions. It may update only candidate `release_members.default_visible` and the release control summary. It refuses active suppression, stale/conflicting timestamps, incomplete coverage, mismatched hashes, a non-candidate/test-only release, and changed membership. Exact replay of the same document is idempotent; a changed document cannot silently replace it. Excluded taxonomy display categories remain non-visible and are identified by a policy reason/reference. The geometry worker should join `uec.release_cohort_review_current` through the member's observation/source/artifact binding and the latest matching versioned taxonomy assignment, using `pipeline.common.release_cohort_review.APPROVED_GEOMETRY_MEMBERS_CTE` for set-based selection.

The recorded statuses are attributable operator decisions, not proof that a factual review, privacy check, legal determination, or geometry assessment actually occurred. Each is kept separate and requires its own explicit method/evidence reference. Factually unreviewed status is preserved; it does not imply privacy eligibility or project approval. Existing smaller release workflows can still use migration 022's release-scoped publication events. Validation reports `publication_not_approved` until the current event for each record is scoped to that release and passes its gates; validation and promotion never create approval events.

Checksums detect alteration relative to a trusted reference; they do not prove factual accuracy, privacy eligibility, or government-source correctness. Withdrawn or sanitized artifacts must remain marked and must not be silently replaced. Signing is not claimed until key custody, distribution, rotation, revocation, and compromised-release handling are separately reviewed and tested.
