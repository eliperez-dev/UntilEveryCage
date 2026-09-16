# United States recovery packet

This packet is private pipeline documentation, not publication approval.

## Source boundaries

The facility-master candidate is USDA FSIS's [Meat, Poultry and Egg Product Inspection Directory](https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory) and its supplemental establishment-demographic CSV. FSIS describes the directory as a listing of FSIS-regulated meat, poultry, and egg establishments, with a weekly replacement edition and generalized activity categories. State meat-and-poultry inspection programs are not silently included.

APHIS is a separate evidence family. The [Animal Care Public Search Tool](https://www.aphis.usda.gov/animal-care/awa-services/usda-animal-care-public-search-tool) exposes licensed/registered persons, inspection reports, and research facility annual reports. The [annual usage summary](https://direct.aphis.usda.gov/awa/research-facility-report/annual-summary) notes that annual reports can be amended. The adapters require an explicit `registrations`, `annual_reports`, or `inspections` profile, and never turn an APHIS row into an FSIS facility or laboratory master record.

## Acquisition boundary

FSIS direct links returned HTTP 403 during the prior reconnaissance. This sprint does not bypass that control. `pipeline.sources.us.fsis.refresh` provides a reproducible operator-assisted capture contract: an authorized operator saves the current CSV export shown on the official page, records the edition/date and final URL, and runs the private adapter. Direct fetch is available only with a terms-review JSON and the shared bounded acquisition primitive; HTML, login, 403, content-type, and schema failures remain fail-closed.

APHIS is UI-mediated. `pipeline.sources.us.aphis.refresh` records the selected profile, official route, query/export context, retrieval time, hash, byte size, and separate evidence type. No hidden endpoint automation is required.

## Validation and handoff

Both adapters preserve source values only in restricted staging and emit parsed, normalized, quarantined, QA, run-status, health, and private candidate-handoff artifacts. They disable geocoding, mark address/coordinate review as pending, quarantine duplicate or missing identities, and set `release_state=not-created`, `publication_state=private-candidate`, and `publication_gate=blocked`. Candidate import remains limited to the disposable loopback database and existing test-only API path; no public promotion is performed by these commands.

## V1 reconciliation

[`v1-field-crosswalk.json`](v1-field-crosswalk.json) is the row-free inventory and field/category map. The checked-in FSIS V1 snapshot has 7,101 rows and 269 columns. Its slaughter and processing flags overlap, so the counts are field-presence observations rather than totals. Until an authorized current artifact exists, V1 rows are not claimed current and a missing current observation is `not-observed`, never closure.

## Review checklist

- authority, edition/effective date, URL, terms/attribution, and retention are recorded;
- source schema fingerprint and count changes are reviewed;
- FSIS, APHIS registrations, APHIS inspections, annual reports, laboratories, and aggregates remain separate;
- phone, DUNS, names, addresses, and precise coordinates receive privacy review;
- current coverage is compared with V1 only by exact source keys and aggregate reports;
- no raw artifact or row-level report is committed or exposed.
