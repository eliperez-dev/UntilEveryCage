# Database import contract

The importer is the boundary between file-based pipeline stages and PostgreSQL/PostGIS. It accepts only a complete, validated staging run; it does not fetch sources, classify records, geocode addresses, or silently repair data.

## Non-destructive data rule

Governed by [ETHICS.md](../ETHICS.md), especially sections 2, 6, 8, and 9. Ordinary imports and enrichment jobs append evidence rather than overwriting it. Later snapshots and corrected interpretations create linked versions/events. Exceptional restriction, redaction, or deletion is a separate authorized maintainer workflow, not an importer cleanup feature. Public release filtering cannot replace required removal from retained storage.

The migration enforces this for evidence tables with database triggers that reject `UPDATE` and `DELETE`. In particular, `geocode_results` is an attempt history: repeated queries are permitted and each attempt records its own timestamp, response, status, and retryability. Current values for application queries must be derived through views or release membership, never by mutating historical evidence.

Geocoding scheduling follows the same rule. `geocode_jobs` provides a stable job identity, while `geocode_job_events` records queued, started, accepted, review-required, unresolved, failed, and cancelled events. Workers append events; they do not update a job status. `geocode_job_current` is a read-only convenience view for the latest event and is not an evidence store.

**Implementation gap:** Existing append-only triggers protect ordinary processing; they do not establish a compliant exceptional-removal mechanism. A narrowly authorized, audited removal path and its tests are outstanding in the [policy checklist](../governance/policy-implementation-todo.md). Do not broadly disable triggers or claim deletion/suppression support from this document alone. Imports, geocoding, release generation, and restores must honor active restrictions; removal audit events must not reproduce protected payloads.

## Required inputs

- archived raw artifact metadata with source URL, retrieval timestamp, byte size, and SHA-256;
- parsed JSONL output whose records reference the raw artifact hash;
- normalized JSONL output preserving `source_fields`;
- classified JSONL output with a ruleset ID, rule ID, category, review status, and visibility policy;
- validation report with expected and actual row counts;
- geocode results, when available, with provider, query, timestamp, response, and acceptance state.

The importer must reject a run when the input hashes do not agree, required stages are missing, the validation report has errors, or the source artifact is not valid XML. A review-required classification or unresolved geocode is not an import failure; it is imported with its review state intact.

## Transaction boundary

One source run is imported inside one database transaction:

```text
begin
  register source and acquisition run
  upsert raw artifact and run/artifact link
  insert source records (idempotently)
  resolve or create facilities
  insert identity decisions and source links
  insert append-only observations
  insert geocode results and validation findings
  create candidate release
commit
```

Any unexpected error rolls back the transaction. The previous validated release remains available.

## Idempotency

The importer may be rerun with the same staging directory. It must not create duplicate source records, facilities, observations, geocode results, or release members. Database uniqueness constraints and deterministic keys are the final safety layer; application checks alone are insufficient.

## Identity policy for the first Denmark import

Use `source_id=dk.smiley` plus `source_record_key=ID_nummer` as the source identity. Create a durable facility for each first-seen source record. Do not merge records solely because names or addresses look similar. Identity merges and splits become explicit decisions in later review work.

## Release policy

The first imported dataset creates a `candidate` release named from the source run and ruleset. It can become `validated` only after the validation report and review summary are accepted. Release membership selects the observation and carries the default visibility flag; acquisition success alone never promotes a release.

Publication additionally requires ETHICS.md privacy and source-status checks. A default visibility flag is not authorization to expose restricted records through another endpoint. Historical release membership is subject to current restrictions, including removal of residential addresses and precise coordinates where required. Unimplemented policy gates must be recorded as blockers for affected publication.
