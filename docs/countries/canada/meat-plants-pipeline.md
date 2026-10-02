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
codes, animal class, names, and facility-location evidence. The normalized
private handoff preserves the facility address for later shared address
enrichment and preserves validated Ontario source coordinates; telephone and
other contact fields are not part of the geocoding query. Ontario publishes
latitude/longitude but does not specify positional accuracy, so those points
remain `source-provided` and are disclosed as approximate/unverified in the
private preview. Coordinate pairs must be complete, finite, nonzero, in global
bounds, and within the Ontario extent. Invalid pairs fall through to the
normalized address/locality enrichment path. No adapter calls an external
geocoder. Ontario plant-type labels derive conservative categories. CFIA's workbook uses numbered function columns
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
reference with no official sanction. Its search page showed a page-modified
date of 2023-09-18; the workbook itself provides no effective/publication date.
This does not establish current completeness. A bounded acquisition on
2026-10-01T03:54:16Z returned 572,928 bytes
(`d2f042a43e0dc72460c892c67b60e8d0cacf9a91bd85032862664a6deae0cfef`); the
response had no `Last-Modified` or `ETag`, and the workbook effective date was
unknown. It parsed as 874 rows: 858 accepted/listable and 16 quarantined (10
unknown function codes, 6 unsupported/missing activity). The 858 accepted
rows supplied no source coordinates and each had a street-address value.

An earlier result-page check recorded 891 establishments, but the currently
retrieved page view exposes only a blank search form and does not repeat that
total without a submitted search. Treat 891 as prior evidence, not a current
official count; the difference from 874 remains unresolved and the workbook
row count is not a completeness claim. The 2026 live run imported 858 private
graph candidates into a dedicated disposable database (0 rejected, 0 public
rows, no release created or promoted). It also staged a restricted queue for
858 unmapped accepted records; that temporary payload was removed after the
E2E. Provider/terms/privacy review remains pending; no geocoder request was
made and no coordinates were produced.

Lifecycle:

`bounded fetch or assisted capture -> immutable provenance -> parse/normalize ->
validate/quarantine -> private QA/health -> candidate handoff and shared
provider-neutral geocode queue for candidates without a usable source point ->
optional private import`. Reruns are
deterministic. Missing observations are not closure. Queue generation does not
call a geocoder. Current licence, attribution, redistribution, privacy,
function-code semantics, freshness, provider selection, and project approval
remain human gates.

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
