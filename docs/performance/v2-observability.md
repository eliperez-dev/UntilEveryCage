# V2 backend observability and spatial operations

The API emits one bounded JSON event after each HTTP response. The event uses
an allowlisted route class rather than the request path, so facility IDs,
coordinates, query strings, and arbitrary paths are never logged:

```json
{"event":"http_request","method":"GET","route_class":"v2_locations_list","status":200,"outcome":"success","latency_ms":12}
```

The fields are intentionally limited to method, route class, status, outcome,
and latency. Latency is capped at 60 seconds. There is no request ID, client
address, forwarded address, query text, response body, secret, or source-row
field. Health requests are classified separately so operators can exclude
probe traffic from user-facing latency summaries. `client_error` and
`server_error` outcomes make bounded error-rate aggregation possible from the
existing process logs without a telemetry service.

## Spatial investigation

The synthetic scale runner covers the same bounded radius predicate and checks
that the geography GiST index is selected. On the local PostGIS 16 / PostGIS
3.4 disposable environment, the 1m radius sample was 238.354 ms in the
baseline run and 201.824 ms in a later run with the projection-support
migration applied. Because the runner uses temporary benchmark tables, this
delta is not attributable to migration 030; it is retained only as directional
before/after aggregate evidence. These are single EXPLAIN samples, not p95 or
capacity measurements; cache state and planner variation can move them
materially.

The public display projection computes a latest geocode and, for approximate
records, a city reference point per candidate row. Migration 030 adds
supporting indexes for both append-only lookup paths:

- `geocode_results_discovery_latest_idx` preserves newest-result ordering,
  including unresolved/no-point results.
- `city_reference_points_discovery_lookup_idx` supports the country,
  case-insensitive city, and postal lookup.

No radius predicate, ordering rule, privacy filter, or release gate was
weakened. If a deployment still approaches the database budget, capture a
representative approved load test before changing pool sizes or introducing a
materialized projection.

## Operator procedure

1. Run the synthetic scale benchmark against the pinned PostGIS image and
   compare aggregate reports on the same class of hardware.
2. Treat a missing expected index, any sequential scan, a page over 50 rows,
   or a radius result above the documented database budget as a review signal.
3. Use the JSON request logs to aggregate latency and status by route class.
   Do not add raw request paths, query parameters, headers, IP addresses, or
   response payloads to the log pipeline.
4. Keep the service stopped during backup restore until the independent
   restriction-ledger gate and current replay succeed.

## Concurrent-load rehearsal

For a local disposable rehearsal against the actual populated API projection:

```powershell
python pipeline/scripts/benchmarks/run_api_load_rehearsal.py `
  --observations 5000 --concurrency 1,4,8,16 `
  --requests-per-level 40 --timeout-ms 2000 `
  --json-output .tmp/api-load.json
```

The harness starts its own E2E PostGIS/API environment, seeds deterministic
synthetic released rows and graph projections, runs a fixed mix of list,
filters, bbox, radius, facets, detail, and graph-ready reads, then destroys
the environment. It refuses non-loopback targets and bounds observations,
concurrency, request count, and timeout. It reports aggregate p50/p95/p99,
throughput, status/error/timeouts, response byte totals, observed database
active/waiting sessions, and pool-pressure signals only. It does not retain
request paths, query values, coordinates, IDs, client data, or response rows.

The default rehearsal currently establishes no clean concurrency level: the
1,000- and 5,000-observation runs show timeout pressure across the tested
levels, with facets a repeatable hotspot. Therefore it must not be used to
choose a production pool size or to claim capacity. Keep production launch
and pool sizing blocked pending an approved representative traffic test on the
deployment topology. The 2-second request timeout and 350 ms database
radius-query budget remain review thresholds for fail-safe behavior, not
performance guarantees.

The benchmark and logs provide operational evidence only. They do not establish
source completeness, publication eligibility, production capacity, cloud
cost, or a guarantee for a particular traffic pattern.
