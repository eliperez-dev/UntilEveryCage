# V2 public projection read-path decision

## Decision

Keep the public projection live and release-scoped, with the flattened view in
migration 032. It evaluates publication review, current suppression, profile
eligibility, geocode display precision, and lifecycle state at read time. Do
not add a request cache or a materialized public surface in this performance
slice.

## Evidence

The synthetic component benchmark at 5,000 observations measured roughly:

| Component | Execution time |
| --- | ---: |
| Release/review/suppression eligibility | 663 ms |
| Per-release eligible observation summary | 3,362 ms |
| Geocode lookup | 16 ms |
| City/coarse-location lookup | 15 ms |
| Lifecycle lookup | 1 ms |
| Full pagination projection | 5,097 ms |
| Full spatial projection | 4,690 ms |

The flattened view removed repeated nested expansion and made the 1,000-row
concurrent rehearsal clean at all tested levels. At 5,000 rows, the remaining
summary and eligibility work still exceeds the current 2-second rehearsal
budget. A candidate that allowed the summary CTE to inline was measured and
rejected because the 5,000-row facets plan increased from about 4,501 ms to
6,622 ms.

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
