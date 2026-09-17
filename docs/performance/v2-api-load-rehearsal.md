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
  --requests-per-level 10 `
  --timeout-ms 2000 `
  --json-output .tmp/api-load-5000.json

python pipeline/scripts/benchmarks/run_api_load_rehearsal.py `
  --observations 25000 `
  --concurrency 1,4,8,16 `
  --requests-per-level 10 `
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

## Captured evidence (2026-09-16)

| Synthetic observations | Concurrency | Requests | Successes | Timeouts | 5xx | Throughput (rps) | p50 / p95 / p99 (ms) | Max active / waiting DB sessions |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5,000 | 1 | 10 | 10 | 0 | 0 | 4.579 | 215.700 / 302.345 / 302.345 | 2 / 1 |
| 5,000 | 4 | 10 | 10 | 0 | 0 | 7.316 | 328.596 / 900.362 / 900.362 | 2 / 1 |
| 5,000 | 8 | 10 | 10 | 0 | 0 | 11.290 | 507.344 / 595.657 / 595.657 | 5 / 4 |
| 5,000 | 16 | 10 | 10 | 0 | 0 | 14.781 | 464.993 / 598.804 / 598.804 | 7 / 8 |
| 25,000 | 1 | 10 | 10 | 0 | 0 | 0.793 | 1263.909 / 1705.504 / 1705.504 | 3 / 2 |
| 25,000 | 4 | 10 | 5 | 5 | 0 | 1.770 | 2004.356 / 2017.358 / 2017.358 | 2 / 1 |
| 25,000 | 8 | 10 | 3 | 7 | 0 | 2.640 | 2010.196 / 2011.692 / 2011.692 | 5 / 4 |
| 25,000 | 16 | 10 | 3 | 7 | 0 | 2.922 | 2006.612 / 2010.724 / 2010.724 | 9 / 7 |
| 100,000 | 1 | 10 | 1 | 9 | 0 | 0.497 | 2004.792 / 2017.417 / 2017.417 | 2 / 1 |
| 100,000 | 4 | 10 | 1 | 9 | 0 | 1.657 | 2007.899 / 2014.835 / 2014.835 | 2 / 1 |
| 100,000 | 8 | 10 | 1 | 9 | 0 | 2.480 | 2011.186 / 2026.853 / 2026.853 | 5 / 3 |
| 100,000 | 16 | 10 | 1 | 9 | 0 | 2.366 | 2016.205 / 2031.078 / 2031.078 | 8 / 6 |
| 150,000 | 1 | 10 | 1 | 9 | 0 | 0.489 | 2008.950 / 2024.313 / 2024.313 | 2 / 1 |
| 150,000 | 4 | 10 | 1 | 9 | 0 | 1.651 | 2014.980 / 2023.360 / 2023.360 | 2 / 1 |
| 150,000 | 8 | 10 | 1 | 9 | 0 | 2.476 | 2010.329 / 2015.471 / 2015.471 | 6 / 4 |
| 150,000 | 16 | 10 | 1 | 9 | 0 | 2.506 | 2009.943 / 2030.332 / 2030.332 | 9 / 5 |

The 5,000-row fixture is clean at every tested concurrency. At 25,000 rows,
the single-worker level is clean, but timeouts begin at concurrency 4. At
100,000 and 150,000 rows, only one of ten mixed requests completed at each
level; the two-second client budget is not viable. No server-side 5xx or
connection errors occurred. Pool pressure rose with concurrency, but the
observed failure mode was request timeout rather than pool exhaustion.

These are actual local measurements from the post-optimization harness, not
capacity claims. The run artifacts remain in the ignored `.tmp/` directory;
only these aggregate values and row-free plan summaries are documented here.

The row-free planner summaries estimated list/facets/radius costs of roughly
82,989 at 5,000 rows, 416,639 at 25,000, 1,683,553 at 100,000, and 2,525,920
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
