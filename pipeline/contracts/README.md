# Source-adapter contract

## Shared private-run QA seam

`private_run.run_typed_adapter` provides the common runner for typed
`SourceAdapter` implementations. It writes a deterministic, row-free
`qa.json` beside the adapter manifest, validates count and release-state
invariants, and accepts provenance recorded either at the manifest root or in
the nested `acquisition` object. The report includes schema/count/anomaly and
drift summaries without copying source values, coordinates, or other row data.

When a prior normalized artifact is supplied, disappeared identifiers are
reported only as `not-observed`; they are never converted into closure or
deauthorization claims. Acquisition, ingestion, release approval, and
publication remain separate stages so the scrape-to-ingestion pipeline can be
fully automated without silently turning a failed or incomplete run into a
public result.

Adapters receive a preserved raw artifact and `SourceArtifact` facts: source URL,
UTC retrieval time, SHA-256, byte size, supplied publication/effective dates,
code/config versions, rights/privacy caveats, and coverage. They must retain
source values, make uncertainty explicit, quarantine malformed or unresolved
records, and write deterministic parsed/normalized/quarantined JSONL plus a
manifest. The manifest is private staging (`release_state: not-created`);
passing validation is not approval, health, or publication authorization.

Denmark's `DenmarkSmileyAdapter` is the proving implementation. Network
acquisition remains the existing reviewed acquisition command; raw/private
artifacts are intentionally not fixtures or committed data.

The shared registered-input runner can call Denmark's `run_registered` bridge.
It requires recorded URL, UTC retrieval time, hash, and byte size; missing or
mismatched provenance fails closed. Database import, geocoding, release approval,
and publication remain separately gated.

For disposable development teardown, remove only the selected
`data/staging/denmark-smiley/<run>/` directory after checking retention duties,
then recreate the local database through the existing maintenance script with
an explicitly local development URL. Never point teardown at production and do
not delete retained research evidence without an authorized decision.
