# Architecture references

Read only the contract relevant to the task. Product scope and sequencing belong
to [PRODUCT-READINESS.md](../PRODUCT-READINESS.md).

| Need | Owner |
| --- | --- |
| Registry, descriptors and adapter organization | [Country source platform](country-source-platform.md) |
| Acquisition, facility/evidence kinds and normalized handoff | [Source lifecycle](source-lifecycle.md) |
| Refresh history, artifacts, retries and health | [Source operations](source-operations.md) |
| Graph entities and fields | [Graph dictionary](graph-data-dictionary.md) |
| Location and precision semantics | [API location contract](api-location-contract.md) |
| Private import | [Database import](database-import-contract.md), [disposable importer](disposable-candidate-import.md) |
| Activation transaction and recovery | [Release activation](release-activation-defects.md) |
| Artifact integrity | [Manifest verification](release-manifest-verification.md) |
| Recorded rights/licence decisions | [Source rights](source-rights-decisions.md) |
| Migration reference | [V1/V2 reconciliation](v1-v2-reconciliation.md) |
| Architecture rationale, not a new implementation plan | [Graph ADR](adr-graph-foundation.md), [map ADR](adr-map-visualization-platform.md) |
| Wire shapes | [API index](../api/README.md) |

Source identities live in [the machine registry](../../pipeline/source_registry.json);
source readiness lives only in [source-status.json](../source-status.json).
Source research and mappings are indexed under [countries](../countries/README.md).
