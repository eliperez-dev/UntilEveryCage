# Germany BVL BLtU private staging

The live refresh follows the public BLtU session flow to select and preserve its
general-list CSV export, then stages it privately. It uses bounded HTTPS requests,
session cookies, a 30-second request timeout, a 16 MiB default artifact cap, and
the pinned 50-column schema contract. Effective date stays unknown unless BVL
supplies one. Run it with:

```text
python -m pipeline.sources.germany.refresh --fetch --run-dir <private/run> --output-root <private/raw>
```

Preserved artifacts may still be replayed with `--raw <private/bltu-export.csv>`.

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
