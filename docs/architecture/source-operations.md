# Private-alpha source operations

`pipeline/source_operations.json` is the shared operational source of truth
for schedule and freshness expectations. It covers every source identity in
`pipeline/source_registry.json` without changing country adapter packages or
publication status. A `null` interval/staleness value means that cadence is
unknown; it is not permission to assume that a source is current.

## Artifact and run layout

The caller chooses a private operations root, normally an ignored directory
under `data/`. The shared layer uses this layout:

```text
<operations-root>/
  raw/sha256/<prefix>/<sha256>/<artifact-name>  # immutable bytes, stored once
  raw/observations/<observation-id>.json         # one provenance record per observation
  history/<source-id>.jsonl                      # append-only run ledger
  notifications/<source-id>.jsonl               # local notification hook output
  runs/<run-id>/                                 # adapter-owned private stages
    parsed/ normalized/ quarantined/
    manifest.json or run-manifest.json
    qa.json run-status.json source-health.json
    release-diff.json review-packet.json failure-report.json
```

Raw bytes are addressed by SHA-256 and are never overwritten. Equal bytes with
different retrieval facts receive separate observation manifests. The ledger
also preserves every failed and unchanged observation; reruns do not replace
earlier evidence. Retention is restricted research evidence subject to the
exceptional removal process in `docs/ETHICS.md`; the operational layer does not
invent an expiry or override a privacy/removal decision.

## Run classification and failure behavior

Every shared-orchestrator run records one of these classifications:

- `changed`: the artifact or normalized output differs from the prior run;
- `unchanged`: both content hashes match the prior run;
- `review-required`: the adapter or QA evidence reports quarantines/drift or
  explicitly requests review;
- `failed`: acquisition, adapter, evidence, or operations validation failed.

`release_promoted` is always `false` in these records and
`release_preserved` is always `true`. A failed or partial rerun therefore
leaves any prior eligible release reference available to the separate release
process. Missing source rows are reported as `not-observed` by the aggregate
diff; they are never interpreted as closure.

Network acquisition retries only retry bounded transport/rate-limit failures.
Terms, content-type, size-limit, malformed-input, and validation failures fail
closed. Each attempt records its category, retryability, and operator action;
the final private `failure-report.json` and optional local notification hook
contain no source rows or sensitive payloads.

## Operator review

`review-packet.json` and `release-diff.json` are deterministic, row-free
operator artifacts. They identify provenance, counts, drift/quarantine
signals, not-observed counts, prior release context, and required actions. They
do not approve, promote, or publish a release. Build the aggregate machine-
readable health index with:

```powershell
python pipeline/scripts/diagnostics/build-source-operations-health.py `
  --operations-root data/restricted/source-operations `
  --output data/reports/source-operations-health.json `
  --registry pipeline/source_registry.json `
  --as-of-utc 2026-09-15T00:00:00Z
```

The index reports `not-run`, `private-validated`, `degraded`,
`review-required`, or `failed` per source, plus freshness and run history
facts. It always sets public exposure to false and publication eligibility to
blocked. It is operational evidence, not a production-health or publication
claim.

The older compatibility registration helper may also retain its stable
`raw/<sha256>.artifact` path and `raw/registrations/*.manifest.json` events;
those paths are still content-addressed and append-only. New integrations
should use the layout above so observation metadata and raw bytes are kept as
separate objects.
