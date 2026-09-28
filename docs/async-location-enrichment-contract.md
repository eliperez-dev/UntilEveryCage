# Async local location enrichment contract

Acquisition and enrichment are separate operations. `real_preview.py refresh --source …`
imports a source snapshot and may classify/enqueue, but it must not call a geocoder
or wait for enrichment. Operators import reviewed administrative reference data
with `real_preview.py import-location-references`; then run
`real_preview.py enrich-locations --source ID --limit N` (or `--all`).
`geospatial-status` returns aggregate states/reasons only and must not expose
queries, addresses, coordinates, or source-record keys.

Country lanes provide stable normalized administrative codes only when their
source contract and privacy policy allow it. Catalonia's register contains
five-digit INE and six-digit Idescat municipality codes; `municipality_code`
preserves either source value verbatim. The reviewed ICGC-sourced Generalitat
dataset `wpyq-we8x` contains both codes and the official representative point
for each capital locality. Its coordinates are from ICGC's Base municipal de
Catalunya 1:5.000 v2.1 and represent the central point of each municipality
capital, not a municipality centroid or establishment point. Matching is by
exact source code only; no truncation, padding, alias inference, or name
matching is allowed. The data was last updated 2024-11-27; cite ICGC and that
date under the Generalitat open-data reuse conditions. Missing/ambiguous
reference matches remain unresolved/conflict. Display evidence carries
`locality_reference_coarse` precision and says “not facility coordinates”. No
source observation is updated, no source address/name/coordinate is used, and
no external provider request is made. These locality-only Catalonia candidates
remain list/search/detail discoverable but are explicitly outside default map
scope; a representative locality point must not imply a facility location.

For ICGC's `wpyq-we8x` dataset, `--reference-file` is the untouched official
CSV export. The importer checks the schema, exact five- and six-digit code
fields, coordinate bounds, and unique codes; it stores both the source-artifact
SHA-256 and the normalized reference projection SHA-256 with each immutable
reference row. The file must be acquired and reviewed before import; no
candidate data is part of this interface. Example invocation:

```powershell
python scripts/real_preview.py import-location-references `
  --reference-file .\reviewed-icgc-capital-localities.csv `
  --reference-source-id es.cat.icgc.municipality-capital-localities `
  --reference-source-url 'https://analisi.transparenciacatalunya.cat/api/v3/views/wpyq-we8x/export.csv?accessType=DOWNLOAD' `
  --reference-dataset-date 2024-11-27
python scripts/real_preview.py enrich-locations --source es.cat.feed-sandach --limit 1000
python scripts/real_preview.py geospatial-status --source es.cat.feed-sandach
```

The generic country-lane handoff contract is therefore: preserve a stable
allowlisted admin code in the normalized candidate projection; supply no raw
address or source geometry to this resolver; consume aggregate outcomes and
render only the explicit approximate precision/provenance.
