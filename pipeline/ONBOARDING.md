# Pipeline contributor onboarding

Read [AGENTS.md](../AGENTS.md), [ETHICS.md](../docs/ETHICS.md),
[VISION.md](../docs/VISION.md) and [the hub](../docs/README.md), then the assigned
source entry in [source-status.json](../docs/source-status.json).
This is the source-worker workflow, not a separate readiness tracker.

## One source, one pattern

1. Identify the exact source ID, country scope and coverage gap. Compare with
   existing/V1 sources before calling a repeat refresh new country coverage.
2. Read that country's research, source-owned README and
   [adapter template](contracts/SOURCE-ADAPTER-TEMPLATE.md).
   Source identities/descriptors live in [the registry](source_registry.json).
3. Keep acquisition bounded: expected URL/schema/content, byte/time/retry limits,
   permitted access/terms and pinned parser dependencies. Preserve raw bytes,
   retrieval/source dates, checksums and code/config versions.
4. Parse, normalize, clean and quarantine deterministically. Preserve original
   fields, aliases, classifications, address/coordinate evidence and provenance
   in permitted private storage. Display simplification is not adapter data loss.
5. Register the adapter with the existing shared runner. Import observations
   before the separate queued location-enrichment task; reuse the queue/providers.
6. Verify importer idempotency, source/query counts, list/detail and actual
   map-feed membership. Missing coordinates are not invented.
7. Update only the owning source inventory entry and its existing research/
   descriptor/aggregate evidence. Do not create a sprint packet or status page.

## Shared source command and E2E meaning

Inspect supported commands first:

```powershell
python scripts/real_preview.py --help
python scripts/dev.py --json doctor
```

The shared `refresh --source <source_id>` path selects source acquisition and
processing. Its `strict-live-private-e2e --source <source_id>` acceptance path
runs live acquisition, adapter stages, private import and API/map checks for a
supported source. Configure the permitted source/terms and assigned disposable
target as documented by the runner; no example here grants new publication.

**E2E ready means the source can be acquired, parsed, normalized/cleaned,
inserted and made available as records in the preview map through the shared
command.** Adapter-only, fixture-only and preserved-artifact runs are not live
E2E. An address-only result must also complete required separate enrichment
before claiming new mapped locations. State input observations, source-qualified
candidates, mapped/unmapped results and precision separately. Do not call
observations or grouped source records unique physical facilities.

Use the approved real-data baseline and a disposable copy for data-backed
acceptance. Keep private raw/derived rows outside Git, preferably on D: for
large retained evidence. Do not mutate the frozen baseline or serving database.
A refresh/enrichment run does not publish a new release.

## Checks and integration

Use focused adapter/runner/importer tests while iterating; do not repeatedly
run every suite or rebuild Rust after small unrelated changes. Available
reference checks include:

```powershell
python -m unittest pipeline.sources.denmark.test_adapter pipeline.common.test_orchestrator pipeline.common.test_review_packet
```

For integrated database-backed changes, use the standard pipeline gate
`pwsh -NoProfile -ExecutionPolicy Bypass -File pipeline/tests/run-standard.ps1`
against its documented disposable environment and the required CI checks.
Run live acceptance when the assignment requires it; report skipped/blocked
checks, never as passes.

Keep last valid state on acquisition/schema failure; preserve quarantine and
source-kind boundaries, restrictions and source-qualified identifiers. A future
scheduler calls this shared path; no scheduler-specific adapter framework is needed.
Follow [the coordination contract](../docs/operations/parallel-agent-workflow.md)
for exclusive paths, one integration branch, worker commits and cleanup.
