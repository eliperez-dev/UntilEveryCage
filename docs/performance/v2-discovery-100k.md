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
