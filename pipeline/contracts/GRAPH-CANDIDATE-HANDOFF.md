# Private graph candidate handoff v1

`graph_candidate_handoff.py` defines the smallest adapter-to-graph boundary.
Each candidate contains a source-qualified record key, preserved `source_values`,
source-native identifiers for facilities and organizations, local references for
relationships, optional claims with at least one supporting artifact/record,
and optional source-scoped crosswalks.

The handoff is always `storage_state: private`, `privacy_status: pending`,
`review_state: review_required`, `publication_status: not_eligible`, and
`release_id: null`. It is not a database import, identity decision, review, or
publication authorization. Adapters must not add `canonical_id`, `global_id`,
or any other universal-identity assertion. Unknown relationships and claims
must carry an explicit reason. The `inspection`, `violation`, `commitment`,
`investigation`, `public_funding`, and `animal_count` claim domains are reserved
attachment points; domain-specific schemas and workflows are intentionally
deferred.
