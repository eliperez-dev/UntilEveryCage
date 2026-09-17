# Bounded large-corpus resilience rehearsal

`pipeline/scripts/benchmarks/run_corpus_resilience.py` is the reusable lane for
the private large-corpus failure modes that the real-corpus reports previously
left unexercised. It expands only the row-free source-count distribution in
`data/manifests/sprint4-real-corpus-regression.json` into deterministic
synthetic rows in a temporary directory. The rows are never committed, and
the report contains counts, timings, byte sizes, and bounded-memory
observations only.

Run the quick, database-free plan check with:

```powershell
python pipeline/scripts/benchmarks/run_corpus_resilience.py `
  --plan-only --max-records 50000 `
  --json-output .tmp/corpus-resilience-plan.json
```

Run the full disposable PostGIS rehearsal with Docker Desktop and the pinned
Python dependencies:

```powershell
python pipeline/scripts/benchmarks/run_corpus_resilience.py `
  --max-records 50000 --batch-size 500 `
  --json-output .tmp/corpus-resilience.json
```

The opt-in E2E assertions run the same lane:

```powershell
$env:UEC_RUN_E2E = "1"
$env:UEC_RUN_CORPUS_RESILIENCE = "1"
python -m unittest pipeline.tests.e2e.test_corpus_resilience -v
```

The exact safety limits are 50,000 selected records, 2,000 rows per import
batch, four maximum simulated interruption batches, loopback-only database
connectivity, a unique disposable Compose project, and teardown with volume
removal in `finally`. The default is the full 50,000-record distribution and a
500-row batch. A smaller `--max-records` value is proportionally allocated by
the largest-remainder method so source shape remains representative.

The lane measures: migration wall time and applied migration count; import
wall time; committed rows before and after a post-commit interruption; resume
rows; duplicate-import new rows and count stability; custom-format dump bytes;
backup and restore wall time; stale pre-service gate rejection; current
suppression replay; database size; total runtime; and Python `tracemalloc`
peaks while loading/importing one partition. The database-size and timing
observations describe this local disposable run only. `tracemalloc` does not
observe PostgreSQL shared buffers, container RSS, or OS peak memory.

The backup is created before the synthetic current suppression is applied.
After restoring it, the pre-service gate must reject the stale state; only
after the temporary current ledger is replayed may the final gate pass. The
same source-record reference is used through a source-key ledger, so the
rehearsal covers same-source reimport protection without copying restricted
payloads.

The full lane was not run in this checkout when Docker Desktop was unavailable;
the focused Python tests and plan-only path remain runnable without Docker.
This harness does not claim real-source quality, adapter correctness,
production capacity, cloud backup durability, WAL recovery, operator access
controls, or publication approval. It also does not measure PostgreSQL or
container memory directly.
