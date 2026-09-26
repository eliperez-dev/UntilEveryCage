# Local real-preview API

This development-only API reads the isolated `real_preview` schema. It is not a public V2 projection and it does not create release membership, review decisions, or publication approval. It is available only when the API starts in development mode with the preview explicitly enabled, a loopback bind, and a runtime preview token.

Every request requires `Host` and any `Origin` to use a loopback name or address, plus the `x-uec-dev-preview-token` header. The runtime token must be at least 32 characters. Responses include `Cache-Control: no-store`. The token must stay in process memory and must not be included in URLs or browser storage.

| Route | Purpose | Bounds |
| --- | --- | --- |
| `GET /dev/real-preview/locations` | Keyset page of explicitly marked source-scoped candidates, including unmapped candidates | `limit` defaults to 100, max 200; `cursor` is the prior opaque `candidate_id`; `q` searches allowlisted name, activity label/source, source name/ID, city, and postal code fields, truncated to 100 characters; optional `default_map_scope` filters `true`/`false` |
| `GET /dev/real-preview/viewport` | Keyset page of default-map-scope candidates with usable source or explicitly approximate display coordinates in a viewport | Required `west`, `south`, `east`, `north`; `limit` defaults to 300, max 500; `cursor` is the prior opaque `candidate_id` |
| `GET /dev/real-preview/map/tiles/{z}/{x}/{y}` | Server-generated, lightweight MapLibre vector tile | Zoom 0–14 and valid XYZ coordinates; optional source-scoped `source_id`; content type is `application/vnd.mapbox-vector-tile`; contains only opaque map keys, opaque cluster lineage, feature kind, count, coordinate treatment, expansion zoom, and geometry |
| `GET /dev/real-preview/map/references/{reference_key}` | Keyset page of candidates represented by an administrative MVT reference | `reference_key` is the opaque 32-character tile feature key; `limit` defaults to 100, max 200; optional cursor and source-scoped `source_id` |
| `GET /dev/real-preview/locations/{candidate_id}` | Candidate detail | Opaque UUID identifier |
| `GET /dev/real-preview/facets` | Candidate counts by source and location class | Aggregate only |
| `GET /dev/real-preview/counts` | Candidate totals by location class, default-map scope, and map visibility | Aggregate only |

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

The importer reads these optional values only from allowlisted normalized fields, never from `source_values`, source rows, or raw artifacts. Text is bounded and type-checked. A missing or unsafe value is represented as null. `default_map_scope` and `map_scope_reason` independently preserve source classification; out-of-default-scope candidates remain listable/searchable and are never viewport results. The route still requires the existing process opt-in, loopback binding, local `Host`/`Origin`, and token authentication, retains the active source/snapshot eligibility filters, and returns `Cache-Control: no-store`. No new field changes the public `/api/v2/*` projection, candidate review state, privacy state, release membership, or publication status.

Candidate rows are source-scoped groups derived only from each adapter's normalized stable source identity field. Every source observation remains stored separately; one deterministic representative per group is marked for candidate routes. No cross-source identity merge occurs. The Denmark source identity is its source establishment key; its default-map classification remains an independent boolean plus an optional safe reason.

The list, detail, facets, and counts routes use the newest source snapshot and retain source-scoped groups even when no usable location is available. Facets report each source and safe location class, split by `default_map_scope`; counts separately report listable candidates, map-scope candidates, out-of-default-map-scope candidates, unmapped candidates, and map-visible candidates. The existing Denmark classification states 565 records in default map scope and 58,112 accepted records outside that scope. These populations remain separate: the latter can be listed/searched and counted in the authenticated local preview, but are not default map points. This interface work does not assert a live Denmark refresh or readiness; fresh candidate rows require an enabled-source import. Counts are private preview aggregates, not approved facility or public release totals.

`numeric_source_coordinate` means a valid, non-zero source coordinate pair exists. Zero/zero and invalid/out-of-range pairs are unusable and stored with null coordinates; a source city/postal value may still provide coarse placement, otherwise the candidate is `unmapped_private_observation`. Coordinates with `source-provided` or `source-precision-unknown` precision are presented as approximate and remain pending human review; they are never described as exact. `city_postal` means the selected source group has city or postal placement and no usable coordinate pair; it has no source point coordinates. Unmapped groups remain in candidate routes but are never assigned map coordinates. Identifier syntax alone is never used to infer location or candidate class.

The importer verifies the selected normalized artifact against its manifest hash. The candidate projection version participates in the combined snapshot identity, so deploying this change creates a new immutable private snapshot from retained normalized inputs and safely reimports unmapped groups and map-scope flags; an idempotent replay of the old snapshot cannot mutate its rows. The retained preview root currently does not include the original source artifacts for hash re-verification; this limitation is reported in the aggregate-only importer result. This local preview does not establish source completeness, release eligibility, factual approval, privacy clearance, or publication readiness.

All pages are bounded and keyset ordered. Search uses only the persisted safe projection fields named above; it does not inspect source payload, address, or private notes. The map viewport always excludes candidates with `default_map_scope=false`, while list/search can include them or filter to either scope. There is no export endpoint. The public `/api/v2/*` contract is unchanged.

## Local map-tile projection

`/map/tiles` is a local-only MapLibre vector-tile projection, protected by the
same loopback and runtime-token gate as every other preview route. It is not a
candidate-detail API: properties are limited to an opaque stable `feature_key`,
an opaque `parent_key` for low-zoom cluster descendants, `kind`, `count`,
`precision`, and `next_zoom`. Names, addresses, source values,
city/postal labels, review notes, and raw payloads are never included.

The route selects only the latest retained snapshot per source. A valid optional
`source_id` is an ASCII lowercase source token (letters, digits, `.` and `-`, at
most 128 bytes); invalid selectors are rejected before database access.
Both the tile and reference-member queries require `default_map_scope=true`.
Out-of-scope candidates remain available to authenticated list/search/detail
routes, but cannot enter a default-map cluster or appear as a reference member.

Selecting a `city_reference` map feature may request its opaque `feature_key`
from `/map/references`. That authenticated, paginated response uses the normal
candidate envelope and the same latest-snapshot/source constraints as the tile.
It is the only path that returns members; a vector tile itself never contains
member IDs, names, or record details. The returned city/commune candidates keep
their `city_reference_approximate` treatment and are not reclassified as
facility points.

At zooms 0–9, numeric source coordinates and administrative references both
contribute to one deterministic WebMercator cluster hierarchy, server-side. At
zooms 10–14 numeric locations are lightweight individual source-coordinate
features, while city/commune references become independently visible
`city_reference` aggregates. A reference is never displayed as a facility pin:
its geometry is an approximate administrative reference centre and `count` is
the number of source-scoped candidates represented there. `next_zoom` is a
navigation hint, not a claim that an administrative reference resolves into
facility coordinates. Low-zoom grid-cluster features include `parent_key` when
their genuine parent exists at the preceding zoom. It is a deterministic opaque
lineage key only: clients may use it to animate a clicked parent into the
children actually returned at the next zoom, but it cannot reveal members.
