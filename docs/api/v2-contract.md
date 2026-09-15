# V2 API contract

The machine-readable contract is [v2-contract.json](v2-contract.json). Successful list/detail response shapes remain unchanged; additive metadata identifies release coverage and prevents facility rows from being mistaken for story-wide or animal totals. Errors use one additive, stable envelope:

```json
{"api_version":"v2","error":{"code":"invalid_profile","message":"profile is unsupported"}}
```

Frontend clients should branch on HTTP status and `error.code`, display `message` only as user-safe text, and treat unknown codes as generic failures. A list request with no promoted eligible release is a successful empty response; an unavailable database is `503`; an absent or suppressed detail is `404`; rate limiting is `429` with `Retry-After`.

Researchers may request `GET /api/v2/locations.csv?profile=official` (or another explicit supported profile). The export is bounded to 1,000 rows, uses deterministic CSV columns and escaping, contains only the public reviewed projection, and includes `release_profile`, `release_id`, and `manifest_sha256` on every row plus matching response headers. It is unavailable when no promoted release with a manifest exists; it never exposes raw evidence or restricted records.

Clients can discover the current controlled vocabularies at `GET /api/v2/discovery/filters`. Filter values are allowlisted and versioned; clients must not invent category/source/profile/status values or send arbitrary free-text search. `country_code` is validated as an uppercase ISO alpha-2 code and returns zero rows when the project has no capability/source coverage for that country. New country adapters should register capabilities and vocabularies in the contract before becoming public.

`GET /api/v2/discovery/facets` returns deterministic value/count pairs for the same controlled dimensions, scoped to the selected promoted profile and current public projection. Its metadata includes the selected release, ruleset, release creation time, and an explicit coverage scope. Counts are eligible public facility-projection rows after current suppression; they are not story-wide totals or animal counts. It applies the supplied filters before counting, caps each dimension at 20 values, and returns no addresses, queries, raw payloads, inactive releases, or restricted records.

List and detail metadata use the same coverage scope. Their source identifiers, source URL, retrieval timestamp, review state, release, and ruleset remain record-level provenance; they do not establish a story-wide denominator or an animal count. Narrative aggregate claims must come from a separately sourced, dated editorial ledger.
