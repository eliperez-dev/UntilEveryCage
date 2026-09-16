# Pipeline scripts

Follow [docs/ETHICS.md](../../docs/ETHICS.md) for every stage, diagnostic, and maintenance utility. Preserve ordinary history while honoring authorized retention/removal exceptions. Avoid printing sensitive addresses, geocoding queries, credentials, or submitted payloads into public logs and fixtures. Active restrictions must survive reprocessing; see the [policy checklist](../../docs/governance/policy-implementation-todo.md) for outstanding enforcement work.

Scripts are grouped by their role in the auditable ingestion workflow:

- `stages/` contains repeatable pipeline stages that produce the next documented artifact: parsing, normalization, classification, validation, geocoding, and import.
- `diagnostics/` contains read-only inspection and sampling tools. These help evaluate a source or service and are not required for a normal full run.
- `maintenance/` contains repository and migration-support utilities, such as the legacy manifest builder.

`diagnostics/build-source-operations-health.py` reads the private append-only
source run ledger and the checked-in schedule inventory to emit a deterministic,
row-free health index. It does not acquire data, update `docs/source-status`,
promote a release, or make a public health claim.

Run scripts from the repository root so their documented paths and output locations are stable. Each stage should accept explicit input and output paths (or a run identifier), preserve source timestamps and checksums, and emit useful progress logs. Generated artifacts belong under `data/`, not beside the scripts.

## Adding another country

Country-owned adapters and source-specific stages live under
`pipeline/sources/<country>/`; Denmark is the current reference layout. The
paths under `pipeline/scripts/stages/` remain shared generic stages or
compatibility shims for legacy commands, while shared orchestration and
validation helpers stay outside country directories. Do not hide source-
specific assumptions in shared code.

Keep diagnostics separate from production stages, and add a short entry to this file when a new script category is introduced.

## Database geocoding worker

After records are imported, enqueue address jobs and run a provider adapter through the shared worker:

```powershell
python pipeline/scripts/stages/enqueue-geocode-jobs.py data/staging/denmark-smiley/<run>/03-classify/classified-records.jsonl --limit 5
python pipeline/scripts/stages/geocode-worker.py --provider dawa --limit 5 --delay 1.0
```

The worker writes append-only job events and geocode attempts. It does not modify source records or observations. New providers should implement the adapter contract in `pipeline/geocoding/` and reuse the worker’s lifecycle, retry, logging, and persistence behavior.
# Private environment controls

`maintenance/private-environment-gate.py` is the clean-checkout and
deployment-shaped gate. In production it requires explicit runtime/CORS/proxy
configuration, a separate durable restriction ledger and post-restore
snapshot, a complete migration inventory, and a trusted release-manifest
digest. It is validation only: it does not acquire, promote, or publish data.

`maintenance/replay-restriction-ledger.py` applies current payload-free
suppression references to a restored database in one transaction. It rejects
missing or ambiguous source keys, supports only whole-record suppression,
writes a row-free post-replay snapshot, and can emit idempotent SQL for a
portless recovery container. Run the service startup gate after replay; never
start public service on a stale restore.
