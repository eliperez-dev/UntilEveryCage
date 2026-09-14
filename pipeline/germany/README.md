# Germany V2 adapter foundation

This is a local, synthetic-only foundation. It accepts a previously acquired raw
CSV path; it does not scrape, download, geocode, publish, or promote records. The
adapter writes separate `parsed/`, `normalized/`, and `quarantined/` outputs and
creates an empty `released/` state to make the publication boundary explicit.

Run the acceptance tests from this directory:

```text
python -m unittest -v test_adapter.py
```

The future acquisition runner must populate the registry fields in
[`source-registry.json`](source-registry.json), preserve the raw artifact outside
the repository where required, and record URL, retrieval time, checksum, byte size,
and source publication date. Terms, privacy/safety, suppression, legal, and project
publication approval remain named human gates. No technical pass is approval.

The source classification mapping is intentionally narrow: `CP` and `GME` map to
`Meat Processing`, while `SH` maps to `Meat Slaughter`. Unknown codes quarantine
with their original source values. Missing coordinates remain explicitly unresolved;
the adapter never geocodes or guesses. `orchestrator.py` now provides hash-addressed
input registration, schema/version manifests, isolated runs, failure-safe candidate
handoff, and suppression application. It deliberately leaves the prior eligible
release reference unchanged on failure and never promotes or publishes a release.
Before any real data is considered, add source-specific acquisition, dependency
capture, and suppression checks across map/API/export/cache/history surfaces; terms,
privacy/safety, legal, review, and publication approval remain human gates.
