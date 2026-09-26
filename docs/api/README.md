# API contracts

**Owner:** backend maintainers. **Purpose:** route interface contracts. The
public V1 migration boundary remains documented in
[`../frontend/v1-behavioral-contract.md`](../frontend/v1-behavioral-contract.md).

| Contract | Label | Boundary |
| --- | --- | --- |
| [V2 contract index](v2-contract.md) | **Canonical** | Stable V2 API contracts and linked schemas. |
| [Public graph contract](public-graph-contract.md) | **Canonical** | Release-scoped public graph projection. |
| [Private graph contract](private-graph-contract.md) | **Canonical** | Operator-only graph analysis. |
| [Real preview contract](real-preview-contract.md) and [candidate DTO schema](real-preview-candidate.schema.json) | **Canonical** | Local/private preview API and import behavior. |
| [MVP API contract](v2-mvp-contract.md) | **Reference** | Earlier MVP interface baseline; current supported DTOs are described by the active contracts. |
| [Backend contract freeze](v2-backend-contract-freeze.md) | **Reference** | Accepted architecture constraints for implementation. |

Do not create sprint contract snapshots or duplicate API specs. Update the
relevant contract and its source schema together.
