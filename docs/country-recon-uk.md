# UK and country source reconnaissance

This is a read-only source assessment and private-artifact record, not source approval,
legal clearance, or publication authorization. Real artifacts remain under ignored
restricted staging. No pipeline code or public data was changed.

## V1 country set verified

The V1 `static_data` directory contains nine country codes with `locations.csv`:

| Code | Rows | Columns | Existing V1 source/processing evidence |
|---|---:|---:|---|
| ca | 1,323 | 100 | Ontario/federal CSVs and cleaners |
| de | 9,254 | 269 | BVL workflow comments and migration script |
| dk | 1,561 | 100 | Smiley XML and Danish converter history |
| es | 4,222 | 100 | legacy Spain CSV/converters |
| fr | 3,201 | 100 | legacy locations only in current checkout |
| mx | 14,836 | 101 | DENUE/aquaculture processing history |
| nz | 1,652 | 17 | bespoke source/process history |
| uk | 7,600 | 100 | `Old CSVs/uk-data.csv`, legacy converter |
| us | 7,101 | 269 | APHIS files/reports |

The user estimate of ten is not supported by the current V1 `static_data` inventory;
the verified count is nine. This is a code/data inventory, not a claim of complete
historical country coverage.

## Readiness matrix

| Source/country | Responsible body and canonical evidence | Type/coverage/refresh/format | Terms/privacy | Acquisition and adapter readiness | Blockers |
|---|---|---|---|---|---|
| UK England + Wales approved establishments | FSA catalogue and CSV: <https://www.data.gov.uk/dataset/2c80e0ce-ee1c-4f26-ba6f-1e1ae1bd8ee9/approved-food-establishments> | Animal-origin establishments under Reg. 853/2004; monthly snapshots; current catalogue entry dated 2026-09-01; CSV | Catalogue says UK OGL v3.0; 104 rows marked `AddressWithheld=Yes` in the private snapshot, so public field minimization/review remains required | Strong: direct CSV and stable application number; reuse BLtU positional/activity preservation pattern, with withheld-address suppression | England/Wales only; duplicate application identifiers observed; coordinate semantics and missingness need review; no automatic publication |
| UK Scotland approved establishments | FSS page: <https://www.foodstandards.gov.scot/open-data-portal/approved-establishments-in-scotland> | Scotland approvals; monthly; CSV; page published 2026-08/09 | Page states OGL v3; exact CSV terms and field-level privacy still require project review | Good separate adapter; source-specific schema and activity codes required | Separate authority/file; cannot merge with FSA without identity/schema review |
| UK Northern Ireland approved establishments | FSA data catalogue link from national entry: <https://data.food.gov.uk/catalog/datasets/dae35822-ca4e-41a2-b2af-b10b6163085a> | Separate NI approved-establishment source; format/update needs metadata inspection | Terms and privacy not yet verified in this reconnaissance | Unknown until metadata/resource inspection | Separate source and terms/coverage confirmation |
| UK FHRS/FHIS | FSA API: <https://api.ratings.food.gov.uk/help> | Food businesses and ratings across England, Scotland, Wales, NI; API JSON/XML; open data files nightly/daily; not limited to animal agriculture | FSA says OGL generally, but API terms/brand conditions apply; businesses can include small premises and potentially personal-address exposure | Technically strong API/open-data adapter; not interchangeable with approved-establishment source | Scope mismatch with facility map; privacy/minimization and local-authority coverage review |
| Canada | Legacy Ontario/federal artifacts; no current authoritative endpoint verified here | Partial, mixed federal/provincial; CSV | Unverified | Hold; existing cleaner is source-specific | Partial coverage, terms, coordinates |
| Denmark | Existing Smiley XML/V1 source | National food businesses; XML; current refresh/license not reassessed in this lane | Existing source review elsewhere; do not infer clearance | Existing adapter foundation | Terms/privacy/source freshness |
| Spain | MAPA REGA/SITRAN and regional derivatives assessed previously | National register privacy-restricted; regional open derivatives | National bulk reuse unresolved; regional licenses vary | Hold pending national/regional source selection | Access/coverage/license fragmentation |
| France | No authoritative current source evidence in V1 checkout | Legacy data only | Unverified | Hold | Provenance and terms |
| Mexico | INEGI DENUE-based historical processing | Legacy economic directory extract; source-specific | Existing historical claims need review | Hold | Current endpoint, scope, personal/address risk |
| New Zealand | Historical bespoke source/process | 17-column legacy file; 665 missing coordinates in prior inventory | Unverified | Hold | Source access/terms and completeness |
| United States | USDA APHIS historical files/reports | Source-specific wide schema and reports | Requires current terms/privacy review | Reference only | Not a clean expansion template |

## UK deeper assessment

The FSA England/Wales catalogue is the clearest near-term candidate: it names the
publisher, states OGL, provides dated monthly CSV snapshots, and separates Scotland
and Northern Ireland. The current private snapshot was acquired from the catalog-linked
official blob URL at 2026-09-14T02:47:04.5428766Z; its manifest records 1,774,417 bytes,
SHA-256 `d5cfec048b0f4dc4a8594b0597982f3788f10eb1b4270f9593ead8abce33b61f`, and an
effective snapshot date of 2026-09-01.

Private aggregate inspection found 5,342 rows and 71 columns, no missing application
numbers, 2,475 rows with both X/Y values, and 104 rows with `AddressWithheld=Yes`.
Duplicate application-number values were observed and require quarantine/identity
review; they must not be silently deduplicated. The file contains England, Wales,
Jersey, Isle of Man, and Guernsey values despite the catalogue's England/Wales title,
which requires a coverage decision before ingestion. No geocoding was performed.

Scotland is a good second UK source because FSS explicitly states monthly cadence,
CSV, and OGL v3. Northern Ireland remains metadata-first until its separate catalogue
resource and terms are inspected. FHRS/FHIS is technically highly automatable, with
documented JSON/XML API and nightly open-data files, but its broad food-business scope
and local-authority coverage make it a separate product/source decision rather than a
drop-in approved-establishment feed.

## Recommendation

1. Proceed first with an England/Wales FSA approved-establishment synthetic adapter and
   private restricted staging, using `AppNo` only as a candidate identifier after the
   duplicate review; preserve all source values, activity strings, withheld-address
   flags, source coordinates, and coverage values.
2. Add Scotland as the next candidate after inspecting its CSV schema and exact terms.
3. Keep Northern Ireland metadata-gated and do not represent the four UK feeds as one
   source until identity, coverage, update, terms, and suppression behavior are
   explicitly reconciled.

The FSA England/Wales source is a stronger near-term candidate than Spain's national
REGA for source clarity and automation, but it is not cleared for public release.
Human terms, privacy, safety, suppression, legal, data-quality, and publication gates
remain mandatory.

## Adapter reconciliation

The canonical implementation is `pipeline/sources/uk/fsa_approved/`. It supports
the existing synthetic contract and the observed monthly FSA CSV profile through
one adapter. Registered runs require source URL, retrieval UTC, checksum, and byte
size and fail closed before staging on missing or mismatched metadata. They preserve
source values, emit deterministic parsed/normalized/quarantined states, record
normalized-output checksums and schema fingerprints, and always use
`release_state=not-created` with a private-candidate publication state.

The monthly profile treats England and Wales as the current source scope and keeps
Northern Ireland as a separate future feed. It quarantines duplicate IDs within a
nation, unknown jurisdictions, malformed rows, missing activities, remarks and
address-risk rows; suppresses `AddressWithheld` addresses and coordinates; validates
X/Y as source longitude/latitude without geocoding; and reports aggregate coverage
and anomaly counts. The synthetic profile retains its authority/status/activity
vocabulary tests for the canonical composition contract.

This reconciliation is a design and test record, not source approval or legal
clearance. No live row data is included, and the private artifact remains outside
Git and public outputs.
