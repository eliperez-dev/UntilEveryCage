# United States recovery packet

This packet is private pipeline documentation, not publication approval.

## Source boundaries

The facility-master candidate is USDA FSIS's [Meat, Poultry and Egg Product Inspection Directory](https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory) and its supplemental establishment-demographic CSV. FSIS describes the directory as a listing of FSIS-regulated meat, poultry, and egg establishments, with a weekly replacement edition and generalized activity categories. State meat-and-poultry inspection programs are not silently included. The source-local bundle adapter is documented in [`pipeline/sources/us/fsis/README.md`](../../../pipeline/sources/us/fsis/README.md): it joins only exact source-native IDs/numbers and keeps all acquired data private/test-only.

APHIS is a separate evidence family. The [Animal Care Public Search Tool](https://www.aphis.usda.gov/animal-care/awa-services/usda-animal-care-public-search-tool) exposes licensed/registered persons, inspection reports, and research facility annual reports. The [annual usage summary](https://direct.aphis.usda.gov/awa/research-facility-report/annual-summary) notes that annual reports can be amended. The adapters require an explicit `registrations`, `annual_reports`, or `inspections` profile, preserve certificate and customer-number variants, version explicit amendments, and never turn an APHIS row into an FSIS facility or laboratory master record.

## Acquisition boundary

FSIS direct links returned HTTP 403 during the prior reconnaissance. This sprint does not bypass that control. `pipeline.sources.us.fsis.refresh` provides a reproducible operator-assisted capture contract: an authorized operator saves one current directory CSV plus the demographic CSV shown on the official page, records the edition/date and final URL for each, and runs the private adapter. Direct fetch is available only with a terms-review JSON and the shared bounded acquisition primitive; HTML, login, 403, content-type, and schema failures remain fail-closed.

APHIS is UI-mediated. `pipeline.sources.us.aphis.refresh` records the selected profile, official route, query/export context, retrieval time, hash, byte size, source dates, and separate evidence type. `pipeline.sources.us.aphis.acquire` can fetch only a terms-reviewed URL for a documented download control; it rejects empty, malformed, HTML/challenge, truncated, and invalid-signature responses before committing bytes. No hidden endpoint automation is required.

### APHIS renewable capture

The supported operator workflow is:

1. Open the official APHIS Animal Care search/report page in an authorized browser session.
2. Select exactly one profile: `registrations`, `annual_reports`, or `inspections`. Preserve the selected year/date, amendment indicator, filters, displayed result count, final URL, and any linked report/document identifier. Do not combine profiles or edit the saved export.
3. Save the CSV export, or save a linked document/amendment separately. Documents are source evidence only and are not automatically merged into annual-report or inspection rows.
4. Run a private refresh. For a saved CSV:

```powershell
python -m pipeline.sources.us.aphis.refresh `
  --raw C:\path\to\authorized-private\aphis.csv `
  --run-dir data/staging/aphis/<run-id> `
  --profile annual_reports `
  --source-url "https://the-final-url-used-by-the-operator" `
  --effective-date 2025 `
  --query-context '{"selected_year":"2025","amended_reports_included":true,"displayed_result_count":"recorded-privately"}'
```

For a linked PDF/XLSX document or amendment, preserve it without parsing or release promotion:

```powershell
python -m pipeline.sources.us.aphis.acquire `
  --profile documents --raw C:\path\to\authorized-private\report.pdf `
  --run-dir data/staging/aphis-documents/<run-id> `
  --retrieved-at-utc 2026-09-18T00:00:00Z `
  --source-url "https://the-final-document-url"
```

`acquire` currently supports the documented-download route; the browser-assisted route is the normal fallback for UI exports. A direct fetch requires an approved terms record and a documented final download URL:

```powershell
python -m pipeline.sources.us.aphis.acquire `
  --profile annual_reports --terms-review data/restricted/aphis-terms-review.json `
  --source-url "https://the-documented-download-url" --output-root C:\path\to\authorized-private\data\raw `
  --run-id <unique-run-id> --query-context '{"selected_year":"2025","amended_reports_included":true}'
```

The fetch path writes `acquisition-metadata.json` and a row-free `manifest.json`; failures write `acquisition-failure.json` with the failure class, attempts, query context, and no committed artifact. Reuse a new run ID for every observation. A failed or empty capture must not replace or delete the previous validated artifact. All APHIS outputs remain restricted private research evidence, with `release_state=not-created`, `publication_state=private-research-evidence`, and `publication_gate=blocked` until separate human review and approval.

## Validation and handoff

Both adapters preserve source values only in restricted staging and emit parsed, normalized, quarantined, QA, run-status, health, and private candidate-handoff artifacts. They disable geocoding, mark address/coordinate review as pending, quarantine duplicate or missing identities, and set `release_state=not-created`, `publication_state=private-candidate`, and `publication_gate=blocked`. APHIS uses a source-specific test-only import packet rather than the facility importer: its `establishment_id` stays null, no graph candidates or edges are emitted, and no database release or public promotion is performed. The APHIS export is not a complete AWA or animal-use census; annual-report absence is not closure or non-use, and amendments/currentness require review.

## V1 reconciliation

[`v1-field-crosswalk.json`](v1-field-crosswalk.json) is the row-free inventory and field/category map. The checked-in FSIS V1 snapshot has 7,101 rows and 269 columns. Its slaughter and processing flags overlap, so the counts are field-presence observations rather than totals. Until an authorized current artifact exists, V1 rows are not claimed current and a missing current observation is `not-observed`, never closure.

## Accountability pilot

The private [FEC and corporate-identity graph reconnaissance](fec-corporate-identity-graph-recon.md)
documents official FEC, SEC EDGAR, IRS TEOS, SAM.gov, and state-registry
evidence families, their identifiers and access limits, and a conservative
event/matching/test contract. It does not authorize contribution-derived
facility links, automatic parent/subsidiary merges, or publication.

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
