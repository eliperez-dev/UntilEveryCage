# Graph foundation data dictionary

| Object | Meaning | Important invariants |
| --- | --- | --- |
| `organizations` | Canonical organization projection | Separate from `facilities`; names are not evidence by themselves. |
| `source_entity_identifiers` | Native identifier observed in one source record | Source-qualified; exactly one facility or organization target; append-only. |
| `source_entity_crosswalks` | A reviewed or candidate mapping between two native identifiers | `identity_scope = source_scoped`; does not merge or assert universal identity. |
| `organization_relationship_observations` | Dated organization-to-facility or organization-to-organization assertion | Validity dates, observation time, source, confidence, review state, and explicit unknowns are distinct. |
| `organization_relationship_current` | Latest observation per scoped endpoint/type | Projection only; different targets remain visible for contradictions. |
| `claims` | Source-backed typed value/unknown for one facility or organization | Multiple values can coexist; unknown requires a reason. |
| `claim_support` | Link from a claim to a source record/artifact | Role is explicit: primary, corroborating, contradicting, or context. |
| `graph_public_claims` / `graph_public_relationships` | Release-scoped public projections | Promoted release + accepted review + passed privacy + released storage + no current suppression. |

Graph row state fields use four independent axes:

* `storage_state`: `raw`, `private`, `reviewed`, or `released`.
* `review_state`: factual review/decision state; it is not source origin.
* `privacy_status`: exposure screening state; it is not factual review.
* `publication_status`: release eligibility state; it is not actual publication.

`claim_domain` values `inspection`, `violation`, `commitment`,
`investigation`, `public_funding`, and `animal_count` are reserved attachment
points. This migration does not implement inspection systems, violation
adjudication, commitment tracking, investigation case management, funding
accounting, or animal-count methodology.

Source records and artifacts remain the provenance boundary. The graph layer
does not copy raw source payloads into public projections. Facility-level
privacy/suppression decisions are expected to propagate through the existing
source-record restriction references and must be checked again on every public
query.
