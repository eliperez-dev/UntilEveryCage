# Architecture documentation

**Owner:** engineering maintainers. **Purpose:** route cross-source platform
decisions and contracts. Product scope and launch sequencing belong to
[`../PRODUCT-READINESS.md`](../PRODUCT-READINESS.md).

| Document | Label | Use |
| --- | --- | --- |
| [Country source platform](country-source-platform.md) | **Canonical** | Shared source registry and country-platform model. |
| [Source lifecycle](source-lifecycle.md) | **Canonical** | Acquisition through validation, review, and release lifecycle. |
| [Source operations](source-operations.md) | **Canonical** | Refresh and operational responsibilities. |
| [Source registry](source-registry.md) | **Reference** | Registry orientation; machine registry remains authoritative. |
| [Graph data dictionary](graph-data-dictionary.md) | **Canonical** | Graph entities and fields. |
| [API location contract](api-location-contract.md) | **Canonical** | Location and precision semantics. |
| [Database import contract](database-import-contract.md) | **Canonical** | Private import boundary. |
| [Release manifest verification](release-manifest-verification.md) | **Canonical** | Release integrity requirements. |
| [Source rights decisions](source-rights-decisions.md) | **Canonical** | Recorded rights and access decisions. |
| [Identity review](d4-identity-review.md) | **Canonical** | Identity-candidate review measures; synthetic controls remain distinct from adjudicated accuracy. |
| [V1–V2 reconciliation](v1-v2-reconciliation.md) | **Reference** | Migration and coexistence model. |
| [API contracts](../api/v2-contract.md) | **Canonical** | Public and private API contract index; related contracts are linked there. |
| [Architecture decision records](adr-graph-foundation.md), [map platform](adr-map-visualization-platform.md) | **Reference** | Accepted cross-cutting architecture rationale. |

Source- and country-specific facts belong in the
[source index](../sources/README.md). Do not create separate plans or repeat
product completion state here.
