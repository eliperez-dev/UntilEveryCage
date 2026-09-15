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
2. Add Scotland as a restricted candidate after inspecting its CSV schema and exact terms.
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
and anomaly counts. Remarks remain a quarantine reason because their free text is
preserved in restricted source values and has not passed privacy review. The address
heuristic was narrowed after aggregate QA: generic facility-building words such as
`house`, `home`, and `lodge` are not sufficient by themselves, while explicit
residential or intermediary indicators remain review blockers. A monthly record not
flagged by that heuristic is still marked `privacy-review-required`; its normalized
coordinates remain suppressed until an authorized privacy decision. A heuristic pass
is not privacy clearance. The synthetic profile retains its authority/status/activity
vocabulary tests for the canonical composition contract.

### Aggregate-only monthly QA (2026-09-14)

The privately retained 2026-09-01 snapshot reproduced 5,342 input rows, 4,090
normalized rows, and 1,252 quarantined rows before the heuristic correction. The
sanitized reason matrix was:

| Reason | Rows | Interpretation | Action |
|---|---:|---|---|
| `remarks_present` | 999 | Short free-text source notes; 956 were under 40 characters; only 46 overlapped an address-risk hit | Keep quarantined pending privacy review |
| `address_privacy_risk` | 268 | 227 generic `house` hits, 25 `lodge`, 7 `home`, 8 `c/o`, and 3 `flat` hits; none had `AddressWithheld=Yes` | Narrow heuristic; retain explicit indicators for review |
| `unknown_nation` | 31 | Jersey, Isle of Man, or Guernsey rows outside the England/Wales profile | Keep quarantined; use separate source scope |
| `duplicate_id_within_nation` | 4 | Repeated application identifiers | Keep quarantined; never silently deduplicate |

This is an aggregate QA result, not source approval. The artifact, row-level values,
coordinates, and derived records remain restricted and were not committed or
published. The automated pipeline requirement remains end-to-end: acquisition,
checksum/metadata validation, parsing, quarantine, manifesting, and downstream
ingestion must be orchestrated before any release gate can open.

After the narrow heuristic correction, the same private artifact produced 4,300
normalized rows and 1,042 quarantined rows. The remaining address-risk count was
11; duplicate, unknown-jurisdiction, and remarks counts were unchanged. This
reduction is not a release decision: remarks, out-of-scope jurisdictions, and
duplicate identifiers remain blocked pending their respective reviews.

### Bounded real handoff (2026-09-14)

A deterministic private sample was staged from the retained 2026-09-01 artifact
for operator and importer-boundary validation. The sample contains 49 source rows:
20 England, 20 Wales, 5 Jersey, 3 Isle of Man, and 1 Guernsey. The source-local
handoff produced 29 normalized rows and 20 quarantined rows; quarantine reasons
were `remarks_present` (11) and `unknown_nation` (9). The pre-DB importer checks
loaded all 29 normalized rows and verified the raw and normalized checksums. The
same handoff was then imported into a disposable local PostGIS database: 29
candidate memberships, 0 default-visible rows, 29 pending privacy rows, 29
coordinate-review-required rows, and 0 geocode rows.

Restricted operator packet paths (not repository files):

- `data/restricted/country-recon/uk/runs/2026-09-14-bounded-real/selection.manifest.json`
- `data/restricted/country-recon/uk/runs/2026-09-14-bounded-real/handoff/manifest.json`
- `data/restricted/country-recon/uk/runs/2026-09-14-bounded-real/handoff/qa.json`

The packet records the official source URL/catalog, parent and sample hashes,
effective date, selection rule, coverage counts, quarantine counts, and disabled
geocoding. The sample and all row-level derivatives remain restricted. On the fresh
de98f73 disposable stack with migration 023, the guarded test-release list returned
29 pending/unmapped rows; detail, facets, and CSV returned successfully. The CSV
contained 29 rows and no raw/source-value fields. Every returned row carried
test-only/private/candidate metadata and null coordinates. A temporary append-only
privacy suppression event reduced the guarded list to 28 rows, then the disposable
stack was destroyed. Public V2 list remained empty and public CSV remained unavailable
because no promoted release exists. No approval, coordinate release, or publication
occurred. Operator decisions still required: source-rights/attribution review,
duplicate and coverage scope review, and privacy review of remarks and addresses.
The existing candidate-preview and public V2 gates were not relaxed. The shared
SourceArtifact/typed-run boundary remains a separate infrastructure integration
limitation; this source-local bridge validates typed artifact facts directly and does
not alter the common contract.

This reconciliation is a design and test record, not source approval or legal
clearance. No live row data is included, and the private artifact remains outside
Git and public outputs.

### Private lifecycle implementation status (2026-09-15)

The FSA England/Wales profile and the FSS Scotland profile now use the shared
bounded acquisition and private lifecycle seams. A network fetch requires an
operator terms-review record, is byte-bounded, and preserves requested/final URLs,
redirects, response headers, retrieval/effective metadata, hashes, byte size, and
code/configuration versions under ignored private storage. Both adapters emit
deterministic parsed/normalized/quarantined outputs, row-free QA, and private
source-health evidence. Activity categories are limited to slaughter, cutting,
processing, and logistics/storage; unknown activity text remains unresolved or
quarantined rather than guessed.

The FSA feed remains explicitly England/Wales in the monthly source profile;
Northern Ireland is retained as a separate source scope and is accepted only by
the synthetic contract until its distinct catalogue resource is independently
inspected. FSS is Scotland-only. Composition keeps source IDs, nation keys, and
identities separate and emits possible-match review signals without merging.
No release, promotion, public API/export exposure, or production acquisition is
authorized by this implementation.

### Bounded live-source validation (2026-09-15)

The explicitly authorized private fetches completed under ignored storage. The
following are aggregate validation results; no raw rows, addresses, coordinates,
or derived records are committed:

| Source/profile | Effective date | Bytes / SHA-256 | Input | Normalized | Quarantined |
| --- | --- | ---: | ---: | ---: | ---: |
| FSA monthly England/Wales profile | 2026-09-01 | 1,774,417 / `d5cfec048b0f4dc4a8594b0597982f3788f10eb1b4270f9593ead8abce33b61f` | 5,342 | 4,300 | 1,042 |
| FSS live Scotland export | 2026-08-11 | 245,871 / `b95b66afb112636c09f6de401054c7ea3d11e5058f34522d900c60435a125246` | 725 | 586 | 139 |

The FSA anomaly counts were 999 `remarks_present`, 31 `unknown_nation`, 11
`address_privacy_risk`, and 4 `duplicate_id_within_nation`. The FSS anomaly
counts were 125 `no_relevant_activity`, 18 `address_privacy_risk`, 2
`malformed_row`, 2 `missing_activity`, and 2 `missing_approval_number`.
Both runs emitted `health_state: private-validated`, `public_exposure: false`,
and import evidence with zero publication-eligible and zero default-visible
rows. Composition contained 4,886 source-preserving reviewable rows and created
no candidate release.

On a disposable PostGIS stack, both source manifests imported idempotently:
4,300 FSA rows and 586 FSS rows on first pass, zero rows on each rerun, 4,886
source records/observations/release members/review events, and zero
default-visible rows. The guarded test-only API returned list, detail, category
filter, cursor pagination, and facets successfully; public list returned zero
rows. The full 4,886-row test export was rejected by the bounded
`export_too_large` guard, while the existing small-candidate E2E covers a
successful private CSV response. The disposable database was destroyed after
validation.

### Repeatable refresh QA (2026-09-14)

The source-local refresh command was validated in aggregate-only dry-run mode against
the retained 2026-09-01 artifact. It recorded the official URL, retrieval timestamp,
effective date, SHA-256, byte size, code/config versions, 71-column schema
fingerprint, coverage, quarantine reasons, and release/publication gates. Results:
5,342 input rows, 4,300 normalized, 1,042 quarantined; anomaly counts were
`remarks_present` 999, `address_privacy_risk` 11, `unknown_nation` 31, and
`duplicate_id_within_nation` 4. No drift alarms were raised. The refresh report is
restricted at `data/restricted/country-recon/uk/runs/2026-09-14-refresh-check/refresh.json`.
Prior-run comparisons report disappeared identifiers as `not-observed`; they never
infer closure. The command keeps Scotland and Northern Ireland outside this source
profile and does not create a release.
