# France golden-country private review packet

Status: private candidate rehearsal complete; no release was created, promoted,
or published. This packet is an operator handoff, not project approval.

## Selection rationale

France is the strongest non-Denmark EU candidate in the current private
evidence. The 2026-09-16 private capture covers two distinct official DGAL
Regulation (EC) 853/2004 scopes: Section I domestic ungulates (1,448 input and
normalized rows) and Section II poultry/lagomorphs (1,068 input and normalized
rows), with zero quarantines in each snapshot. The scopes remain separate and
do not establish national completeness.

Italy has a stronger acquisition volume but is less ready for a golden-country
vertical: its 2026-09-16 853/2004 capture has 47,373 input rows, 41,847
normalized rows, and 5,526 quarantined repeated recognition/activity rows.
Those identity collisions require review before it can provide an equally
clean candidate handoff. Italy's 1069/2009 by-products catalog is also a
separate unimplemented scope.

## Lifecycle evidence

The focused disposable rehearsal is
`pipeline/tests/e2e/test_france_candidate_import.py`. It uses only sanitized
checked-in fixtures for executable coverage; it does not copy real private
rows into Git. The test runs both France sections through:

- preserved-artifact hash/byte provenance and source-local source IDs;
- parsing, normalization, explicit duplicate/missing-identity quarantine;
- rerun with a zero-change delta and no closure inference;
- source-local graph candidates with `review_required`, `private`, and
  `not_eligible` publication state;
- row-free operator packets and unpromoted candidate handoff manifests;
- disposable candidate import twice, with stable counts and zero default
  visibility;
- guarded test-release list/detail/facet/export API checks, including FR
  country identity, persistent test-only labeling, raw-field exclusion, and
  null geospatial output while coordinate review remains unresolved;
- append-only privacy suppression across list, detail, export, and public API.

The current aggregate private evidence is recorded in
`data/manifests/france-golden-country-private-2026-09-18.json`. Real raw
artifacts, addresses, coordinates, and normalized rows remain restricted and
ignored. The executable test's synthetic rows are not source evidence.

## Remaining gates

- confirm file-specific DGAL terms and attribution;
- review residential/mixed-use address risk, SIRET/name exposure, and any
  future coordinate enrichment;
- confirm the Section I/II category codebook and duplicate semantics;
- keep source disappearance as `not observed`, never closure;
- obtain authorized project review and release approval before any publication.

No human approval, current national completeness, factual certification, or
public availability is claimed.
