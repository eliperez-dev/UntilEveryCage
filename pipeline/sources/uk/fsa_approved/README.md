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
still require review. `AddressWithheld=Yes` emits no address or coordinates;
X/Y are validated as source longitude/latitude without geocoding, but monthly
normalized coordinates remain suppressed behind an explicit
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
