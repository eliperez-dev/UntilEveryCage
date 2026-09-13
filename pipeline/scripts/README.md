# Pipeline scripts

Follow [docs/ETHICS.md](../../docs/ETHICS.md) for every stage, diagnostic, and maintenance utility. Preserve ordinary history while honoring authorized retention/removal exceptions. Avoid printing sensitive addresses, geocoding queries, credentials, or submitted payloads into public logs and fixtures. Active restrictions must survive reprocessing; see the [policy checklist](../../docs/governance/policy-implementation-todo.md) for outstanding enforcement work.

Scripts are grouped by their role in the auditable ingestion workflow:

- `stages/` contains repeatable pipeline stages that produce the next documented artifact: parsing, normalization, classification, validation, geocoding, and import.
- `diagnostics/` contains read-only inspection and sampling tools. These help evaluate a source or service and are not required for a normal full run.
- `maintenance/` contains repository and migration-support utilities, such as the legacy manifest builder.

Run scripts from the repository root so their documented paths and output locations are stable. Each stage should accept explicit input and output paths (or a run identifier), preserve source timestamps and checksums, and emit useful progress logs. Generated artifacts belong under `data/`, not beside the scripts.

## Adding another country

Country-specific adapters currently live in `stages/` because Denmark is the only active adapter. Once a second country is added, move country logic into a dedicated `stages/<country>/` directory and keep shared orchestration or validation helpers outside country directories. Do not hide source-specific assumptions in shared code.

Keep diagnostics separate from production stages, and add a short entry to this file when a new script category is introduced.

## Database geocoding worker

After records are imported, enqueue address jobs and run a provider adapter through the shared worker:

```powershell
python pipeline/scripts/stages/enqueue-geocode-jobs.py data/staging/denmark-smiley/<run>/03-classify/classified-records.jsonl --limit 5
python pipeline/scripts/stages/geocode-worker.py --provider dawa --limit 5 --delay 1.0
```

The worker writes append-only job events and geocode attempts. It does not modify source records or observations. New providers should implement the adapter contract in `pipeline/geocoding/` and reuse the worker’s lifecycle, retry, logging, and persistence behavior.
