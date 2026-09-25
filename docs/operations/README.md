# Operations documentation

**Owner:** engineering and operations maintainers. **Purpose:** route practical
runbooks and operational contracts. Product-wide release readiness is owned by
[`../PRODUCT-READINESS.md`](../PRODUCT-READINESS.md).

| Area | Documents | Label |
| --- | --- | --- |
| Local development and testing | [development.md](../development.md), [pipeline/README.md](../../pipeline/README.md), [pipeline onboarding](../../pipeline/ONBOARDING.md) | **Canonical** |
| Deployment | [development preview](../deployment/dev-preview.md), [private environment](../deployment/private-environment.md), [production operations](../deployment/production-operations.md) | **Canonical** runbooks |
| Refresh and import | [source operations](../architecture/source-operations.md), [pipeline contracts](../../pipeline/contracts/README.md) | **Canonical** |
| Geocoding | [operator](../geocoding-operator.md), [worker](../geocoding-worker.md) | **Canonical** |
| Performance and recovery | [performance index](../performance/README.md), [E2E backup/restore](../../pipeline/tests/e2e/BACKUP-RESTORE.md) | **Canonical** |
| Credential guidance | [Geocodio credentials](../security/geocodio-credentials.md) | **Reference**; never store credentials here |

Operational evidence should be placed in generated reports/manifests and
summarized in its canonical runbook or readiness authority. Temporary run logs,
handoffs, and dated status Markdown are not durable documentation.
