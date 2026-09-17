# V2 public projection read-path decision

## Decision

Keep the public projection live and release-scoped, with the flattened view in
migration 032. It evaluates publication review, current suppression, profile
eligibility, geocode display precision, and lifecycle state at read time. Do
not add a request cache or wire a materialized public surface into the API in
this performance slice. A disposable release-built component prototype is
implemented behind a candidate view for invariant testing only.

## Evidence

The earlier pre-rewrite synthetic component benchmark at 5,000 observations
measured roughly:

| Component | Execution time |
| --- | ---: |
| Release/review/suppression eligibility | 663 ms |
| Per-release eligible observation summary | 3,362 ms |
| Geocode lookup | 16 ms |
| City/coarse-location lookup | 15 ms |
| Lifecycle lookup | 1 ms |
| Full pagination projection | 5,097 ms |
| Full spatial projection | 4,690 ms |

The flattened view removed repeated nested expansion. The scale-hardening
revision keeps eligibility inline and uses window aggregates for the
per-facility summary, allowing release and facility predicates to be pushed
before the summary work while preserving the same live joins. In a fresh
synthetic 5,000-row local plan capture, list and facets measured approximately
108 ms and 106 ms. These are single-query samples, not p95 or capacity
measurements.

The prototype builder is reproducible with:

```powershell
python pipeline/scripts/maintenance/build_release_summary_component.py RELEASE_ID
```

It stores release-membership observation facts, not a frozen current-public
decision. The candidate summary joins the exact release manifest checksum and
re-evaluates current review, profile, and suppression state on every read.
At 1,000 rows its candidate summary took about 406 ms versus 121 ms for the
current live summary; at 5,000 rows it took about 9,984 ms versus 3,044 ms in
the earlier component comparison. The candidate therefore still proves the
safety protocol but does not justify API integration or a production capacity
claim.

## Alternatives considered

1. Request caching is rejected. An emergency suppression, privacy decision,
   or release/profile change must take effect on the next read; cache expiry
   is not an acceptable enforcement mechanism.

2. A release-built immutable base projection could reduce repeated joins, but
   it is not itself a public surface. A future implementation would need to
   build it from an identified release manifest, validate row counts and
   checksums, publish it atomically, and fail closed when the artifact is
   missing, stale, or inconsistent.

3. Even with an immutable base, every public read would still have to join the
   current release/profile decision and evaluate current suppression directly.
   Suppression cannot be handled only by a delayed refresh or by invalidating a
   cache. Public summaries would need either a live eligible aggregation or a
   transactionally maintained restriction delta with tests for reimport,
   release reconstruction, restoration, and cross-profile isolation.

4. Because the dominant cost is the live eligible summary rather than
   geocode/city/lifecycle lookup, materializing a base component is not yet
   sufficiently justified by this evidence. The current view is the safer
   architecture until a representative deployment load test and a precise
   summary strategy are approved.

## Required safeguards for future work

Any release-built component must specify, before implementation:

- manifest-bound build inputs and deterministic row/count/checksum validation;
- atomic activation and a fail-closed missing/stale-artifact path;
- live review, profile, and suppression joins on every public read;
- suppression/restriction replay and reimport invalidation behavior;
- backup/restore ordering that keeps the service stopped until the independent
  restriction-ledger gate and current replay pass;
- semantic E2E coverage for publication, profile, suppression, privacy,
  ordering, null-region, and detail/list agreement.

This document is an implementation boundary, not a production capacity claim.
