# V2 API contract

The machine-readable contract is [v2-contract.json](v2-contract.json). Successful list/detail response shapes remain unchanged; additive metadata identifies release coverage and prevents facility rows from being mistaken for story-wide or animal totals. Errors use one additive, stable envelope:

The final backend boundary, including private exact/inferred graph semantics,
is frozen in [v2-backend-contract-freeze.md](v2-backend-contract-freeze.md) and
its machine-readable companion. This page remains the public location/API
contract; the graph contract does not make private edges public.

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
logical snapshot key and send the displayed `release_id` on list and detail
requests. A pinned list/detail only serves that currently promoted eligible
release/profile. If it has been withdrawn, the API returns `410 release_unavailable`;
if a detail is absent or currently suppressed, it returns `404 location_not_found`.
Clients discard or refresh cursor pages when release metadata changes. Current
suppression is authoritative on every read, including filtered results,
exports, history, reimports, and restores.

## Public cached map tiles

An eligible map release carries a versioned `map_artifact` object. It identifies
the release and profile, generation time, current suppression generation,
attribution, bounds, zoom range, immutable XYZ `.mvt` URL template, the sole
source layer (`uec_map`), feature schema version, per-tile SHA-256/ETag values,
and bounded cache policy. Fetch tile bytes from
`GET /api/v2/releases/{release_id}/map/tiles/{z}/{x}/{y}.mvt?profile={profile}`.
The route verifies the active release/profile, canonical manifest, current
suppression generation, and the requested tile checksum before returning MVT.
Manifest and tile responses use ETags and
`Cache-Control: public, max-age=0, must-revalidate`, so stored bytes can be
reused only after the current eligibility check succeeds. Tile properties are restricted to `feature_key`,
`kind`, `count`, `exact_count`, `coarse_count`, `next_zoom`, optional exact-leaf
`record_id`, and `category_key`; geometry carries location. Names, evidence,
addresses, and tokens are never tile properties. Server-side aggregation
provides low-zoom clusters; MapLibre native clustering is not applied to this
vector source. Exact and coarse leaves remain distinct. Coarse leaves are
uncertainty aggregates and never resolve as exact records. Unmapped records
remain list/search-only.

Tiles are release/profile scoped immutable artifacts and become available only
after promotion. A cached tile may be used for first paint only after the
client has confirmed that its release and suppression generation remain
eligible; stale cached bytes alone are not authorization to display a feature.
List and detail calls pin to the displayed release/profile, and current
suppression can make an old record return 404 or withdraw a release with 410.

List and detail metadata use the same coverage scope. Their source identifiers, source URL, retrieval timestamp, review state, release, and ruleset remain record-level provenance; they do not establish a story-wide denominator or an animal count. Narrative aggregate claims must come from a separately sourced, dated editorial ledger.

The current wire intentionally stops at the fields listed in
[v2-location.schema.json](v2-location.schema.json). It does not promise
evidence content hashes, source publication/effective dates or availability
status, geocoder provider/query/precision metadata, independent review-event
identifiers/scopes/dates/outcomes, or richer release-scoped approval metadata.
Those are tracked as explicit deferred gaps in the
[product convergence gap ledger](v2-product-convergence-gap-ledger.md), not
silently inferred from the current fields.
