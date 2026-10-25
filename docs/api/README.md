# API contracts

Current wire formats come from schemas, implemented routes and contract tests.
The [frontend guide](../frontend/README.md) owns presentation, not DTO shapes.

| Need | Owner |
| --- | --- |
| Location/search/facets/releases/exports and contribution routes | [V2 contract](v2-contract.md) |
| Public explorer | [public-openapi.json](public-openapi.json) |
| Location DTO | [v2-location.schema.json](v2-location.schema.json) |
| Public graph | [public-graph-contract.md](public-graph-contract.md) |
| Operator-only graph | [private-graph-contract.md](private-graph-contract.md) |
| Private preview | [real-preview-contract.md](real-preview-contract.md), [candidate schema](real-preview-candidate.schema.json) |
| Deferred wire fields | [gap ledger JSON](v2-product-convergence-gap-ledger.json): contract-scoped, not product readiness |

The retained [MVP](v2-mvp-contract.json) and
[backend freeze](v2-backend-contract-freeze.json) machine records support
compatibility tests. They are dated contract snapshots, not instructions to
remove subsequently implemented features. Current product scope is only in
[the roadmap](../PRODUCT-READINESS.md).

Update the owning schema and focused drift tests with an API change. Do not
create new sprint-specific contract copies.
