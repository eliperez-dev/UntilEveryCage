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

The benchmark and logs provide operational evidence only. They do not establish
source completeness, publication eligibility, production capacity, cloud
cost, or a guarantee for a particular traffic pattern.
