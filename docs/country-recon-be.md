# Belgium source reconnaissance

Status: source reconnaissance, private adapter implementation, and strict live private E2E. The operator/codebook pair completed one live private run on 2026-09-24: 4,033 source observations and 1,793 source-scoped candidates. No real facility rows, names, addresses, contacts, coordinates, release, or publication are retained in Git. Synthetic fixtures contain no real operators; current status is in [source-status](source-status.md).

Last checked: 2026-09-17 UTC under `docs/ETHICS.md`, policy version 1.0, last reviewed 2026-09-12. This is source-status evidence, not publication approval or a runtime-health claim.

## Terms and private processing scope

The source catalogue indicates CC BY 4.0. A recorded operator decision permits
restricted private processing of the FASFC operator list and LAP/PAP codebook.
Any eventual public use requires carefully selected animal-related categories,
FASFC and latest-update attribution, no implication of FASFC endorsement,
minimization of possible natural-person fields, and counts that distinguish
activity observations from deduplicated candidates. This is an operator
authorization for private processing, not legal advice or a blanket rights or
publication clearance. The current public release remains blocked pending
source-specific category, privacy/safety, factual-review, and release decisions.

The implementation is in [`pipeline/sources/belgium/`](../pipeline/sources/belgium/). It requires two independently preserved official artifacts: the operator CSV at `https://www.static.favv.be/bo-documents/inter_actieve_actoren_EN.csv` and the LAP/PAP codebook at `https://www.static.favv.be/bo-documents/inter_PAP_omschrijving_EN.csv`. The bounded assisted command is repeatable when a browser or authorized operator supplies both files:

```text
python -m pipeline.sources.belgium.refresh --operators <private/operators.csv> --activity-codes <private/inter_PAP_omschrijving_EN.csv> --run-dir <private/run> --retrieved-at-utc 2026-09-15T00:00:00Z
```

The codebook join is exact and deterministic; unresolved or ambiguous codes quarantine. The adapter preserves source activity text and distinguishes slaughter, cutting, processing, storage, animal-by-products, and export domains. It never geocodes and keeps source address/coordinate/enterprise values out of normalized/API-shaped rows. The current live operator header is recorded as a cp1252, 20-column identifier/activity/location schema in the private run manifest; the checked-in fixture remains synthetic and no raw rows are committed.

## Readiness

| Candidate | Evidence | Acquisition | Terms / privacy | Readiness / next action |
|---|---|---|---|---|
| FASFC operator list | Official [data.gov.be dataset](https://data.gov.be/en/datasets/favv-afsca-operators) and published [English CSV](https://www.static.favv.be/bo-documents/inter_actieve_actoren_EN.csv) verified | 2026-09-17 normal HTTPS capture; cp1252, 20 columns, 87,903,986 bytes | CC Attribution 4.0; FASFC says attribute source and last-update date, do not imply FASFC affiliation/approval, and do not mislead | Private adapter validated; human terms/privacy/classification gates remain open |
| FASFC activity-code list | Official [data.gov.be dataset](https://data.gov.be/en/datasets/fasfc-activity-codes) and [English CSV](https://www.static.favv.be/bo-documents/inter_PAP_omschrijving_EN.csv) verified | 2026-09-17 normal HTTPS capture; cp1252, 13 columns, 101,987 bytes | CC Attribution 4.0; weekly metadata on data.gov.be | Companion codebook; not a facility list and not sufficient by itself |
| EU-approved food-establishment PDF lists | Official [FASFC approved-establishments page](https://www.foodweb.favv-afsca.be/professionals/foodstuffs/establishments/default.asp) verified | PDF links are a separate publication surface | Scope and currentness differ from open-data CSV; PDF schema/version handling required | Useful cross-check only; do not merge with operator rows without explicit identity/version evidence |
| Animal by-products lists | Official [FASFC animal-by-products page](https://www.foodweb.favv-afsca.be/professionals/animalbyproducts/approvedoperators/) verified | Sectioned PDF lists | Separate legal scope under Regulation (EC) 1069/2009 | Keep separate from food slaughter/processing coverage |

## What the authoritative open-data files mean

The operator dataset describes enterprises and establishments that currently have an FASFC registration, approval, or authorization, with LAP/PAP activity codes, activity descriptions, and approval/authorization numbers. Data.gov.be reports identifier `favv-afsca-operators`, Belgium coverage, CSV format, weekly frequency, CC BY 4.0, and an update date of 2026-08-05 at the checked page revision.

The activity-code dataset is a codebook, not a location dataset. Its published description says codes are grouped by Place/Activity/Product and include linked approval codes. The fetched English CSV used 13 delimited header fields (accented labels redacted here), 395 non-empty data rows, and includes fields corresponding to PAP ID, place code/description, activity code/description, product code/description, approval form/code/description, language, and a currentness/date field. Preserve source labels and codes; do not infer slaughtering from broad food-sector categories.

The operator page does not establish that every row is a slaughterhouse. It covers all FASFC-regulated operators with a current registration, approval, or authorization, potentially including retail, restaurants, transport, storage, processing, feed, primary production, and other activities. Filtering must use the codebook and retain every original activity/category value. Slaughterhouses, cutting plants, processing plants, cold stores, animal-by-product facilities, exports, inspection outcomes, and aggregate statistics are separate concepts and must not be silently combined.

## Identity, geography, and privacy risks

The captured operator CSV uses cp1252 CSV with 20 columns and 310,660 data rows. It supplies operator/location identifiers, PAP activity fields, postal code, municipality, province, approval number, and dates, but no establishment-name or street-address column. The adapter records `name_state=not-supplied-by-source` and never invents a name. Treat any postal or municipality value as a facility claim requiring source-field preservation and privacy screening; a registered office or mixed residential/business address is not automatically an operating site. Do not geocode until provider/query/time/precision/review metadata and the ETHICS.md residential/private-location rules are implemented.

Foodweb is an interactive lookup and inspection-results surface, not a bulk inspection dataset. Its published FAQ says inspection-result publication is limited to B2C operators and cannot produce a complete list by municipality or activity. It must not be used as a substitute for the operator master or treated as slaughterhouse evidence.

Coverage is Belgium-wide according to data.gov.be, but completeness is bounded by FASFC registrations/approvals/authorizations currently represented in that feed. It is not evidence of operating status beyond the publisher's stated current eligibility, nor a census of all animal-agriculture facilities.

## Acquisition provenance (private, no raw artifact retained in Git)

The current pair was fetched over normal HTTPS from the official static host into ignored private storage. The row-free sidecars preserve response headers, catalog update date, byte size, SHA-256, and schema fingerprints; no raw rows are checked in.

| Artifact | Retrieval UTC | HTTP | Content type | Bytes | SHA-256 | Supplied update/effective date |
|---|---|---:|---|---:|---|---|
| `inter_PAP_omschrijving_EN.csv` | 2026-09-15T17:05:26.4902745Z | 200 | `text/csv` | 101,987 | `c50d5ff8db705664a56bef73aec88c94159ff7f810cf6125e978e0e16c5a0812` | data.gov.be page: 2026-08-05; no artifact-level effective date observed |
| `inter_actieve_actoren_EN.csv` | 2026-09-17T20:20:48Z | 200 | `text/csv` | 87,903,986 | `9df1a9626cfbe30229f509e3004abbc291bd5b2aac3cd7437d96cceb124ffbb4` | data.gov.be page: 2026-08-05; source last-modified 2026-09-14 |

## Adapter readiness and recommended next step

Readiness: private adapter validated against the current pair, not ready for publication. The authoritative source pair and reuse terms are clear, and the activity codebook is machine-readable. The live operator schema is now recorded as cp1252 CSV with 20 columns; repeated location/activity identifiers are retained as distinct source observations, while five exact duplicate rows and 15 unresolved activity codes are quarantined. The private run produced 310,660 input rows, 310,640 normalized rows, and 20 quarantined rows. Human terms/attribution, privacy, classification, and project approval gates remain open.

Next step: obtain human confirmation of attribution/privacy/reuse and review the current candidate classifications. Keep the private artifacts restricted and publication blocked; build additional synthetic regression fixtures for repeated activities, missing identifiers, multilingual text, category ambiguity, and mixed residential/business addresses.

The source-scoped Belgium private preview can be refreshed with `python scripts/real_preview.py refresh --source be.locations`.
