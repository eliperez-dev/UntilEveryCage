# V2 product-convergence gap ledger

Contract freeze: `uec-v2-mvp-backend-contract-1` (reviewed 2026-09-20).
The machine-readable ledger is
[v2-product-convergence-gap-ledger.json](v2-product-convergence-gap-ledger.json).

This ledger records what the current V2 API does not promise. A field is not
added to a DTO merely because the governing policy would eventually benefit
from it. Until the relevant evidence, privacy, and publication behavior exists,
clients must preserve the explicit limitation.

| ID | Deferred capability | Current contract truth |
| --- | --- | --- |
| `GAP-EVIDENCE-INTEGRITY` | Evidence record IDs, content hashes, byte sizes, and public evidence references | The wire has source identifiers, URL, and retrieval timestamp; raw evidence is not public. |
| `GAP-SOURCE-DATES-AVAILABILITY` | Source publication/effective dates and source-availability semantics | Observation timestamps are project observations. Disappearance is not closure, and source availability is not represented. |
| `GAP-GEOCODER-METADATA` | Geocoder provider, query, timestamp, precision, result, and review status | Eligible coordinates and display precision may be returned without geocoder metadata. A coordinate is not publication permission. |
| `GAP-REVIEW-EVENTS` | Review event IDs, actor scope, dates, outcomes, and evidence references | `factual_review_status` and `reviewer_role` are summary fields, not an event history or proof of acceptance. |
| `GAP-APPROVAL-METADATA` | Richer release/profile-scoped approval and publication event metadata | `project_approval`, release, and ruleset provide current summary context only; they do not expose approval authority, basis, dates, or revocation events. |
| `GAP-FRONTEND-REVOCATION` | Durable frontend cache, invalidation, revocation, and push-update signals | The frontend uses request-level `cache: no-store`. V2 promises no durable cache or invalidation/revocation signal. Current suppression is authoritative when each request is evaluated. |

The frozen surface does include profile-scoped promoted release selection,
release/ruleset metadata, current suppression, deterministic cursor pagination,
compatibility `offset`, bounded bbox/radius filters, facets, CSV, and a
manifest endpoint. Those features must not be described as supplying any of
the deferred evidence or review detail above.

When a gap is closed, update the machine-readable contract, schema, Rust
serialization, static validator, Svelte wire schema, and focused drift tests in
one review. Until then, the gap remains a launch limitation rather than an
implicit frontend TODO or a user-visible claim.
