# V2 location API contract

The V2 public API must read from curated database projections, never raw evidence tables. The default query returns only records in a promoted release that are eligible for public access. It is exposed under `/api/v2/locations`; the legacy `/api/locations` endpoint remains separate during migration.

Each location response includes the stable location ID, name, category, source origin, review state, release/profile, display precision, and provenance. Provenance includes `first_observed_at`, `last_observed_at`, and `observation_count`; these describe the project's retained observations, not guaranteed opening or operating dates.

Lifecycle is independent from observation history. Valid states are `active_observed`, `explicitly_closed`, `not_seen_recently`, and `status_unknown`. A record disappearing from a later source snapshot must not be labeled closed. `explicitly_closed` requires traceable closure evidence and a recorded lifecycle event.

The API supports explicit `category`, `source_type`, `display_precision`, and `lifecycle_status` filters while preserving labels. `source_type` is one of `official`, `secondary`, or `user_submitted`; user-submitted profiles are separate from official profiles and are not included in the default official release. Safety-restricted records are excluded from every public response, including historical and filtered queries.

The optional `profile` filter selects `official`, `secondary`, or `community`; absent `profile` means `official`. A release whose stored profile does not match the request is never returned. This prevents community or user-submitted publication contexts from silently appearing in the official view.

Pagination is deterministic offset pagination: `limit` defaults to 100 and is bounded to 1,000; `offset` defaults to 0 and is bounded to 1,000,000. Results are ordered by stable `facility_id`. Cursor pagination should replace offset pagination before very large public collections are exposed.

Release selection and location rows are read inside one `REPEATABLE READ`, read-only transaction. This ensures the response metadata and records come from one database snapshot, even if another release is promoted concurrently. Each release has an explicit publication `profile` (`official`, `secondary`, or `community`), independent of source origin and factual review status; the API returns that stored value rather than inferring it. The legacy `provenance_source` response field is retained as a compatibility alias for `provenance_source_name`; new clients should use the explicit `provenance_source_id`, `provenance_source_name`, `provenance_source_url`, and `provenance_retrieved_at` fields.

Example response fields:

```json
{
  "id": "stable-public-id",
  "category": "slaughter",
  "source_type": "official",
  "display_precision": "exact",
  "first_observed_at": "2021-04-12",
  "last_observed_at": "2026-09-13",
  "observation_count": 6,
  "lifecycle_status": "active_observed",
  "provenance": {"source_name": "Find Smiley", "retrieved_at": "2026-09-13T07:05:28Z"}
}
```
