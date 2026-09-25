# Performance and resilience

**Owner:** engineering maintainers. **Purpose:** document measured capacity,
failure behavior, and performance contracts. These are system-level
specifications and evidence, not overall product readiness claims.

| Document | Label | Scope |
| --- | --- | --- |
| [Corpus resilience](corpus-resilience.md) | **Canonical** | Failure isolation and corpus-scale behavior. |
| [Public projection read path](v2-public-projection-read-path.md) | **Canonical** | Read-path contract. |
| [Observability](v2-observability.md) | **Canonical** | Signals, metrics, and operational visibility. |
| [API load rehearsal](v2-api-load-rehearsal.md) | **Reference** | Bounded rehearsal results and limitations. |
| [100k discovery rehearsal](v2-discovery-100k.md) | **Reference** | Synthetic discovery-scale result and limitations. |

Current product gates belong in [PRODUCT-READINESS.md](../PRODUCT-READINESS.md).
