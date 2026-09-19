# V2 synthetic API load rehearsal

This is a bounded, local, synthetic rehearsal of the V2 API. It is not a
production capacity claim. Each run creates a fresh disposable PostGIS E2E
environment, applies every migration, seeds only deterministic synthetic
records, exercises the API and graph read paths, and destroys the environment.
The report contains aggregate counters, latency percentiles, and row-free
environment/planner metadata only; raw rows, coordinates, identifiers, and
response bodies are not retained in Git.

## Reproduction

Install the pinned Python dependencies, then run:

```powershell
python pipeline/scripts/benchmarks/run_api_load_rehearsal.py `
  --observations 5000 `
  --concurrency 1,4,8,16 `
  --requests-per-level 40 `
  --timeout-ms 2000 `
  --json-output .tmp/api-load-5000.json

python pipeline/scripts/benchmarks/run_api_load_rehearsal.py `
  --observations 25000 `
  --concurrency 1,4,8,16 `
  --requests-per-level 40 `
  --timeout-ms 2000 `
  --json-output .tmp/api-load-25000.json

python pipeline/scripts/benchmarks/run_api_load_rehearsal.py `
  --observations 100000 `
  --concurrency 1,4,8,16 `
  --requests-per-level 40 `
  --timeout-ms 2000 `
  --json-output .tmp/api-load-100000.json

python pipeline/scripts/benchmarks/run_api_load_rehearsal.py `
  --observations 150000 `
  --concurrency 1,4,8,16 `
  --requests-per-level 40 `
  --timeout-ms 2000 `
  --json-output .tmp/api-load-150000.json
```

The runner bounds observations at 150,000, concurrency at 16, and requests per
level at 80. It refuses non-loopback API targets. The 150,000-row bound is an
explicitly finite synthetic safety limit, not a statement about supported
production scale.

Each run also captures row-free planner metadata for the list, facets, radius,
and graph read shapes, setup timings, runtime metadata, and final PostgreSQL
database size. Reports include estimated costs, node counts, relation and index
names, and sequential-scan relation names; they do not include SQL, plan
filters, identifiers, coordinates, or result rows.

At scales above 1,000 facilities, the graph-shaped fixture is intentionally
capped at 1,000 organizations, relationships, and claims. This keeps the
150,000-row run focused on the facility discovery API rather than multiplying
unrelated graph evidence rows; graph scale is measured separately.

When an authorized private V2 normalized corpus is available, first create a
row-free distribution report and then pass it to the same synthetic rehearsal:

```powershell
python pipeline/scripts/benchmarks/build_private_distribution.py `
  --normalized data/private/<run>/normalized/records.jsonl `
  --output .tmp/private-v2-distribution.json

python pipeline/scripts/benchmarks/run_api_load_rehearsal.py `
  --distribution-report .tmp/private-v2-distribution.json `
  --concurrency 1,4,8,16 --requests-per-level 10 `
  --timeout-ms 2000 --json-output .tmp/api-load-private-distribution.json
```

The distribution report is explicitly blocked and contains only aggregate
country/category/precision strata. The rehearsal expands those strata into
deterministic synthetic rows; it never imports private names, identifiers,
addresses, coordinates, or source values into the disposable database or
report. A real corpus therefore informs shape without becoming publication,
release, or benchmark-output data.

## Captured evidence (2026-09-17)

| Synthetic observations | Concurrency | Requests | Successes | Timeouts | 5xx | Throughput (rps) | p50 / p95 / p99 (ms) | Max active / waiting DB sessions |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5,000 | 1 | 40 | 40 | 0 | 0 | 4.631 | 209.422 / 325.983 / 344.818 | 2 / 1 |
| 5,000 | 4 | 40 | 40 | 0 | 0 | 13.448 | 258.708 / 726.186 / 769.800 | 3 / 1 |
| 5,000 | 8 | 40 | 40 | 0 | 0 | 21.698 | 342.017 / 601.806 / 620.059 | 4 / 3 |
| 5,000 | 16 | 40 | 40 | 0 | 0 | 21.352 | 531.698 / 1396.417 / 1526.794 | 9 / 8 |
| 25,000 | 1 | 40 | 40 | 0 | 0 | 1.075 | 923.039 / 1370.227 / 1411.224 | 2 / 1 |
| 25,000 | 4 | 40 | 35 | 5 | 0 | 2.696 | 1351.349 / 2028.480 / 2569.991 | 2 / 1 |
| 25,000 | 8 | 40 | 30 | 10 | 0 | 4.138 | 1857.025 / 2816.699 / 3052.711 | 5 / 4 |
| 25,000 | 16 | 40 | 8 | 32 | 0 | 5.048 | 2011.321 / 5568.897 / 5627.295 | 8 / 7 |
| 100,000 | 1 | 40 | 40 | 0 | 0 | 1.087 | 1015.709 / 1202.332 / 1219.876 | 2 / 1 |
| 100,000 | 4 | 40 | 40 | 0 | 0 | 4.058 | 992.229 / 1394.278 / 1470.834 | 3 / 2 |
| 100,000 | 8 | 40 | 40 | 0 | 0 | 6.476 | 1133.208 / 1677.974 / 1749.388 | 6 / 3 |
| 100,000 | 16 | 40 | 14 | 26 | 0 | 6.616 | 2007.854 / 2470.506 / 2503.633 | 8 / 7 |
| 150,000 | 1 | 40 | 38 | 2 | 0 | 0.820 | 1248.998 / 1831.875 / 2023.506 | 1 / 1 |
| 150,000 | 4 | 40 | 40 | 0 | 0 | 2.776 | 1460.322 / 1947.559 / 1983.054 | 2 / 1 |
| 150,000 | 8 | 40 | 25 | 15 | 0 | 4.195 | 1879.540 / 2023.364 / 2025.709 | 6 / 4 |
| 150,000 | 16 | 40 | 8 | 32 | 0 | 6.627 | 2010.105 / 2444.161 / 2704.441 | 10 / 6 |

The 5,000-row fixture is clean at every tested concurrency. At 25,000 rows,
the single-worker level is clean, but timeouts begin at concurrency 4. In the
final 100,000-row run, levels 1/4/8 were clean and level 16 completed 14/40
requests. In the final 150,000-row run, level 4 was clean, level 1 completed
38/40, and levels 8/16 completed 25/40 and 8/40. No server-side 5xx or
connection errors occurred. Pool pressure rose with concurrency, and the
observed failure mode was request timeout rather than pool exhaustion. The
single-run 150k concurrency boundary is variable on this workstation, so it
is not a CI or production capacity promise.

These are actual local measurements from the post-optimization harness, not
capacity claims. The 100k setup took 29,047.971 ms to seed and 14,790.181 ms
to build the gated read model; the 150k setup took 43,387.792 ms and
22,674.087 ms respectively. The final PostgreSQL database sizes were
408,031,715 bytes (100k) and 590,123,491 bytes (150k). The run artifacts remain
in the ignored `.tmp/` directory; only these aggregate values and row-free
plan summaries are documented here.

The exact host was a Lenovo 81Q6 with an Intel Core i7-9750H (12 logical
processors), 15.91 GiB RAM, Windows 11 Home build 10.0.26200, AMD64 Python
3.11.2. Docker Engine/Desktop was 28.5.2 and the database image was
`postgis/postgis:16-3.4` (`sha256:44126d872ac91993766c341e369c539e8196614321765d36a6f1bab0419a5fa5`).
The harness records host metadata and database size; container RSS/peak memory
was not captured, so no PostgreSQL memory-capacity claim is made.

The row-free planner summaries estimated list/facets/radius costs of roughly
82,989 at 5,000 rows, 416,635 at 25,000, 1,683,553 at 100,000, and 2,525,908
at 150,000. The graph-shaped plan estimated roughly twice the discovery cost.
The repeated sequential-scan relations were control-plane tables used by the
live suppression and review views, including `source_records`,
`record_access_events`, `suppression_case_events`, and
`suppression_references`. No query-plan row payloads or filter values were
retained.

The dominant slow path remains the live eligibility/summary work documented in
`v2-public-projection-read-path.md`. The fixture closure uses a set-based,
release-scoped builder query with correlated live review/access/suppression
gates; it does not cache public decisions or relax safety checks. The evidence
does not justify caching, relaxing current suppression checks, or claiming
production readiness.

## Data and ethics boundary

The fixture uses only synthetic source, facility, observation, graph, and
geocode-shaped records. The API harness reads response bodies to completion
and immediately discards them. JSON outputs belong under `.tmp/`, which is
ignored. Do not copy raw or private rows, coordinates, source paths, or
identifiers into reports, logs, backups, or commits.
