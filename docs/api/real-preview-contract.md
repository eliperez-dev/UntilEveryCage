# Local real-preview API

This development-only API reads the isolated `real_preview` schema. It is not a public V2 projection and it does not create release membership, review decisions, or publication approval. It is available only when the API starts in development mode with the preview explicitly enabled, a loopback bind, and a runtime preview token.

Every request requires `Host` and any `Origin` to use a loopback name or address, plus the `x-uec-dev-preview-token` header. The runtime token must be at least 32 characters. Responses include `Cache-Control: no-store`. The token must stay in process memory and must not be included in URLs or browser storage.

| Route | Purpose | Bounds |
| --- | --- | --- |
| `GET /dev/real-preview/locations` | Keyset page of explicitly marked source-scoped facility candidates with numeric or city/postal placement | `limit` defaults to 100, max 200; `cursor` is the prior opaque `candidate_id`; optional `q` searches only city and postal code, truncated to 100 characters |
| `GET /dev/real-preview/viewport` | Keyset page of numeric source-coordinate candidates in a viewport | Required `west`, `south`, `east`, `north`; `limit` defaults to 300, max 500; `cursor` is the prior opaque `candidate_id` |
| `GET /dev/real-preview/locations/{candidate_id}` | Candidate detail | Opaque UUID identifier |
| `GET /dev/real-preview/facets` | Candidate counts by source and location class | Aggregate only |
| `GET /dev/real-preview/counts` | Candidate totals by numeric and city/postal placement | Aggregate only |

Candidate objects contain an opaque preview ID, source ID, location class, country code, optional city and postal code, coordinate values only for numeric source-coordinate candidates, and the documented coordinate precision. Coordinate review is reported as pending human privacy review; factual review is not reviewed and privacy screening is pending. They never contain upstream source keys, raw source values, full addresses, geocoder queries, private notes, release IDs, or approval claims. Every object is labeled as private and not project-approved or published.

Candidate list, viewport, and detail objects also include the following display and provenance fields:

| Field | Semantics |
| --- | --- |
| `display_name` | A short normalized name, populated only when the row's normalized `privacy_gate` explicitly says `eligible`, `privacy-cleared`, `passed`, `clear`, or `public-eligible`. Missing or any other gate value suppresses it. It is not an approval or publication decision. |
| `activity_label` | A short string selected from allowlisted normalized source activity fields (`source_activity`, `activity_description`, `activity_label`, or simple string members of the activity lists). It is source-supplied wording, not a project classification. |
| `activity_source` | `source` when an activity label is present; otherwise null. |
| `source_name` | Maintained human-readable label for the allowlisted `source_id`. |
| `source_record_id` | The generated opaque `candidate_id` UUID. It is stable only for that imported candidate snapshot and never exposes an upstream record key. |
| `source_url` | Retrieval URL from the matching source manifest, returned only when it parses as an HTTPS URI without credentials. Otherwise null. |
| `source_record_url` | Optional normalized record link, returned only when it is HTTPS, has no credentials, query, or fragment, and passes the bounded string check. Current imported source contracts do not supply this field, so it is null unless a future source explicitly allowlists it. |
| `retrieved_at` | The acquisition timestamp from the matching source manifest. A candidate without a matching manifest is omitted; this is not the observation date. |
| `observed_at` | A timezone-aware source observation date from the normalized record (`source_observed_at`, `observed_at`, or `observation_date`); invalid, naive, or unavailable dates become null. |
| `evidence_summary` | Optional short normalized summary, only when that field is explicitly allowlisted for the source. It does not copy source payloads or notes; currently unavailable summaries are null. |

The importer reads these optional values only from allowlisted normalized fields, never from `source_values`, source rows, or raw artifacts. Text is bounded and type-checked. A missing or unsafe value is represented as null. The route still requires the existing process opt-in, loopback binding, local `Host`/`Origin`, and token authentication, retains the active source/snapshot eligibility filters, and returns `Cache-Control: no-store`. No new field changes the public `/api/v2/*` projection, candidate review state, privacy state, release membership, or publication status.

Candidate rows are source-scoped groups derived only from the normalized source identity fields: France `establishment_id`/`recognition_number`, Italy `recognition_number`, and FSIS `establishment_number`. Every source observation remains stored separately; one deterministic representative per group is marked for candidate routes. No cross-source identity merge occurs. France's 233 exact cross-section overlap signals remain separate candidate groups; the row-free France union metric subtracts those signals for comparison only.

The API counts retain all 35,073 source-scoped groups: 31,504 usable coordinate groups and 3,569 city/postal groups. The separate union comparison is 34,840 groups (31,504 numeric and 3,336 city/postal) after subtracting the 233 France overlap signals; API storage and candidate routes do not subtract them.

`numeric_source_coordinate` means a valid, non-zero source coordinate pair exists. Zero/zero and invalid/out-of-range pairs are unusable and stored with null coordinates; a source city/postal value may still provide coarse placement, otherwise the observation is unmapped. The aggregate reports 31,504 usable coordinate groups and 486 rejected zero-coordinate groups (Italy); the 486 rejected groups have city values and are counted as city/postal placement, not map points. Coordinates with `source-provided` or `source-precision-unknown` precision are presented as approximate and remain pending human review; they are never described as exact. `city_postal` means the selected source group has city or postal placement and no usable coordinate pair; it has no point coordinates. Rows or groups without usable placement remain private observations and are excluded from candidate routes. Identifier syntax alone is never used to infer location or candidate class.

The importer verifies the selected normalized artifact against its manifest hash. The retained preview root currently does not include the original source artifacts for hash re-verification; this limitation is reported in the aggregate-only importer result. This local preview does not establish source completeness, release eligibility, factual approval, privacy clearance, or publication readiness.

All pages are bounded and keyset ordered. There is no export endpoint. The public `/api/v2/*` contract is unchanged.
