# V2 public projection read-path decision

## Current implementation (2026-10-09)

The approved v0 repair supersedes the earlier no-request-cache decision below.
Public map reads use the manifest-bound discovery read model and a prepared,
serialized projection. Rust keeps at most eight projection identities in memory
and coalesces concurrent builds. Startup warms the current official compact
projection in the background; readiness and other requests are not blocked.
The first request can still wait if warming has not finished.

Every server lookup, including conditional `304` responses, first verifies the
current eligible release, manifest checksum and suppression generation. The
cache key also includes profile and format. Migration 067 advances that
generation for taxonomy assignment changes. An identity change causes a new
build rather than serving stale rows; a restart loses the in-memory cache.

`/api/v2/map/feed?format=compact` returns `compact-v1`: one UUID and coordinate
pair per point, with dictionaries for repeated source/category/precision values.
The existing GeoJSON response remains available. Both formats have the same
release metadata, counts and point semantics. The browser expands the compact
response for native MapLibre clustering, whose default radius remains 30px.

The public map repository uses Cache Storage, bounded to three identities,
keyed by profile/release/manifest/generation. It validates release identity
before reuse, shares simultaneous loads, and isolates subscriber cancellation.
The debug menu can clear that cache. Searches, credentials and contribution
input are not persisted by this public cache. Cache Storage is a
browser capability, not a guarantee of permanent retention or offline access.

The loopback-only repair preview has a separate Cache Storage namespace,
`uec-candidate-map-projection-v1`, keyed by the configured release and snapshot.
It revalidates through ETag/304 and shares concurrent loads. Its debug action
clears the current preview mode's cache, not every cache namespace. Clearing
advances a write generation so older background writes cannot restore cleared
entries. The Rust candidate projection cache likewise shares builds and serves
conditional requests without rebuilding unchanged bodies. Ordinary HTTP gzip
and Brotli compression are supported; no custom compression protocol is used.
The private preview is distinct from the frozen public v0 projection.

Ordinary list queries select a bounded candidate page before taxonomy
enrichment. `meta.total_count` describes the full eligible filtered result,
independent of cursor/page size. Taxonomy-dependent searches retain their
matching semantics; they are not claimed to have the same cost as plain browse.

The 2026-10-10 repair filters taxonomy through the release-bound assignment
indexes before assembling row detail. Migration 070 separates the candidate
cohort review path from the event-review path; the API chooses a fixed relation
using only the already-selected server release, never a client-provided SQL
identifier. Both paths retain live access, suppression and manifest checks.
Six real-v0 category/precision pairs returned unchanged totals in 1.7–2.7
seconds locally, versus 6.9–15.1 seconds before branch isolation. These are
single-host samples, not a production latency guarantee. The earlier migration
069 CTE hint alone did not establish a speed improvement.

Real-v0 acceptance verifies compact/GeoJSON parity, 63,601 searchable records,
48,756 points, filtered count unions, conditional responses and bounded exports.
Unit tests separately cover persistent reuse, identity changes, clearing,
concurrent loads and cancellation. These are local functional checks, not a
production capacity or tail-latency claim.

## Earlier decision and evidence (historical)

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

The manifest-bound read-model builder was subsequently hardened for the
representative HTTP rehearsal. Its high-volume activation now inserts from a
single set-based query and uses the same release-scoped correlated review,
current-access, and suppression gates as the live read model. It does not read
through the older compatibility history view, whose suppression UNION expands
all source records before release filtering. On the 2026-09-17 Windows/Docker
rehearsal host, the 100k synthetic activation took 14,790.181 ms and the 150k
activation took 22,674.087 ms; interrupted activation remains transactional
and fail-closed.

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
