# FSA approved establishments

This adapter supports the pinned synthetic contract and the observed monthly FSA
CSV profile. The monthly profile requires a recorded SourceArtifact and validates
the AppNo, TradingName, Country, CompetentAuthority, X, Y, AddressWithheld, and
activity headers before staging. FSS Scotland and Northern Ireland remain separate
source feeds; they are not merged into this capability.

Source values and identifiers are preserved. Duplicate IDs are quarantined within
nation, unknown jurisdictions are quarantined, and malformed rows, missing or
unresolved activity, remarks, authority mismatches, and address-risk values remain
explicit review outcomes. Remarks remain quarantined because their free text is
retained in restricted source values and has not passed privacy review. Address
privacy heuristics intentionally exclude generic facility-building names such as
"house", "home", and "lodge"; explicit residential or intermediary indicators
still require review. `AddressWithheld=Yes` emits no address or coordinate
evidence. Non-withheld X/Y values are preserved only as raw source axes with
unverified CRS and precision; they are neither interpreted as longitude/latitude
nor displayed. Monthly normalized coordinates remain null behind an explicit
`privacy-review-required` gate even when no heuristic address-risk token is
present. A heuristic pass is not privacy clearance. Registered runs
write deterministic parsed, normalized, and quarantined states with a manifest
whose `release_state` is always `not-created` and whose publication state is
private-candidate.

The source-local refresh command provides the repeatable acquisition boundary. It
can fetch the configured official URL or accept a preserved raw artifact. Network
fetches require a terms-review JSON and use the shared bounded acquisition
primitive, recording requested/final URLs, redirects, response headers,
URL/retrieval/effective dates, hash, byte size, code/config versions, schema
fingerprint, coverage, counts, and quarantine reasons. It also runs the shared
lifecycle and emits row-free QA/source-health evidence. Dry-run is the default;
`--mode handoff` additionally emits the private candidate-handoff contract. A
changed header fingerprint or substantial unbounded count change raises a drift
alarm and blocks handoff. A comparison with a prior normalized run reports
disappeared identifiers as `not-observed`, never as closure. `--bounded-sample`
is only for explicitly labeled private test samples.

Before a registered or fetched run, maintainers must verify the current official
URL, effective/publication date, ownership, terms/licence, attribution, rate limits,
retention/removal rules, and redistribution status. Privacy/suppression review,
factual review, project approval, and publication remain independent gates.

## Live monthly profile observed 2026-09-27

The National Data Library links the FSA monthly England/Wales CSV snapshot and
labels it under the UK Open Government Licence. A bounded private fetch of the
2026-09-01 edition reproduced the 71-column contract (schema fingerprint
`8a78f58c004a84811e51af53fab6eaf9316a93462575a17f52b6f7a7543e1fa8`) and 5,342
input rows. With adapter `fsa-uk-v2-2`, 4,291 rows normalize and 1,051 quarantine.
Reason counts are `remarks_present` 999, `no_relevant_activity` 9,
`unknown_nation` 31, `address_privacy_risk` 11, and duplicate identifiers 4;
reason totals overlap. The mapping covers explicit animal-product categories
found in the FSA feed, including egg packing, fish processing, LBM dispatch and
purification, while crop-only sprout production and a generic wholesale market
remain unresolved. All normalized monthly coordinates stay null; unverified
X/Y pairs remain private diagnostics, not usable points. Address-only evidence
may enter a separate source-scoped private Geoapify queue, while acquisition
makes no provider request. Records remain private candidates only and the
catalogue's licence statement is not redistribution or publication approval.
Scotland and Northern Ireland remain distinct source scopes.

## Strict live private E2E reacquisition — 2026-10-01

The existing one-command runner fetched the currently linked official FSA
England/Wales CSV (Last-Modified 2026-09-01 10:47:02 GMT) on 2026-10-01 at
21:17:12Z. It is the same 1,774,417-byte snapshot as the previous retained
baseline (SHA-256
`d5cfec048b0f4dc4a8594b0597982f3788f10eb1b4270f9593ead8abce33b61f`), so source
hash, 4,291 accepted candidates, 1,051 quarantines, and 5,342 inputs have zero
delta. Its private raw/normalized/accepted handoffs and source metadata are
retained under ignored `target/real-preview/runs/refresh-fb93336e0b57aa27/`.
The disposable DB/API certificate and same-DB idempotent replay passed with
zero public rows. This verifies private processing only.

The taxonomy projection preserves source activity labels/codes and treats all
FSA mappings as derived. Of 4,291 candidate projections, 3,204 are partial and
1,087 unmapped; none is classified as direct, unclassified, conflicting, or
ambiguous. There are 402 candidates with multiple activity assignments. All
4,291 remain unmapped for geography: the feed has no usable city/postal
coordinates in this approved candidate scope, normalized numeric coordinates
remain suppressed, and the map-visible count is 0 (delta 0 from baseline).
The row-free counts and hashes are in the [BE/UK sprint ledger](../../../../data/manifests/source-evidence-be-uk-20261001.json).

Scotland is a distinct source, `fss_approved_establishments`, not part of this
FSA feed. The current FSS registration has no approved terms-review record and
is not enabled for private preview acquisition; do not fetch it until those
gates and its current official artifact/schema are confirmed.

The shared strict private-preview route was verified on 2026-09-27 with two
live refreshes into a unique disposable database. The final source snapshot was
retrieved at `2026-09-27T21:50:57Z` (source SHA-256
`d5cfec048b0f4dc4a8594b0597982f3788f10eb1b4270f9593ead8abce33b61f`; 1,774,417
bytes). Both refreshes yielded 4,291 listable unmapped observations from 5,342
rows; the second replay was idempotent. Authenticated source list, search and
detail checks passed. Numeric coordinates, city/postal positions, and map pins
were all zero; public rows were zero. This is one-time certification, not a
recurring health signal, source completeness claim, row-level privacy clearance,
or permission to publish.

Run the complete isolated live acquisition, double-import replay, and API
certification with:

```text
python scripts/real_preview.py strict-live-private-e2e --source fsa_approved_establishments
```

Run focused tests from the repository root:

```text
python -m unittest -q pipeline.sources.uk.fsa_approved.test_adapter pipeline.sources.uk.approved.test_compose
```

Private dry-run example:

```text
python -m pipeline.sources.uk.fsa_approved.refresh \
  --raw <restricted-artifact.csv> \
  --run-dir <restricted-run-dir> \
  --effective-date 2026-09-01 \
  --mode dry-run
```
