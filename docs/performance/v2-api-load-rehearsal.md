# V2 synthetic API load rehearsal

This is a bounded, local, synthetic rehearsal of the V2 API. It is not a
production capacity claim. Each run creates a fresh disposable PostGIS E2E
environment, applies every migration, seeds only deterministic synthetic
records, exercises the API and graph read paths, and destroys the environment.
The report contains aggregate counters and latency percentiles only; raw rows,
coordinates, identifiers, and response bodies are not retained in Git.

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
```

The runner bounds observations at 150,000, concurrency at 16, and requests per
level at 80. It refuses non-loopback API targets. The 150,000-row bound is an
explicitly finite synthetic safety limit, not a statement about supported
production scale.

Each run also captures row-free planner metadata for the list, facets, radius,
and graph read shapes. Reports include estimated costs, node counts, relation
and index names, and sequential-scan relation names; they do not include SQL,
plan filters, identifiers, coordinates, or result rows.

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
| 100,000 | 1 | 40 | 5 | 35 | 0 | 0.514 | 2009.788 / 2030.512 / 2037.203 | 1 / 1 |
| 100,000 | 4 | 40 | 5 | 35 | 0 | 1.825 | 2008.869 / 2781.670 / 2816.510 | 2 / 1 |
| 100,000 | 8 | 40 | 5 | 35 | 0 | 3.313 | 2012.523 / 3854.425 / 4288.312 | 5 / 3 |
| 100,000 | 16 | 40 | 5 | 35 | 0 | 4.670 | 2013.890 / 5622.259 / 6525.069 | 8 / 7 |
| 150,000 | 1 | 40 | 5 | 35 | 0 | 0.485 | 2010.421 / 2410.614 / 2664.676 | 2 / 1 |
| 150,000 | 4 | 40 | 5 | 35 | 0 | 1.791 | 2010.972 / 3000.228 / 3257.245 | 2 / 1 |
| 150,000 | 8 | 40 | 5 | 35 | 0 | 3.315 | 2011.654 / 4249.663 / 4262.470 | 5 / 4 |
| 150,000 | 16 | 40 | 5 | 35 | 0 | 4.713 | 2011.055 / 5836.123 / 6133.832 | 8 / 7 |

The 5,000-row fixture is clean at every tested concurrency. At 25,000 rows,
the single-worker level is clean, but timeouts begin at concurrency 4. At
100,000 and 150,000 rows, only five of forty mixed requests completed at each
level; the two-second client budget is not viable. No server-side 5xx or
connection errors occurred. Pool pressure rose with concurrency, but the
observed failure mode was request timeout rather than pool exhaustion.

These are actual local measurements from the post-optimization harness, not
capacity claims. The run artifacts remain in the ignored `.tmp/` directory;
only these aggregate values and row-free plan summaries are documented here.

The row-free planner summaries estimated list/facets/radius costs of roughly
82,989 at 5,000 rows, 416,635 at 25,000, 1,683,553 at 100,000, and 2,525,908
at 150,000. The graph-shaped plan estimated roughly twice the discovery cost.
The repeated sequential-scan relations were control-plane tables used by the
live suppression and review views, including `source_records`,
`record_access_events`, `suppression_case_events`, and
`suppression_references`. No query-plan row payloads or filter values were
retained.

The dominant slow path remains the live eligibility/summary work documented in
`v2-public-projection-read-path.md`. The evidence does not justify caching,
relaxing current suppression checks, or claiming production readiness.

## Data and ethics boundary

The fixture uses only synthetic source, facility, observation, graph, and
geocode-shaped records. The API harness reads response bodies to completion
and immediately discards them. JSON outputs belong under `.tmp/`, which is
ignored. Do not copy raw or private rows, coordinates, source paths, or
identifiers into reports, logs, backups, or commits.
