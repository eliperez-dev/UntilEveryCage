# Shared country-source lifecycle

The V2 source boundary is intentionally private and staged:

```text
acquire -> preserve -> parse -> normalize -> validate -> health
       -> candidate import -> guarded test-only API
```

Acquisition records the official URL, retrieval time, byte size, SHA-256, any
publisher date, and code/configuration versions. Preservation writes the raw
artifact before interpretation. The adapter then keeps parsed, normalized, and
quarantined records separate and writes a private manifest with reconciled
counts. Validation may identify anomalies but never silently drops records or
turns source disappearance into closure.

The reusable Python seam is `pipeline.contracts.source_lifecycle` plus
`pipeline.common.orchestrator.run_private_lifecycle`. `SourceArtifact` is the
typed handoff from preservation to an adapter. The runner emits row-free
`qa.json`, restricted `run-status.json`, and, when the retrieval timestamp is
available, deterministic `source-health.json`. Health means only that the
private evidence passed its contract; it does not mean current, complete,
accurate, approved, or publishable data.

Database candidate import and the guarded test-only API remain explicit
commands. They must receive a private candidate and preserve privacy and
publication gates; neither is called by the lifecycle runner. A failed or
restricted run therefore leaves any previous eligible release untouched.

Country-specific code belongs under `pipeline/sources/<country>/`. Historical
entry points may remain as thin compatibility shims, but new stages should be
implemented only in the source-owned package. Use the
[`country-source adapter template`](../../pipeline/contracts/SOURCE-ADAPTER-TEMPLATE.md)
for new packages.
