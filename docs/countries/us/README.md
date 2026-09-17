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

## Accountability pilot

The private accountability pilot in
[`pipeline/sources/us/accountability`](../../../pipeline/sources/us/accountability/README.md)
adds a deterministic, graph-foundation-compatible link ledger. It starts from
FSIS establishment/approval IDs and the modeled APHIS registration/inspection
IDs, while keeping operators, legal entities, parents, brands, inspections,
violations, enforcements, laboratories, and aggregate observations distinct.
It accepts only exact source IDs or explicit reviewed link events. Ambiguous,
stale, conflicting, overlapping-ownership, and suppressed relationships are
quarantined. The checked-in fixture is synthetic/sanitized, private/test-only,
and does not add a graph migration or public release.

## Legacy real-data V2 and graph rehearsal

Run `python -m pipeline.scripts.maintenance.rehearse_us_real --root . --output data/manifests/us-real-legacy-graph-rehearsal-2026-09-17.json --private-dir data/graph-rehearsal/us-real-20260917` to replay the checked-in V1-derived US snapshots through the typed FSIS and APHIS private lifecycle contracts and build a private graph ledger. The rehearsal keeps FSIS federal facility/establishment-approval evidence separate from APHIS inspection and annual-report evidence, emits regulator edges only from source scope, and never joins across FSIS and APHIS by name, address, phone, or coordinates. All output rows remain ignored private staging; the checked-in manifest is aggregate-only.

The 2026-09-17 rehearsal measured 7,101 FSIS rows, 4,507 APHIS inspection rows, and 1,013 APHIS annual-report rows. It produced 25,238 explicit source-local ledger assertions; 2,664 survived the stale/retrieval safety checks and 22,574 were quarantined for review. These are candidate and queue counts, not accuracy, ownership, operating-status, approval, or publication claims. State inspection programs remain excluded.

The current FSIS page was observed in a normal browser with a September 14, 2026 update and three CSV routes, but the exact file routes returned HTTP 403 to bounded direct acquisition. See the row-free [current-route manifest](../../../data/manifests/us-fsis-current-route-2026-09-17.json).

## Review checklist

- authority, edition/effective date, URL, terms/attribution, and retention are recorded;
- source schema fingerprint and count changes are reviewed;
- FSIS, APHIS registrations, APHIS inspections, annual reports, laboratories, and aggregates remain separate;
- phone, DUNS, names, addresses, and precise coordinates receive privacy review;
- current coverage is compared with V1 only by exact source keys and aggregate reports;
- no raw artifact or row-level report is committed or exposed.
