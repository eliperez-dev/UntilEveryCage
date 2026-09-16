# V2 discovery synthetic 100k benchmark

This is a disposable, synthetic benchmark plan. It must never be populated with
retained source records, names, addresses, coordinates, or geocoder responses.

## Budgets

- First list page (50 rows): p95 <= 250 ms at the database, p95 <= 800 ms end to end.
- Cursor page (50 rows): p95 <= 200 ms at the database, p95 <= 700 ms end to end.
- Text search/filter page: p95 <= 350 ms at the database, p95 <= 1 s end to end.
- Spatial viewport/radius page: p95 <= 350 ms at the database, p95 <= 1 s end to end.
- Detail: p95 <= 200 ms at the database, p95 <= 600 ms end to end.
- Browser memory: <= 128 MB attributable to loaded discovery records at 100k rows.

## Reproduction

The reproducible scale runner requires only PostGIS and the pinned Python
dependencies; it does not require application migrations because all benchmark
tables are temporary and synthetic:

```powershell
$env:UEC_DATABASE_URL = "postgresql://uec:uec-local-development-only@localhost:55434/uec?sslmode=disable"
python pipeline/scripts/benchmarks/run_discovery_scale.py --json-output .tmp/discovery-scale.json
```

It creates deterministic 100k and 1m observation sets and runs aggregate
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` checks for list, cursor pagination,
category filters, text filters, bbox, radius, detail, and release/privacy/
suppression-aware graph joins. The plan checker requires the expected index
family for each shape and bounds every result page at 50 rows. The JSON report
contains timings, aggregate buffer counts, plan node types, and index names;
it never contains query rows or source/private values. Closing the connection
automatically drops every temporary table. The benchmark is evidence about
query shape and budget only; it is not publication, release, or production
load evidence.

The original `pipeline/tests/benchmarks/discovery_100k.sql` remains available
as a minimal SQL-only query-shape sample.

## Local disposable capture (2026-09-15)

Against PostGIS 16 / PostGIS 3.4 with 100,000 synthetic rows, the captured
single-query timings were: first page 0.072 ms, cursor page 0.136 ms, text
search 3.206 ms, bbox 1.578 ms, radius 0.057 ms, and detail lookup 5.848 ms.
The list/cursor/search/spatial plans used the expected B-tree, trigram GIN, or
geography GiST indexes. These are cold/warm local database plan samples, not a
production load test or an end-to-end p95 claim.

## Operational interpretation

Capture reports on the same PostGIS image and representative hardware when
comparing revisions. A plan regression, increasing shared reads, or a query
that fails its expected-index check is a release-review input. The measurements
do not establish capacity, cloud cost, or public-source completeness; those
require a separate load test with an approved traffic model and deployment
configuration.

## Sprint 3 5k/25k query-plan capture (2026-09-16)

On a fresh fully migrated PostGIS 16 / PostGIS 3.4 disposable database, the
same row-free runner was executed with `--scales 5000 25000`. All 16 query
observations passed their expected-index checks, returned at most 50 rows, and
reported zero sequential-scan nodes. Aggregate execution times in milliseconds
were:

| Query shape | 5,000 | 25,000 |
| --- | ---: | ---: |
| list | 0.100 | 0.040 |
| pagination | 0.010 | 0.009 |
| filters | 0.046 | 0.044 |
| text filter | 0.042 | 0.047 |
| bbox | 0.039 | 0.060 |
| radius | 9.658 | 7.150 |
| detail | 0.011 | 0.011 |
| graph-ready join | 0.133 | 0.118 |

These are single-query local plan samples over temporary synthetic tables. They
demonstrate query-shape/index behavior only and do not establish API latency,
concurrency capacity, or production readiness. The companion API rehearsal and
its limitations are recorded in `v2-api-load-rehearsal.md`.
