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

Run `pipeline/tests/benchmarks/discovery_100k.sql` against a disposable PostGIS
database after migrations through `025_discovery_query_indexes.sql` have been
applied. The script creates only `bench_discovery_100k`, fills deterministic
synthetic rows, runs `ANALYZE`, and emits `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`
for the list, cursor, text, bbox, radius, and detail shapes used by the API.
Drop the benchmark table after capture. The benchmark is evidence about query
shape and budget only; it is not publication or release evidence.

## Local disposable capture (2026-09-15)

Against PostGIS 16 / PostGIS 3.4 with 100,000 synthetic rows, the captured
single-query timings were: first page 0.072 ms, cursor page 0.136 ms, text
search 3.206 ms, bbox 1.578 ms, radius 0.057 ms, and detail lookup 5.848 ms.
The list/cursor/search/spatial plans used the expected B-tree, trigram GIN, or
geography GiST indexes. These are cold/warm local database plan samples, not a
production load test or an end-to-end p95 claim.
