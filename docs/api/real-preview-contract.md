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

Candidate objects contain an opaque preview ID, source ID, location class, country code, optional city and postal code, coordinate values only for numeric source-coordinate candidates, and the documented coordinate precision. Coordinate review is reported as pending human privacy review; factual review is not reviewed and privacy screening is pending. They never contain source identifiers, raw source values, full addresses, geocoder queries, private notes, release IDs, or approval claims. Every object is labeled as private and not project-approved or published.

`numeric_source_coordinate` means the source row contains a valid coordinate pair and an explicitly supported numeric precision value. `city_postal` means the source row has city or postal placement and an explicitly coarse precision value; it has no point coordinates. Rows without those fields remain private observations and are excluded from candidate routes. Candidate inclusion requires an explicit `facility_candidate: true` source-row flag; identifier syntax is never used to infer a location or candidate class.

All pages are bounded and keyset ordered. There is no export endpoint. The public `/api/v2/*` contract is unchanged.
