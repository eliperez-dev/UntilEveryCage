# Canada federal/provincial private meat-plant pipelines

Status: implemented private candidate pipelines; no release or public API exposure.

The source registry keeps Ontario and CFIA as separate identities. Ontario is
the verified Government of Ontario provincially licensed meat-plant dataset and
is Ontario-only. CFIA is the federal registry download for federally registered
meat establishments and licensed operators. Neither source is a complete
Canada-wide facility register, and the CFIA export-eligibility lists are not
substituted for the federal registry.

Both sources use the same compact adapter contract while retaining jurisdiction
level, jurisdiction name, plant/registration number, source activity/function
codes, animal class, names, contact fields, addresses, and coordinates in
restricted source values. Normalized candidate fields suppress street address,
phone, and coordinates behind privacy/review gates. Ontario plant-type labels
derive conservative categories. CFIA's workbook uses numbered function columns
whose suffix values are defined by the key on its results page, rather than
combined numeric codes:

| Workbook fields | CFIA function key | Candidate interpretation |
| --- | --- | --- |
| `CODES_1` | 1 slaughter species and i/j ritual slaughter | slaughter |
| `CODES_2`, `CODES_3`, `CODES_6` | 2 canning, 3 boning/cutting, 6 other processing; f/x/g are species subcodes | processing, cutting, processing |
| `CODE_4`, `CODE_5`, `CODE_8`, `TRICHINA` | 4 edible rendering, 5 casing preparation, 8 inedible rendering, 12 trichina treatment | processing |
| `CODE_7`, `CODES_10` | 7 packaging/labelling/storing, 10 storage only (A cold, B dry) | logistics and storage |
| `CODES_9` | 9 detained/imported-product inspection | recognized but does not by itself establish a production activity |
| `EXPORT` | 11 destination-market eligibility | retained as source evidence; never treated as a facility operation |

Unknown suffixes quarantine the row. Inspection-only rows without a supported
production/storage activity remain private quarantined evidence and do not
enter the candidate set. Missing identifiers/names, duplicate source rows,
inconsistent columns, and schema drift fail closed or quarantine without
silent merging. The linked CFIA list states its consolidation is a convenience
reference with no official sanction and was last updated 2023-12-04; this does
not establish current completeness. The private preview does not geocode or
derive points from addresses, and these source rows have no coordinates.
The official result page currently reports 891 establishments, while the live
download artifact parsed as 874 nonblank workbook rows. This discrepancy is
unresolved; the download count is an artifact count, not a completeness claim.

Lifecycle:

`bounded fetch or assisted capture -> immutable provenance -> parse/normalize ->
validate/quarantine -> private QA/health -> operator review packet -> candidate
handoff`. Reruns are deterministic. Missing observations are not closure. No
geocoding is performed. Current licence, attribution, redistribution, privacy,
function-code semantics, freshness, and project approval remain human gates.

For the one-time CFIA private E2E, the operator-scoped terms record is
[`../../../data/terms-reviews/ca.cfia.federal-meat.json`](../../../data/terms-reviews/ca.cfia.federal-meat.json).
It permits only bounded retrieval and private preview under Canada's
non-commercial reproduction terms; it is not a public-release approval.

The adapter also emits row-level graph candidates into the private run. Every
accepted row gets a source-scoped facility node keyed by its source
establishment number and a supported operation claim. CFIA rows with an
explicit operator field additionally get operator and federal-registry
regulator edges; Ontario's plant-name field is never guessed to be an operator.
These graph candidates remain `review_required`, private, and not eligible for
publication, with no universal identity or cross-source merge assertion.

Run with `python -m pipeline.sources.canada.refresh --source ontario --raw <restricted.csv> --run-dir <restricted-run>` or `--source cfia --fetch --terms-review <approved-terms.json>`. Keep federal and provincial candidate releases separate.
