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
