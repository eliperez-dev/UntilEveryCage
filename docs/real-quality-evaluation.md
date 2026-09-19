# Real geospatial, identity, and graph evaluation

`pipeline/scripts/diagnostics/real_quality_evaluation.py` runs an offline,
deterministic evaluation over the nine checked-in V1-derived legacy snapshots.
It reads all available rows (currently 50,750), hashes each input, and writes
only aggregate metrics: coordinate validity and decimal precision, missing or
invalid coordinates, source-native duplicate/conflict rates, country/source/
category composition, and conservative privacy review queues.

The US strata are selected independently by ascending SHA-256 row fingerprint:
3,500 FSIS locations, 2,500 inspection rows, and 1,000 APHIS observations.
Selection fails closed if an input is too small. The tool counts exact
source-native identifier opportunities and explicit endpoint pairs. It never
joins by names, addresses, coordinates, or proximity; no cross-source
relationship candidate is emitted when the row schema lacks both endpoints.

Run privately:

```powershell
python pipeline/scripts/diagnostics/real_quality_evaluation.py `
  --output data/reports/real-quality-evaluation.json `
  --as-of 2026-09-16T00:00:00Z
```

The report is publication-blocked and row-free. Coordinate validity is not
positional accuracy, privacy indicators are human-review queues rather than
residential classifications, and duplicate/conflict rates are within-source
diagnostics. Raw source artifacts are not present in this checkout, so the
evaluation does not claim raw-preserving acquisition or source-authorized
publication. The US snapshots are sufficient for the requested sample sizes;
the resulting graph yield must still be reviewed before any graph import.
