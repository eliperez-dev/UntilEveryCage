# Release manifest verification

Promotion stores an immutable machine-readable manifest with the release ID, profile, ruleset version, source coverage, database creation time, and an inventory of declared distributed files. Supply each file with a repeated `--artifact <path>` option; promotion hashes the file bytes and records its basename, size, and SHA-256. If there really are no distributed files, the operator must explicitly pass `--no-distributed-artifacts`. `--manifest <path>` exports the canonical JSON whose SHA-256 is stored in `uec.release_manifests`; the CLI result printed to stdout is a separate operation receipt. Obtain the manifest from a trusted project channel, verify its SHA-256 against the stored digest, then hash each listed artifact locally.

The workflow does not discover distributed files or prove that the operator supplied a complete inventory. An empty declared inventory is not evidence that no files were distributed. The manifest records the ruleset version, but other configuration and code versions are not yet part of the release schema; the source ID list is not complete record-level provenance. Hashing at promotion does not freeze later distribution bytes. The database promotion and writing `--manifest` to disk are separate operations; if the file write fails, the database manifest remains stored and an operator must recover and verify it before distribution. These limits require operational review before making a full release-integrity claim.

Migration 022 binds publication review events to releases. After importing the candidate, use the actual `release_id` recorded in `uec.releases` and `uec.release_members` when an authorized maintainer records a reviewed decision. For example, a maintainer can parameterize the following SQL with a source record ID from the candidate and the candidate's real release ID; the values and decision must be chosen by that maintainer:

```sql
SELECT release_id, status FROM uec.releases
WHERE release_id = :candidate_release_id AND status = 'candidate';

SELECT DISTINCT observation.source_record_id
FROM uec.release_members member
JOIN uec.observations observation ON observation.observation_id = member.observation_id
WHERE member.release_id = :candidate_release_id;
```

```sql
INSERT INTO uec.publication_review_events
    (source_record_id, release_id, factual_review_status,
     privacy_screening_status, maintainer_approval, publication_eligible,
     reviewer_role, note)
VALUES (:reviewed_source_record_id, :candidate_release_id,
        :reviewed_factual_status, :reviewed_privacy_status,
        :maintainer_decision, :reviewed_publication_eligibility,
        :authorized_reviewer_role, :review_note);
```

First verify the source record belongs to that candidate through `uec.observations` and `uec.release_members`. Validation reports `publication_not_approved` until the current review event for each record is scoped to that release and passes its gates; `--mark-validated` only changes a passing candidate's status. Historic source-only decisions spanning multiple releases remain withheld and need a new human release-scoped event. Validation and promotion never create approval events.

Checksums detect alteration relative to a trusted reference; they do not prove factual accuracy, privacy eligibility, or government-source correctness. Withdrawn or sanitized artifacts must remain marked and must not be silently replaced. Signing is not claimed until key custody, distribution, rotation, revocation, and compromised-release handling are separately reviewed and tested.
