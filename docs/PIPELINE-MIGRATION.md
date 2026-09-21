# Shared source lifecycle migration

Source packages retain ownership of parsing, classification, source-native
fields, and quarantine reasons. Shared code owns acquisition evidence,
content-addressed storage, typed `SourceArtifact` construction, private run
status, manifests, health, row-free deltas, and candidate handoff.

Migrated routes include France DGAL Sections I/II and Canada Ontario/CFIA.
Their refresh entry points accept either a bounded fetch or a preserved local
artifact and pass metadata through `source_artifact_from_acquisition`; no
source rows or raw artifacts belong in Git. UK FSA/FSS remains the next
consolidation target because its monthly drift and handoff rules are more
specialized. Italy remains source-specific until its catalog evidence and
terms are authorized.

The private lifecycle always leaves `release_state=not-created`, keeps public
surfaces disabled, and treats disappearance as `not-observed`, never closure.
Failures preserve the previous validated release and emit a restricted
failure report. Acquisition terms approval and publication approval remain
separate human gates.

## Migration runner contract

`pipeline/scripts/maintenance/apply-migrations.py` discovers every `*.sql` file
in the migration directory and sorts the paths lexically. The migration identity
stored in `uec.schema_migrations.version` is the complete filename stem, not the
numeric prefix. Consequently, `020_release_manifests.sql` and
`020_suppression_aware_v2_history.sql` have distinct identities and are both
applied in that lexical order. Migration files must not be renamed, edited,
deleted, squashed, or resequenced after they have been applied; a new change
gets a new filename.

The runner records the SHA-256 digest of each migration and refuses to execute
an already-recorded identity when its file content has changed. Database setup
and each migration run in separate transactions. A failed migration rolls back
its SQL and ledger insert, while earlier successful migrations remain recorded
so a subsequent run can retry and resume at the failed identity.

The database connection is retried up to ten times after an operational
connection error, waiting one second between attempts. Connection retries do
not alter migration ordering or checksum behavior. These rules are tested by
`pipeline/tests/test_apply_migrations.py` without connecting to a database.
