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
derive conservative categories; CFIA function codes derive slaughter, cutting,
processing, and storage only for recognized codes. Unknown federal codes,
missing identifiers/names, duplicate source rows, inconsistent columns, and
schema drift fail closed or quarantine without silent merging.

Lifecycle:

`bounded fetch or assisted capture -> immutable provenance -> parse/normalize ->
validate/quarantine -> private QA/health -> operator review packet -> candidate
handoff`. Reruns are deterministic. Missing observations are not closure. No
geocoding is performed. Current licence, attribution, redistribution, privacy,
function-code semantics, freshness, and project approval remain human gates.

The adapter also emits row-level graph candidates into the private run. Every
accepted row gets a source-scoped facility node keyed by its source
establishment number and a supported operation claim. CFIA rows with an
explicit operator field additionally get operator and federal-registry
regulator edges; Ontario's plant-name field is never guessed to be an operator.
These graph candidates remain `review_required`, private, and not eligible for
publication, with no universal identity or cross-source merge assertion.

Run with `python -m pipeline.sources.canada.refresh --source ontario --raw <restricted.csv> --run-dir <restricted-run>` or `--source cfia --fetch --terms-review <approved-terms.json>`. Keep federal and provincial candidate releases separate.
