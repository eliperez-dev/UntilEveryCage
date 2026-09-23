# Italy Ministry 853/2004 private source

`it.853-2004` is the Ministry of Health open-data catalog for establishments
recognized under Regulation (EC) 853/2004. The catalog page is the stable
authority boundary; `acquire.py` discovers its current same-origin CSV link,
archives the raw bytes under ignored `data/raw/italy/`, and records the
requested catalog URL, final download URL, retrieval time, response metadata,
SHA-256, byte size, supplied catalog/file dates, source ID, code/configuration
versions, and terms-review evidence. Network acquisition is bounded and
requires an approved private terms-review JSON file.

Run private acquisition and staging with:

```text
python -m pipeline.sources.italy.acquire --fetch --terms-review <review.json> --output-root data/raw --run-id <id>
python -m pipeline.sources.italy.refresh --raw data/raw/it.853-2004/<id>/source.csv --run-dir data/staging/italy-853/<id>
```

The refresh uses `run_private_lifecycle`, producing parsed, normalized,
quarantined, row-free QA, restricted run status, and deterministic private
health artifacts. It ends at `candidate-ready`; candidate import and guarded
test-only API checks are separate explicit steps. No release is promoted and
default/public visibility remains zero.

The adapter treats each establishment/activity row as an observation. It
preserves source values privately, retains source identifiers, represents
unknown dates/geography/coordinates explicitly, and quarantines malformed
rows, unknown statuses, missing identifiers/activity codes, invalid dates,
and repeated recognition/activity identities. Repeated rows are not merged.
Addresses, tax identifiers, and source coordinates are never copied into the
normalized public-shaped fields; any future coordinate or address use requires
separate privacy and project review.

## 1069/2009 boundary

The Ministry's animal-by-products catalog is a separate source with a separate
schema, recognition semantics, activity/product codes, and optional links to an
853 recognition number. It is not included in `it.853-2004`, its row counts,
identity rules, candidate release, health snapshot, or API filters. A
provisional `it.1069-2009` adapter now has its own source ID, synthetic fixture,
private manifest, and shared-runner registration. This establishes fixture
readiness only; the fixture is not an upstream edition. It accepts only the exact
synthetic CSV contract documented in `it_1069_adapter.py`; that contract is a
test seam, not a claim about the Ministry export. The parser preserves category
and activity codes separately, records status/date uncertainty, quarantines
malformed or repeated observation IDs, and fails closed on schema drift. Any
source-supplied 853 recognition number is kept only in private source values;
the normalized cross-source link remains unresolved. Source observation IDs
do not establish facility identity.

Preserved-artifact contract readiness requires an operator capture matching
that exact contract; live one-command E2E readiness is not established because
live acquisition is disabled. Use fixture mode for the checked-in synthetic
artifact or local-artifact mode for an operator-preserved artifact. A local
artifact requires a sibling `acquisition-metadata.json` with `source_url`,
`retrieved_at_utc`, `sha256`, `byte_size`, and an opaque
`terms_review_reference`; the digest and size are checked before parsing, and
row-free metadata is copied into the private run. Live acquisition is disabled.
Do not add upstream field mappings until an authorized preserved capture
supplies the actual schema, response/hash/date metadata,
status/category/activity codebooks, date semantics, and file-specific terms.
ABP category/activity observations remain separate from food approvals; no
counts, identities, or links are shared with 853/2004.

This is private staging evidence, not a completeness, accuracy, project-
approval, or publication claim. The catalog notes that some coordinates came
from OpenStreetMap contributors; that provenance does not itself authorize
precise-coordinate publication.

## Sprint 02 live handoff

The 2026-09-19 private refresh is recorded in
`data/manifests/italy-sprint02-20260919.json` and
`docs/reports/italy-sprint02-20260919.md`. The exact raw and staging paths are
restricted under the sprint's excluded private root; no row-level artifact is
tracked. The source run had 47,375 observations, 41,849 normalized rows, and
5,526 quarantined repeated recognition/activity observations. A registered
office is not supplied by this source: the source address is a recognized-
establishment location and is not treated as proof of current operation.

The preferred replay command is the `acquire.py --fetch` command above. If the
local Python TLS stack cannot negotiate the Ministry host, use the ordinary
HTTPS `curl.exe --http1.1 --tlsv1.2` catalog-then-discovered-CSV capture route
documented in the private handoff, preserving both response headers and the
catalog-discovered URL before running `refresh.py`. This is a transport
fallback only; it does not bypass access controls or change source scope.
