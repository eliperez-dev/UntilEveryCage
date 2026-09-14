# Private candidate handoff v1

`candidate_handoff.write_handoff` emits the importer-compatible `manifest.json`
and `normalized/records.jsonl`. Required provenance is copied from
`SourceArtifact`; rows retain private `source_values` and require an explicit
`normalized.establishment_id`, `source_id`, and `source_row`. The manifest is
always `release_state: not-created`, `publication_state: private-candidate`,
`review_state: review_required`, `privacy_gate: pending`, and
`coordinate_gate: review_required`. It never infers identities or approval.

Legacy adapters that still receive dictionaries should call
`source_artifact_from_mapping` at their source-local boundary; the shared
contract remains typed and uses `sha256` internally.

The Denmark adapter currently uses `source_record_key` rather than
`normalized.establishment_id`; it must receive a reviewed source-specific
mapping before this handoff can be used for Denmark import. No mapping is
invented by this contract.
