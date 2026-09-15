# Belgium source reconnaissance

Status: reconnaissance plus private/test-only adapter implementation. No real facility rows, names, addresses, contacts, coordinates, release, or publication are retained here. Synthetic fixtures contain no real operators.

Last checked: 2026-09-15 UTC under `docs/ETHICS.md`, policy version 1.0, last reviewed 2026-09-12. This is source-status evidence, not publication approval or a runtime-health claim.

The implementation is in [`pipeline/sources/belgium/`](../pipeline/sources/belgium/). It requires two independently preserved official artifacts: the operator CSV at `https://www.static.favv.be/bo-documents/inter_actieve_actoren_EN.csv` and the LAP/PAP codebook at `https://www.static.favv.be/bo-documents/inter_PAP_omschrijving_EN.csv`. The bounded assisted command is repeatable when a browser or authorized operator supplies both files:

```text
python -m pipeline.sources.belgium.refresh --operators <private/operators.csv> --activity-codes <private/inter_PAP_omschrijving_EN.csv> --run-dir <private/run> --retrieved-at-utc 2026-09-15T00:00:00Z
```

The codebook join is exact and deterministic; unresolved or ambiguous codes quarantine. The adapter preserves source activity text and distinguishes slaughter, cutting, processing, storage, animal-by-products, and export domains. It never geocodes and keeps source address/coordinate/enterprise values out of normalized/API-shaped rows. The live operator header was not obtainable in this environment, so the checked-in fixture is a schema contract and the first real capture must be reviewed for schema drift.

## Readiness

| Candidate | Evidence | Acquisition | Terms / privacy | Readiness / next action |
|---|---|---|---|---|
| FASFC operator list | Official [data.gov.be dataset](https://data.gov.be/en/datasets/favv-afsca-operators) and published [English CSV](https://www.static.favv.be/bo-documents/inter_actieve_actoren_EN.csv) verified | Published CSV route; bounded header retrieval timed out from the static host in this environment | CC Attribution 4.0; FASFC says attribute source and last-update date, do not imply FASFC affiliation/approval, and do not mislead | Candidate for a private adapter after header/schema capture, delimiter/encoding test, and category mapping |
| FASFC activity-code list | Official [data.gov.be dataset](https://data.gov.be/en/datasets/fasfc-activity-codes) and [English CSV](https://www.static.favv.be/bo-documents/inter_PAP_omschrijving_EN.csv) verified | In-memory bounded retrieval succeeded; bytes discarded | CC Attribution 4.0; weekly metadata on data.gov.be | Companion codebook; not a facility list and not sufficient by itself |
| EU-approved food-establishment PDF lists | Official [FASFC approved-establishments page](https://www.foodweb.favv-afsca.be/professionals/foodstuffs/establishments/default.asp) verified | PDF links are a separate publication surface | Scope and currentness differ from open-data CSV; PDF schema/version handling required | Useful cross-check only; do not merge with operator rows without explicit identity/version evidence |
| Animal by-products lists | Official [FASFC animal-by-products page](https://www.foodweb.favv-afsca.be/professionals/animalbyproducts/approvedoperators/) verified | Sectioned PDF lists | Separate legal scope under Regulation (EC) 1069/2009 | Keep separate from food slaughter/processing coverage |

## What the authoritative open-data files mean

The operator dataset describes enterprises and establishments that currently have an FASFC registration, approval, or authorization, with LAP/PAP activity codes, activity descriptions, and approval/authorization numbers. Data.gov.be reports identifier `favv-afsca-operators`, Belgium coverage, CSV format, weekly frequency, CC BY 4.0, and an update date of 2026-08-05 at the checked page revision.

The activity-code dataset is a codebook, not a location dataset. Its published description says codes are grouped by Place/Activity/Product and include linked approval codes. The fetched English CSV used 13 delimited header fields (accented labels redacted here), 395 non-empty data rows, and includes fields corresponding to PAP ID, place code/description, activity code/description, product code/description, approval form/code/description, language, and a currentness/date field. Preserve source labels and codes; do not infer slaughtering from broad food-sector categories.

The operator page does not establish that every row is a slaughterhouse. It covers all FASFC-regulated operators with a current registration, approval, or authorization, potentially including retail, restaurants, transport, storage, processing, feed, primary production, and other activities. Filtering must use the codebook and retain every original activity/category value. Slaughterhouses, cutting plants, processing plants, cold stores, animal-by-product facilities, exports, inspection outcomes, and aggregate statistics are separate concepts and must not be silently combined.

## Identity, geography, and privacy risks

The dataset description confirms enterprise/establishment scope and approval identifiers, but the operator CSV header was not captured in this reconnaissance. Address, postal-code, municipality, establishment-versus-enterprise identifiers, coordinates, effective dates, and status fields therefore remain unverified. Treat any address as a facility claim requiring source-field preservation and privacy screening; a registered office or mixed residential/business address is not automatically an operating site. Do not geocode until provider/query/time/precision/review metadata and the ETHICS.md residential/private-location rules are implemented.

Foodweb is an interactive lookup and inspection-results surface, not a bulk inspection dataset. Its published FAQ says inspection-result publication is limited to B2C operators and cannot produce a complete list by municipality or activity. It must not be used as a substitute for the operator master or treated as slaughterhouse evidence.

Coverage is Belgium-wide according to data.gov.be, but completeness is bounded by FASFC registrations/approvals/authorizations currently represented in that feed. It is not evidence of operating status beyond the publisher's stated current eligibility, nor a census of all animal-agriculture facilities.

## Acquisition provenance (private, no raw artifact retained)

The activity-code request was performed read-only in memory and response bytes were discarded. The operator request was attempted but did not yield bytes; no operator rows were retained.

| Artifact | Retrieval UTC | HTTP | Content type | Bytes | SHA-256 | Supplied update/effective date |
|---|---|---:|---|---:|---|---|
| `inter_PAP_omschrijving_EN.csv` | 2026-09-15T17:05:26.4902745Z | 200 | `text/csv` | 101,987 | `c50d5ff8db705664a56bef73aec88c94159ff7f810cf6125e978e0e16c5a0812` | data.gov.be page: 2026-08-05; no artifact-level effective date observed |
| `inter_actieve_actoren_EN.csv` | 2026-09-15; no response body | unavailable | unavailable | unavailable | unavailable | data.gov.be page: 2026-08-05 |

## Adapter readiness and recommended next step

Readiness: medium difficulty, not ready for implementation. The authoritative source pair and reuse terms are clear, and the activity codebook is machine-readable. The main work is schema capture for the operator CSV, deterministic delimiter/encoding handling, codebook versioning, establishment/enterprise identity semantics, multilingual labels, status/effective-date interpretation, and explicit mappings for slaughterhouse versus cutting/processing/storage and other PAP categories. Expect one operator row per activity or repeated establishment identifiers; this must be verified rather than assumed.

Next step: obtain an authorized, bounded operator-CSV retrieval; record its redirect chain, headers, byte size, SHA-256, supplied date, and sanitized schema; then build synthetic fixtures for repeated activities, missing identifiers, multilingual text, category ambiguity, and mixed residential/business addresses. Keep acquisition private and publication blocked pending human privacy and release review.
