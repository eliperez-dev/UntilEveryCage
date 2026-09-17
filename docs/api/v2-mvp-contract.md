# V2 MVP backend/API contract freeze

Contract ID: `uec-v2-mvp-backend-contract-1`  
Status: frozen for Sprint 1 review  
Reviewed: 2026-09-16

The machine-readable freeze is
[v2-mvp-contract.json](v2-mvp-contract.json). It freezes the backend surface
that the functional MVP frontend may consume. It does not claim that V2 is
production-deployed or that every source is current.

## Frozen public surface

| Surface | Contract |
| --- | --- |
| Health | `/health/live`, `/health/ready`, and coarse privacy-safe `/health/diagnostics` |
| Discovery | `/api/v2/locations`, `/api/v2/locations/{facility_id}`, `/api/v2/discovery/filters`, and `/api/v2/discovery/facets` |
| Export | Bounded `/api/v2/locations.csv`; reproducible release packages remain an operator CLI concern |
| Release metadata | `/api/v2/releases/manifest` exposes only an eligible promoted manifest |
| Development preview | `/api/dev/preview/candidates` is authenticated, private, test-only, and unavailable as a production surface |

The existing [v2-contract.json](v2-contract.json) remains the endpoint
source contract. The public location object is frozen by
[v2-location.schema.json](v2-location.schema.json). The consistency test
ensures these surfaces do not drift silently.

## Frozen behavior

- Public reads select one promoted, non-test release inside the requested
  profile and use one read-only snapshot for release metadata and rows.
- The default profile is `official`; `secondary` and `community` require
  explicit selection. A profile mismatch cannot relabel a release.
- A record must pass the applicable publication, privacy, and release gates.
  Current suppression applies even to older releases, filtered requests,
  exports, history, reimports, and restores.
- Exact, city/coarse, and unmapped locations remain distinct. A geocode is
  evidence about location, not publication permission.
- Cursor and offset cannot be combined. Bbox and radius cannot be combined.
  Pagination is deterministic and bounded.
- Errors use `{ "api_version": "v2", "error": { "code": "...", "message": "..." } }`.
- Public responses contain the reviewed projection only. Raw fields, private
  addresses, source-record payloads, geocoder queries/responses, reviewer
  identities, and restriction reasons are not part of this contract.
- Community-unreviewed data, when eligible, is only available through an
  explicit community profile and carries the persistent warning that it has
  not been verified by Until Every Cage.

## Deliberate non-goals

This freeze does not include an administrative review UI, public ingestion,
the public accountability graph, the narrative frontend, device-geolocation
requirements, an unbounded bulk API, or deployed production authorization.
These are separate MVP or post-MVP work items, not implied by the endpoint
names.

## Change policy

Additive fields or endpoints require updated contract/schema tests and clear
public-safety review. A breaking response or behavior change requires a new
contract ID and an explicit migration path. Documentation alone cannot mark a
claim implemented; the claim-evidence matrix must point to code and test or
rehearsal evidence.

See the [claim-evidence matrix](../governance/v2-mvp-claim-evidence.md) for
what this frozen surface does and does not substantiate.
