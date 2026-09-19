# Private real-data regression corpus

`pipeline/scripts/diagnostics/real_corpus_report.py` inventories authorized
local acquisition manifests and emits a row-free JSON report. It is safe to
commit because it never reads or copies raw rows, addresses, coordinates, or
derived records. Run:

```text
python pipeline/scripts/diagnostics/real_corpus_report.py --output data/manifests/real-data-corpus-report.json
```

The report distinguishes counted row artifacts from metadata-only and
route-only observations. Unknown counts remain unknown. It records the
requested Sprint 4 threshold (25,000 records, five countries, eight source
profiles) and explicitly reports failure when the local authorized corpus
cannot substantiate it. This checkout currently has no reproducible corpus at
that threshold: most retained evidence is metadata-only, and no release or
publication approval is implied.

Future adapters should add private run manifests with source URL, retrieval
time, SHA-256, byte size, code/config versions, input/normalized/quarantine
counts, and aggregate strata. Raw artifacts remain under ignored private
storage. Reruns should write a new manifest; a missing source is
`not-observed`, not closure. Candidate handoff and test-only API checks remain
separate gates.
