# Italy Sprint 02 private handoff

This row-free report records the lane-5 private candidate refresh completed on
2026-09-19. It is not a release, factual approval, completeness claim, or
redistribution clearance.

## Frozen source and scope

- Source ID: `it.853-2004`.
- Official boundary: Italian Ministry of Health catalog for establishments
  recognized under Regulation (EC) 853/2004.
- Catalog: `https://www.dati.salute.gov.it/it/dataset/stabilimenti-italiani-gli-alimenti-di-origine-animale/`.
- Download observed: dated `STAB_POA_8_20260919.csv`.
- Separate `it.1069-2009` by-products data was not acquired or unioned.

## Acquisition evidence

The retained source is 49,940,074 bytes with SHA-256
`06c853fea232bd692e101d3c0b1b660d92ff80f56b2421bdd9e9746b01189dd8`.
The catalog artifact hash is
`1db2f27a54a1b54a51295da027624baf94f853afb5d05a2d310177b3af2cdcdf`.
The catalog supplied `2026-09-19` as its last-updated date and the filename
supplied the same publication-date signal. Retrieval was recorded at
`2026-09-19T18:00:29Z`.

The private run directory name `20260919T000000Z-live` is a deterministic
operator label only; it is not used as the retrieval timestamp. The private
acquisition metadata records the catalog response at `18:00:07Z`, the CSV
response at `18:00:29Z`, and an audit event documenting this distinction.

The repository's Python urllib route encountered a TLS handshake failure. The
same official catalog-discovered URL was acquired with ordinary `curl.exe`
HTTPS (`--http1.1 --tlsv1.2`), preserving catalog and source response headers.
No challenge bypass, paid service, or alternate source was used.

## Candidate and review boundary

The private lifecycle reconciles 47,375 source observations into 41,849
normalized observations and 5,526 quarantined rows. Every quarantine reason
was `ambiguous_repeated_recognition_activity`; repeated recognition/activity
observations remain occurrence-qualified and are not merged. Accepted rows
form 25,316 provisional source-recognition groups, not canonical facilities.

The source supplies a recognized-establishment location, not a legal
registered office. The adapter now carries that distinction explicitly:
registered location is `not-supplied-by-source`, and the establishment address
remains restricted source evidence rather than proof of current operation.
Source categories and activity codes remain preserved diagnostics. Geocoding is
disabled; coordinates remain source-value-pending-review. Address, tax,
coordinate, privacy, rights, project-approval, and publication gates remain
closed.

## Private handoff and replay

Exact restricted paths, safe hashes/counts, and replay commands are recorded in
`data/manifests/italy-sprint02-20260919.json`. The private handoff is under
`C:\New Projects\UntilEveryCage\.private\sprint02-20260919\italy`; no raw or
row-level artifact is tracked in Git or included in this report.

Checks run: `python -m unittest pipeline.sources.italy.test_acquire
pipeline.sources.italy.test_it_853_adapter` (15 tests, pass), live catalog and
CSV hash verification, private lifecycle replay, candidate handoff, row-free
review packet, private health report, and graph-candidate manifest.
