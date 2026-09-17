# Belgium FASFC private staging

The official pair is the weekly FASFC operator CSV and its separate LAP/PAP
activity-code CSV. `refresh.py` accepts both as already-preserved files, records
independent hashes and retrieval metadata, joins codes exactly, and runs the
shared private lifecycle. `--fetch` is available for an operator-authored terms
review, but the current operator URL may require an assisted browser download.

```text
python -m pipeline.sources.belgium.refresh --operators <private/operators.csv> --activity-codes <private/activity-codes.csv> --run-dir <private/run> --retrieved-at-utc 2026-09-15T00:00:00Z
```

The checked-in fixtures are synthetic only. A current official pair may be
provided through private ignored storage with `--acquisition-metadata`; a
successful run is still only a private candidate with publication blocked. It
is not FASFC approval, project review, or a public release.
