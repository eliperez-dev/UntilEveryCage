# Denmark private review packet

As of 2026-09-15, `dk.smiley` has a private, deterministic staging path. It is not a release approval or a completeness claim.

- Terms/licensing: the Find Smiley data page indicates attribution and currentness conditions; a named project release decision remains open.
- Privacy: addresses and source coordinates require residential/private-location screening. Geocoding is an enrichment and remains separately review-gated.
- Completeness: coverage is limited to records available in Find Smiley; the publisher supplies no dataset effective date and the result is not a census.
- Classification: source category and source key mappings must remain explicit; unknown or ambiguous values quarantine.
- Coverage/lifecycle: source disappearance is `not-observed`, never closure. Candidate import and guarded API checks must remain disposable/test-only.

Evidence: `pipeline/sources/denmark/`, `pipeline/contracts/source_health.py`, and `docs/countries/denmark/denmark-data-flow.md`.

The bounded release lane and current row-free evidence are recorded in
[`docs/reviewed-demonstration-release.md`](reviewed-demonstration-release.md)
and [`data/manifests/reviewed-demonstration-release-2026-09-17.json`](../data/manifests/reviewed-demonstration-release-2026-09-17.json).
That evidence records no public rows and does not represent a release approval.
