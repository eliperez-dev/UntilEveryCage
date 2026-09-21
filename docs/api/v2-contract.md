# V2 API contract

The machine-readable contract is [v2-contract.json](v2-contract.json). Successful list/detail response shapes remain unchanged; additive metadata identifies release coverage and prevents facility rows from being mistaken for story-wide or animal totals. Errors use one additive, stable envelope:

```json
{"api_version":"v2","error":{"code":"invalid_profile","message":"profile is unsupported"}}
```

Frontend clients should branch on HTTP status and `error.code`, display `message` only as user-safe text, and treat unknown codes as generic failures. A list request with no promoted eligible release is a successful empty response; an unavailable database is `503`; an absent or suppressed detail is `404`; rate limiting is `429` with `Retry-After`.

Researchers may request `GET /api/v2/locations.csv?profile=official` (or another explicit supported profile). The export is bounded to 1,000 rows, uses deterministic CSV columns and escaping, contains only the public reviewed projection, and includes `release_profile`, `release_id`, and `manifest_sha256` on every row plus matching response headers. It is unavailable when no promoted release with a manifest exists; it never exposes raw evidence or restricted records.

For reproducible bulk snapshots, use `pipeline/scripts/stages/export-release.py` with an explicit release ID and profile. It emits deterministic CSV and GeoJSON, a schema/data dictionary, `manifest.json`, and `SHA256SUMS.json`; it fails closed on test-only, unapproved, privacy-failed, suppressed, profile-mismatched, or unclear-rights rows. See [the data-product contract](../data-product.md) and [the machine-readable dictionary](../data-dictionary.json). The package is the citation artifact; the bounded API export is a convenience view of the same public projection.

Clients can discover the current controlled vocabularies at `GET /api/v2/discovery/filters`. Category/source/profile/precision/lifecycle values are allowlisted and versioned; `country_code` is validated as an uppercase ISO alpha-2 code and `region` is a bounded release-backed city/region value. The bounded `q` parameter searches canonical name, city, country, category, and source name server-side. Bbox (`min_lon`, `min_lat`, `max_lon`, `max_lat`) and radius (`latitude`, `longitude`, `radius_km`) are mutually exclusive and validated before release access. New country adapters should register capabilities and vocabularies in the contract before becoming public.

`GET /api/v2/discovery/facets` returns deterministic value/count pairs for the same controlled dimensions, scoped to the selected promoted profile and current public projection. Its metadata includes the selected release, ruleset, release creation time, and an explicit coverage scope. Counts are eligible public facility-projection rows after current suppression; they are not story-wide totals or animal counts. It applies the supplied filters before counting, caps each dimension at 20 values, and returns no addresses, queries, raw payloads, inactive releases, or restricted records.

Pagination is deterministic and bounded (`limit` defaults to 100 and is capped at
1,000). `cursor` is the preferred continuation mechanism and contains the last
returned `facility_id`. `offset` remains supported for compatibility (default 0,
bounded to 1,000,000); `cursor` and `offset` cannot be combined. Bbox uses
`min_lon`, `min_lat`, `max_lon`, and `max_lat`; radius uses `latitude`,
`longitude`, and `radius_km`; a request cannot use both spatial forms.

Clients should treat `(profile, release_id, ruleset_version, query)` as the
logical snapshot key and discard or refresh cursor pages when release metadata
changes. The current frontend uses request-level `cache: no-store`; this
contract does not promise a durable client cache, a server revocation signal, or
a cache-invalidation event. Current suppression is authoritative on each read,
including filtered results, exports, history, reimports, and restores.

List and detail metadata use the same coverage scope. Their source identifiers, source URL, retrieval timestamp, review state, release, and ruleset remain record-level provenance; they do not establish a story-wide denominator or an animal count. Narrative aggregate claims must come from a separately sourced, dated editorial ledger.

The current wire intentionally stops at the fields listed in
[v2-location.schema.json](v2-location.schema.json). It does not promise
evidence content hashes, source publication/effective dates or availability
status, geocoder provider/query/precision metadata, independent review-event
identifiers/scopes/dates/outcomes, or richer release-scoped approval metadata.
Those are tracked as explicit deferred gaps in the
[product convergence gap ledger](v2-product-convergence-gap-ledger.md), not
silently inferred from the current fields.
