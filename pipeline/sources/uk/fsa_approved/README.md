# FSA approved establishments

This adapter supports the pinned synthetic contract and the observed monthly FSA
CSV profile. The monthly profile requires a recorded SourceArtifact and validates
the AppNo, TradingName, Country, CompetentAuthority, X, Y, AddressWithheld, and
activity headers before staging. FSS Scotland and Northern Ireland remain separate
source feeds; they are not merged into this capability.

Source values and identifiers are preserved. Duplicate IDs are quarantined within
nation, unknown jurisdictions are quarantined, and malformed rows, missing or
unresolved activity, remarks, authority mismatches, and address-risk values remain
explicit review outcomes. `AddressWithheld=Yes` emits no address or coordinates;
X/Y are validated as source longitude/latitude without geocoding. Registered runs
write deterministic parsed, normalized, and quarantined states with a manifest
whose `release_state` is always `not-created` and whose publication state is
private-candidate.

The adapter does not download or automate acquisition. Before a registered run,
maintainers must verify the current official URL, effective/publication date,
ownership, terms/licence, attribution, rate limits, retention/removal rules, and
redistribution status. Privacy/suppression review, factual review, project approval,
and publication remain independent gates.

Run focused tests from the repository root:

```text
python -m unittest -q pipeline.sources.uk.fsa_approved.test_adapter pipeline.sources.uk.approved.test_compose
```
