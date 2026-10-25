# Germany BVL BLtU private staging

Use the stable [BVL BLtU landing page](https://www.bvl.bund.de/bltu) and select
the current general-list CSV export in the portal. Save that export outside Git
and run the assisted refresh:

```text
python -m pipeline.sources.germany.refresh --raw <private/bltu-export.csv> --run-dir <private/run> --retrieved-at-utc 2026-09-15T00:00:00Z
```

For a captured export with row-free acquisition metadata, also pass
`--acquisition-metadata <private/capture-metadata.json>`.

The typed adapter preserves repeated activity columns and source evidence,
quarantines schema and mapping anomalies, emits shared health evidence, and
cannot create a release. Address/coordinate review, BVL reuse terms, and human
publication approval remain blocked.

## Older adapter foundation

`pipeline/germany/` is the earlier restricted local-artifact foundation, not
another live acquisition path. Its synthetic tests run with
`python -m unittest -v test_adapter.py` from that directory. Its narrow prototype
mapping accepts CP/GME as processing and SH as slaughter; unknown codes retain
their values in quarantine. The BLtU positional profile preserves repeated
headers, irregular row lengths and distinct current/legacy approval IDs.
Schema/config/mapping hashes and diagnostics do not establish public readiness.
Use this source-owned page for implementation instructions and
[the Germany assessment](../../../docs/germany-source-assessment.md) for research.
